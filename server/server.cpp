/*
 * server.cpp — Servidor Central SIMP (Sensor IoT Monitoring Protocol)
 *
 * Uso:  ./server <puerto> <archivo_de_logs>
 *
 * Requisitos:
 *   - C++17 o superior
 *   - POSIX sockets (Linux / AWS EC2 Ubuntu)
 *
 * Compilar (ver Makefile):
 *   g++ -std=c++17 -pthread server.cpp logger.cpp http_server.cpp -o server
 */

#include "protocol.h"
#include "logger.h"
#include "http_server.h"

// POSIX / red
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>

// C++ estándar
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <mutex>
#include <thread>
#include <atomic>
#include <sstream>
#include <cstring>
#include <csignal>
#include <chrono>
#include <algorithm>

// ============================================================
// Configuración global (cambiable por .env o parámetros)
// ============================================================
static const int    HTTP_PORT      = 9001;
static const int    AUTH_PORT      = 9002;
static const int    MAX_CLIENTS    = 100;
static const int    BACKLOG        = 10;
static const char*  AUTH_HOST_ENV  = "AUTH_SERVICE_HOST"; // variable de entorno
static const char*  AUTH_HOST_DEF  = "auth.iot-monitor.local"; // DNS por defecto

// ============================================================
// Estado global del servidor (thread-safe)
// ============================================================

struct SensorInfo {
    std::string id;
    std::string type;
    double      last_value;
    std::string unit;
    long        last_seen;   // timestamp Unix
    std::string client_ip;
    int         client_port;
    int         fd;
};

struct OperatorInfo {
    std::string id;
    std::string client_ip;
    int         client_port;
    int         fd;
    long        connected_at;
};

struct AlertRecord {
    long        timestamp;
    std::string sensor_id;
    std::string sensor_type;
    double      value;
    std::string description;
};

// ── Estado compartido ────────────────────────────────────────
std::map<std::string, SensorInfo>   g_sensors;
std::map<std::string, OperatorInfo> g_operators;
std::vector<AlertRecord>            g_alerts;
std::mutex                          g_state_mutex;
std::atomic<bool>                   g_running(true);
long                                g_start_time;

// ── Socket del servidor ──────────────────────────────────────
int g_server_fd = -1;

// ============================================================
// Forward declarations
// ============================================================
void handle_client(int client_fd,
                   const std::string& client_ip,
                   int client_port);

bool authenticate(const std::string& client_id,
                  const std::string& role,
                  const std::string& token);

void broadcast_alert(const std::string& alert_msg,
                     const std::string& source_sensor_id);

void check_thresholds(const SensorInfo& sensor,
                      double new_value);

std::string build_sensor_list();

void remove_client(const std::string& client_id);

void signal_handler(int sig);

void setup_http_routes(HttpServer& http);

// ============================================================
// main()
// ============================================================
int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Uso: " << argv[0] << " <puerto> <archivo_de_logs>\n";
        return 1;
    }

    int port = std::stoi(argv[1]);
    std::string log_file = argv[2];

    // Inicializar logger
    Logger::init(log_file);
    Logger::log_info("=== Servidor SIMP v1.0 iniciando ===");
    Logger::log_info("Puerto SIMP: " + std::to_string(port));
    Logger::log_info("Puerto HTTP: " + std::to_string(HTTP_PORT));

    g_start_time = static_cast<long>(std::time(nullptr));

    // Manejador de señales para cierre limpio
    std::signal(SIGINT,  signal_handler);
    std::signal(SIGTERM, signal_handler);
    std::signal(SIGPIPE, SIG_IGN); // ignorar pipe roto (cliente desconectado)

    // ── Servidor HTTP ────────────────────────────────────────
    HttpServer http(HTTP_PORT, "../web");
    setup_http_routes(http);
    http.start();

    // ── Socket principal SIMP (TCP) ──────────────────────────
    g_server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (g_server_fd < 0) {
        Logger::log_error("main", "socket() falló: " + std::string(strerror(errno)));
        return 1;
    }

    // Reutilizar dirección/puerto inmediatamente tras reinicio
    int opt = 1;
    setsockopt(g_server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in server_addr{};
    server_addr.sin_family      = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port        = htons(port);

    if (bind(g_server_fd, (struct sockaddr*)&server_addr,
             sizeof(server_addr)) < 0) {
        Logger::log_error("main", "bind() falló: " + std::string(strerror(errno)));
        return 1;
    }

    if (listen(g_server_fd, BACKLOG) < 0) {
        Logger::log_error("main", "listen() falló: " + std::string(strerror(errno)));
        return 1;
    }

    Logger::log_info("Servidor SIMP escuchando en puerto " +
                     std::to_string(port));
    Logger::log_info("Esperando conexiones...");

    // ── Bucle principal de aceptación ───────────────────────
    while (g_running) {
        struct sockaddr_in client_addr{};
        socklen_t addrlen = sizeof(client_addr);

        int client_fd = accept(g_server_fd,
                               (struct sockaddr*)&client_addr,
                               &addrlen);
        if (client_fd < 0) {
            if (g_running) {
                Logger::log_error("accept", strerror(errno));
            }
            continue;
        }

        std::string client_ip   = inet_ntoa(client_addr.sin_addr);
        int         client_port = ntohs(client_addr.sin_port);

        Logger::log_info("Nueva conexión TCP: " + client_ip + ":" +
                         std::to_string(client_port));

        // Cada cliente en su propio hilo
        std::thread(handle_client, client_fd, client_ip, client_port)
            .detach();
    }

    // Cierre limpio
    Logger::log_info("Servidor detenido.");
    Logger::close();
    http.stop();
    close(g_server_fd);
    return 0;
}

// ============================================================
// Manejo de un cliente (sensor u operador)
// ============================================================
void handle_client(int client_fd,
                   const std::string& client_ip,
                   int client_port) {

    std::string registered_id;
    std::string registered_role;
    bool        is_registered = false;

    // Buffer de recepción acumulativo (para mensajes fragmentados)
    std::string recv_buf;
    char        tmp[SIMP::MAX_MSG_LEN];

    while (g_running) {
        // Establecer timeout de lectura (SO_RCVTIMEO)
        struct timeval tv{};
        tv.tv_sec  = SIMP::TIMEOUT_SECS;
        tv.tv_usec = 0;
        setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

        ssize_t bytes = recv(client_fd, tmp, sizeof(tmp) - 1, 0);

        if (bytes <= 0) {
            if (bytes == 0) {
                Logger::log_info("Cliente desconectado: " +
                                 client_ip + ":" + std::to_string(client_port));
            } else {
                Logger::log_error("recv",
                                  client_ip + ":" + std::to_string(client_port) +
                                  " — " + strerror(errno));
            }
            break;
        }

        tmp[bytes] = '\0';
        recv_buf  += tmp;

        // Procesar todos los mensajes completos (\n) del buffer
        size_t pos;
        while ((pos = recv_buf.find('\n')) != std::string::npos) {
            std::string raw_msg = recv_buf.substr(0, pos + 1);
            recv_buf.erase(0, pos + 1);

            Logger::log_request(client_ip, client_port, raw_msg);

            SIMP::Message msg = SIMP::parse(raw_msg);
            std::string response;

            // ── Mensaje inválido ─────────────────────────────
            if (!msg.valid) {
                response = SIMP::make_error(SIMP::E001,
                           "Formato invalido: " + msg.parse_error);
                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ── Tipo desconocido ─────────────────────────────
            if (!SIMP::is_valid_type(msg.type)) {
                response = SIMP::make_error(SIMP::E002,
                           "Tipo de mensaje desconocido: " + msg.type);
                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ════════════════════════════════════════════════
            // REGISTER
            // ════════════════════════════════════════════════
            if (msg.type == SIMP::T_REGISTER) {
                if (msg.fields.size() < 2) {
                    response = SIMP::make_error(SIMP::E001,
                               "REGISTER requiere campos: rol|token");
                } else {
                    std::string role  = msg.fields[0];
                    std::string token = msg.fields[1];

                    if (!SIMP::is_valid_role(role)) {
                        response = SIMP::make_error(SIMP::E001,
                                   "Rol invalido. Use SENSOR u OPERATOR");
                    } else if (!authenticate(msg.sender_id, role, token)) {
                        response = SIMP::make_error(SIMP::E003,
                                   "Autenticacion fallida: token invalido");
                    } else {
                        // Registro exitoso
                        registered_id   = msg.sender_id;
                        registered_role = role;
                        is_registered   = true;

                        std::lock_guard<std::mutex> lock(g_state_mutex);

                        if (role == SIMP::ROLE_SENSOR) {
                            SensorInfo si{};
                            si.id          = registered_id;
                            si.last_seen   = msg.timestamp;
                            si.client_ip   = client_ip;
                            si.client_port = client_port;
                            si.fd          = client_fd;
                            g_sensors[registered_id] = si;
                        } else {
                            OperatorInfo oi{};
                            oi.id           = registered_id;
                            oi.client_ip    = client_ip;
                            oi.client_port  = client_port;
                            oi.fd           = client_fd;
                            oi.connected_at = msg.timestamp;
                            g_operators[registered_id] = oi;
                        }

                        Logger::log_connect(client_ip, client_port,
                                            registered_id, role);
                        response = SIMP::make_ok(
                            "Registro exitoso. Bienvenido " + registered_id);
                    }
                }

                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ── El cliente debe estar registrado para todo lo demás ──
            if (!is_registered) {
                response = SIMP::make_error(SIMP::E003,
                           "Debe registrarse primero con REGISTER");
                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ════════════════════════════════════════════════
            // DATA (solo sensores)
            // ════════════════════════════════════════════════
            if (msg.type == SIMP::T_DATA) {
                if (registered_role != SIMP::ROLE_SENSOR) {
                    response = SIMP::make_error(SIMP::E004,
                               "DATA solo permitido para sensores");
                } else if (msg.fields.size() < 3) {
                    response = SIMP::make_error(SIMP::E001,
                               "DATA requiere: tipo_sensor|valor|unidad");
                } else {
                    std::string sensor_type = msg.fields[0];
                    double      value       = 0.0;
                    std::string unit        = msg.fields[2];

                    try {
                        value = std::stod(msg.fields[1]);
                    } catch (...) {
                        response = SIMP::make_error(SIMP::E001,
                                   "Valor numerico invalido");
                        send(client_fd, response.c_str(), response.size(), 0);
                        Logger::log_response(client_ip, client_port, response);
                        continue;
                    }

                    if (!SIMP::is_valid_sensor_type(sensor_type)) {
                        response = SIMP::make_error(SIMP::E001,
                                   "Tipo de sensor desconocido: " + sensor_type);
                    } else {
                        SensorInfo sensor_copy;
                        {
                            std::lock_guard<std::mutex> lock(g_state_mutex);
                            auto& si      = g_sensors[registered_id];
                            si.type       = sensor_type;
                            si.last_value = value;
                            si.unit       = unit;
                            si.last_seen  = msg.timestamp;
                            sensor_copy   = si;
                        }

                        // Verificar umbrales y disparar alertas
                        check_thresholds(sensor_copy, value);

                        response = SIMP::make_ok("Medicion recibida correctamente");
                    }
                }

                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ════════════════════════════════════════════════
            // QUERY (solo operadores)
            // ════════════════════════════════════════════════
            if (msg.type == SIMP::T_QUERY) {
                if (registered_role != SIMP::ROLE_OPERATOR) {
                    response = SIMP::make_error(SIMP::E004,
                               "QUERY solo permitido para operadores");
                } else if (msg.fields.empty()) {
                    response = SIMP::make_error(SIMP::E001,
                               "QUERY requiere subtipo: STATUS|SENSORS|ALERTS");
                } else {
                    std::string subtype = msg.fields[0];

                    if (subtype == SIMP::QUERY_STATUS) {
                        std::lock_guard<std::mutex> lock(g_state_mutex);
                        long uptime = static_cast<long>(std::time(nullptr))
                                      - g_start_time;
                        response = SIMP::make_status_info(
                            (int)g_sensors.size(),
                            (int)g_operators.size(),
                            (int)g_alerts.size(),
                            uptime);

                    } else if (subtype == SIMP::QUERY_SENSORS) {
                        response = build_sensor_list();

                    } else if (subtype == SIMP::QUERY_ALERTS) {
                        std::lock_guard<std::mutex> lock(g_state_mutex);
                        if (g_alerts.empty()) {
                            response = SIMP::make_ok("Sin alertas recientes");
                        } else {
                            // Devuelve las últimas 10 alertas
                            std::string body = "ALERTS|SERVER|" +
                                std::to_string(SIMP::now_ts()) + "|";
                            int start = std::max(0,
                                (int)g_alerts.size() - 10);
                            for (int i = start; i < (int)g_alerts.size(); i++) {
                                auto& a = g_alerts[i];
                                body += a.sensor_id + ":" +
                                        a.sensor_type + ":" +
                                        std::to_string(a.value) + ":" +
                                        a.description + ";";
                            }
                            body += "\n";
                            response = body;
                        }
                    } else {
                        response = SIMP::make_error(SIMP::E001,
                                   "Subtipo QUERY desconocido: " + subtype);
                    }
                }

                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                continue;
            }

            // ════════════════════════════════════════════════
            // PING → PONG
            // ════════════════════════════════════════════════
            if (msg.type == SIMP::T_PING) {
                response = SIMP::make_pong();
                send(client_fd, response.c_str(), response.size(), 0);
                continue;
            }

            // ════════════════════════════════════════════════
            // DISCONNECT
            // ════════════════════════════════════════════════
            if (msg.type == SIMP::T_DISCONNECT) {
                response = SIMP::make_ok("Hasta luego, " + registered_id);
                send(client_fd, response.c_str(), response.size(), 0);
                Logger::log_response(client_ip, client_port, response);
                break; // salir del bucle → cierra conexión
            }
        } // while mensajes completos
    } // while g_running

    // Limpiar estado del cliente
    if (is_registered) {
        remove_client(registered_id);
        Logger::log_disconnect(client_ip, client_port, registered_id);
    }

    close(client_fd);
}

// ============================================================
// Autenticación contra el servicio externo
// ============================================================
bool authenticate(const std::string& client_id,
                  const std::string& role,
                  const std::string& token) {
    // Resolver nombre DNS del auth service (sin hardcodear IP)
    const char* auth_host = std::getenv(AUTH_HOST_ENV);
    if (!auth_host) auth_host = AUTH_HOST_DEF;

    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family   = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    int rc = getaddrinfo(auth_host,
                         std::to_string(AUTH_PORT).c_str(),
                         &hints, &res);
    if (rc != 0 || res == nullptr) {
        Logger::log_error("auth",
            "DNS falló para " + std::string(auth_host) +
            ": " + gai_strerror(rc));
        // Si no hay auth service disponible, rechazar por seguridad
        return false;
    }

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        freeaddrinfo(res);
        Logger::log_error("auth", "socket() falló");
        return false;
    }

    // Timeout de conexión al auth service
    struct timeval tv{};
    tv.tv_sec  = 5;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    if (connect(sock, res->ai_addr, res->ai_addrlen) < 0) {
        freeaddrinfo(res);
        close(sock);
        Logger::log_error("auth", "connect() al auth service falló");
        return false;
    }
    freeaddrinfo(res);

    // Enviar petición de validación (formato JSON simple)
    std::string json_body = "{\"id\":\"" + client_id +
                            "\",\"role\":\"" + role +
                            "\",\"token\":\"" + token + "\"}";

    std::string request =
        "POST /validate HTTP/1.0\r\n"
        "Host: " + std::string(auth_host) + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
        "Connection: close\r\n"
        "\r\n" + json_body;

    send(sock, request.c_str(), request.size(), 0);

    // Leer respuesta
    std::string resp;
    char buf[512] = {};
    ssize_t bytes;
    while ((bytes = recv(sock, buf, sizeof(buf) - 1, 0)) > 0) {
        buf[bytes] = '\0';
        resp += std::string(buf, bytes);
    }
    close(sock);

    if (resp.empty()) {
        Logger::log_error("auth", "Sin respuesta del auth service");
        return false;
    }

    // Buscar JSON body (después de \r\n\r\n)
    size_t body_pos = resp.find("\r\n\r\n");
    if (body_pos != std::string::npos) {
        resp = resp.substr(body_pos + 4);
    }


    // Respuesta esperada: {"ok":true} o {"ok":false}
    bool ok = (resp.find("\"ok\":true") != std::string::npos ||
               resp.find("\"ok\": true") != std::string::npos);
    Logger::log_info("Auth " + client_id + " [" + role + "]: " +
                     (ok ? "ACEPTADO" : "RECHAZADO"));
    return ok;
}

// ============================================================
// Verificar umbrales y generar alertas
// ============================================================
void check_thresholds(const SensorInfo& sensor, double new_value) {
    SIMP::SensorThreshold thr = SIMP::get_threshold(sensor.type);
    if (thr.min_val == 0.0 && thr.max_val == 0.0) return;

    if (new_value < thr.min_val || new_value > thr.max_val) {
        std::string desc;
        if (new_value > thr.max_val) {
            desc = "CRITICO: " + sensor.type + " supera umbral maximo (" +
                   std::to_string(thr.max_val) + " " + thr.unit + ")";
        } else {
            desc = "CRITICO: " + sensor.type + " cae bajo umbral minimo (" +
                   std::to_string(thr.min_val) + " " + thr.unit + ")";
        }

        std::string alert_msg = SIMP::make_alert(sensor.id, sensor.type,
                                                  new_value, desc);

        Logger::log_alert(sensor.id, desc + " valor=" +
                          std::to_string(new_value));

        // Guardar historial de alerta
        {
            std::lock_guard<std::mutex> lock(g_state_mutex);
            AlertRecord ar;
            ar.timestamp   = SIMP::now_ts();
            ar.sensor_id   = sensor.id;
            ar.sensor_type = sensor.type;
            ar.value       = new_value;
            ar.description = desc;
            g_alerts.push_back(ar);

            // Mantener historial máximo de 100 alertas
            if (g_alerts.size() > 100) {
                g_alerts.erase(g_alerts.begin());
            }
        }

        broadcast_alert(alert_msg, sensor.id);
    }
}

// ============================================================
// Broadcast de alertas a todos los operadores conectados
// ============================================================
void broadcast_alert(const std::string& alert_msg,
                     const std::string& /*source_sensor_id*/) {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    for (auto& kv : g_operators) {
        int fd = kv.second.fd;
        if (fd >= 0) {
            ssize_t sent = send(fd, alert_msg.c_str(), alert_msg.size(), 0);
            if (sent < 0) {
                Logger::log_error("broadcast",
                    "No se pudo enviar alerta a operador " + kv.first);
            }
        }
    }
}

// ============================================================
// Construir lista de sensores activos (para QUERY SENSORS)
// ============================================================
std::string build_sensor_list() {
    std::lock_guard<std::mutex> lock(g_state_mutex);

    std::string payload;
    for (auto& kv : g_sensors) {
        auto& s = kv.second;
        payload += s.id + ":" +
                   s.type + ":" +
                   std::to_string(s.last_value) + ":" +
                   s.unit + ";";
    }

    return SIMP::T_SENSOR_LIST + SIMP::FIELD_SEP +
           "SERVER" + SIMP::FIELD_SEP +
           std::to_string(SIMP::now_ts()) + SIMP::FIELD_SEP +
           std::to_string(g_sensors.size()) + SIMP::FIELD_SEP +
           payload + SIMP::MSG_END;
}

// ============================================================
// Remover cliente del estado global
// ============================================================
void remove_client(const std::string& client_id) {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    g_sensors.erase(client_id);
    g_operators.erase(client_id);
}

// ============================================================
// Señales del sistema
// ============================================================
void signal_handler(int sig) {
    Logger::log_info("Señal recibida (" + std::to_string(sig) +
                     "). Cerrando servidor...");
    g_running = false;
    if (g_server_fd >= 0) {
        close(g_server_fd);
        g_server_fd = -1;
    }
}

// ============================================================
// Rutas HTTP dinámicas (API REST del dashboard)
// ============================================================
void setup_http_routes(HttpServer& http) {

    // GET /api/status — estado general del sistema
    http.add_route("/api/status", [](const HttpRequest&) -> HttpResponse {
        std::lock_guard<std::mutex> lock(g_state_mutex);
        long uptime = static_cast<long>(std::time(nullptr)) - g_start_time;

        std::string json = "{";
        json += "\"sensors\":"   + std::to_string(g_sensors.size())   + ",";
        json += "\"operators\":" + std::to_string(g_operators.size()) + ",";
        json += "\"alerts\":"    + std::to_string(g_alerts.size())    + ",";
        json += "\"uptime\":"    + std::to_string(uptime);
        json += "}";
        return http_json(json);
    });

    // GET /api/sensors — lista de sensores activos
    http.add_route("/api/sensors", [](const HttpRequest&) -> HttpResponse {
        std::lock_guard<std::mutex> lock(g_state_mutex);

        std::string json = "[";
        bool first = true;
        for (auto& kv : g_sensors) {
            auto& s = kv.second;
            if (!first) json += ",";
            json += "{";
            json += "\"id\":\""         + s.id                          + "\",";
            json += "\"type\":\""       + s.type                        + "\",";
            json += "\"value\":"        + std::to_string(s.last_value)  + ",";
            json += "\"unit\":\""       + s.unit                        + "\",";
            json += "\"last_seen\":"    + std::to_string(s.last_seen)   + ",";
            json += "\"ip\":\""         + s.client_ip                   + "\"";
            json += "}";
            first = false;
        }
        json += "]";
        return http_json(json);
    });


    // POST /api/login — proxy al auth service para la interfaz web
    http.add_route("/api/login", [](const HttpRequest& req) -> HttpResponse {
        const char* auth_host_l = std::getenv(AUTH_HOST_ENV);
        if (!auth_host_l) auth_host_l = AUTH_HOST_DEF;

        struct addrinfo hints2{}, *res2 = nullptr;
        hints2.ai_family   = AF_INET;
        hints2.ai_socktype = SOCK_STREAM;

        if (getaddrinfo(auth_host_l, std::to_string(AUTH_PORT).c_str(),
                        &hints2, &res2) != 0 || !res2) {
            return http_error(503, "Service Unavailable",
                              "Auth service no disponible");
        }
        int sock2 = ::socket(AF_INET, SOCK_STREAM, 0);
        struct timeval tv2{}; tv2.tv_sec = 5;
        setsockopt(sock2, SOL_SOCKET, SO_RCVTIMEO, &tv2, sizeof(tv2));
        setsockopt(sock2, SOL_SOCKET, SO_SNDTIMEO, &tv2, sizeof(tv2));
        if (connect(sock2, res2->ai_addr, res2->ai_addrlen) < 0) {
            freeaddrinfo(res2); close(sock2);
            return http_error(503, "Service Unavailable",
                              "No se pudo conectar al auth service");
        }
        freeaddrinfo(res2);
        std::string http_req2 =
            "POST /login HTTP/1.0\r\n"
            "Host: " + std::string(auth_host_l) + "\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: " + std::to_string(req.body.size()) + "\r\n"
            "Connection: close\r\n\r\n" + req.body;
        ::send(sock2, http_req2.c_str(), http_req2.size(), 0);
        std::string raw2;
        char buf2[4096];
        ssize_t n2;
        while ((n2 = recv(sock2, buf2, sizeof(buf2)-1, 0)) > 0) {
            buf2[n2] = '\0'; raw2 += buf2;
        }
        close(sock2);
        size_t bp = raw2.find("\r\n\r\n");
        std::string jbody = (bp != std::string::npos) ? raw2.substr(bp+4) : "{}";
        return http_json(jbody);
    });

    // GET /api/alerts — últimas alertas
    http.add_route("/api/alerts", [](const HttpRequest&) -> HttpResponse {
        std::lock_guard<std::mutex> lock(g_state_mutex);

        std::string json = "[";
        int start = std::max(0, (int)g_alerts.size() - 20);
        bool first = true;
        for (int i = start; i < (int)g_alerts.size(); i++) {
            auto& a = g_alerts[i];
            if (!first) json += ",";
            json += "{";
            json += "\"timestamp\":"  + std::to_string(a.timestamp)  + ",";
            json += "\"sensor_id\":\"" + a.sensor_id                 + "\",";
            json += "\"type\":\""     + a.sensor_type                + "\",";
            json += "\"value\":"      + std::to_string(a.value)      + ",";
            json += "\"desc\":\""     + a.description                + "\"";
            json += "}";
            first = false;
        }
        json += "]";
        return http_json(json);
    });
}

// Nota: La ruta /api/login se registra como extensión en http_server
// El proxy al auth service se realiza desde setup_http_routes en la
// función _handle_login_proxy que se llama desde la ruta registrada.
