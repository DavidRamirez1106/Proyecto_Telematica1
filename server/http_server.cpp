#include "http_server.h"
#include "logger.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sstream>
#include <fstream>
#include <algorithm>
#include <cstring>
#include <stdexcept>

// -------------------------------------------------------
// Helpers públicos
// -------------------------------------------------------

HttpResponse http_ok(const std::string& body, const std::string& content_type) {
    HttpResponse resp(200, "OK");
    resp.body = body;
    resp.headers["Content-Type"]   = content_type + "; charset=utf-8";
    resp.headers["Content-Length"] = std::to_string(body.size());
    return resp;
}

HttpResponse http_json(const std::string& json_body) {
    return http_ok(json_body, "application/json");
}

HttpResponse http_error(int code, const std::string& text,
                        const std::string& detail) {
    HttpResponse resp(code, text);
    std::string body = "<html><body><h2>" + std::to_string(code) +
                       " " + text + "</h2><p>" + detail + "</p></body></html>";
    resp.body = body;
    resp.headers["Content-Type"]   = "text/html; charset=utf-8";
    resp.headers["Content-Length"] = std::to_string(body.size());
    return resp;
}

// -------------------------------------------------------
// Constructor / Destructor
// -------------------------------------------------------

HttpServer::HttpServer(int port, const std::string& web_root)
    : port_(port), web_root_(web_root), server_fd_(-1), running_(false) {}

HttpServer::~HttpServer() {
    stop();
}

// -------------------------------------------------------
// Registro de rutas
// -------------------------------------------------------

void HttpServer::add_route(const std::string& path, RouteHandler handler) {
    routes_[path] = handler;
}

// -------------------------------------------------------
// Start / Stop
// -------------------------------------------------------

void HttpServer::start() {
    server_fd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd_ < 0) {
        Logger::log_error("HttpServer", "No se pudo crear socket HTTP");
        return;
    }

    int opt = 1;
    setsockopt(server_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(port_);

    if (bind(server_fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        Logger::log_error("HttpServer", "bind() falló en puerto " +
                          std::to_string(port_));
        close(server_fd_);
        return;
    }

    if (listen(server_fd_, 10) < 0) {
        Logger::log_error("HttpServer", "listen() falló");
        close(server_fd_);
        return;
    }

    running_ = true;
    server_thread_ = std::thread(&HttpServer::listen_loop, this);
    Logger::log_info("Servidor HTTP escuchando en puerto " +
                     std::to_string(port_));
}

void HttpServer::stop() {
    running_ = false;
    if (server_fd_ >= 0) {
        close(server_fd_);
        server_fd_ = -1;
    }
    if (server_thread_.joinable()) {
        server_thread_.join();
    }
}

// -------------------------------------------------------
// Bucle principal de aceptación
// -------------------------------------------------------

void HttpServer::listen_loop() {
    while (running_) {
        struct sockaddr_in client_addr{};
        socklen_t len = sizeof(client_addr);

        int client_fd = accept(server_fd_,
                               (struct sockaddr*)&client_addr, &len);
        if (client_fd < 0) {
            if (running_) {
                Logger::log_error("HttpServer", "accept() falló");
            }
            continue;
        }

        std::string client_ip = inet_ntoa(client_addr.sin_addr);
        int         client_port = ntohs(client_addr.sin_port);

        // Cada petición HTTP en su propio hilo (detached — petición corta)
        std::thread([this, client_fd, client_ip, client_port]() {
            handle_client(client_fd, client_ip, client_port);
        }).detach();
    }
}

// -------------------------------------------------------
// Manejo de cliente HTTP
// -------------------------------------------------------

void HttpServer::handle_client(int client_fd,
                                const std::string& client_ip,
                                int client_port) {
    char buffer[8192] = {};
    ssize_t bytes = recv(client_fd, buffer, sizeof(buffer) - 1, 0);

    if (bytes <= 0) {
        close(client_fd);
        return;
    }

    std::string raw_request(buffer, bytes);
    Logger::log_request(client_ip, client_port,
                        raw_request.substr(0, raw_request.find('\n')));

    HttpRequest  req  = parse_request(raw_request);
    HttpResponse resp;

    if (req.method != "GET"  && req.method != "POST") {
        resp = method_not_allowed();
    } else {
        // Primero busca ruta dinámica registrada
        auto it = routes_.find(req.path);
        if (it != routes_.end()) {
            try {
                resp = it->second(req);
            } catch (const std::exception& e) {
                resp = http_error(500, "Internal Server Error", e.what());
            }
        } else {
            // Si no existe ruta, intenta servir archivo estático
            resp = serve_file(req.path);
        }
    }

    std::string raw_resp = build_response(resp);
    send(client_fd, raw_resp.c_str(), raw_resp.size(), 0);

    Logger::log_response(client_ip, client_port,
                         "HTTP " + std::to_string(resp.status_code) +
                         " " + resp.status_text);

    close(client_fd);
}

// -------------------------------------------------------
// Parsing de la petición HTTP
// -------------------------------------------------------

HttpRequest HttpServer::parse_request(const std::string& raw) {
    HttpRequest req;
    std::istringstream stream(raw);
    std::string line;

    // Primera línea: METHOD PATH HTTP/VERSION
    if (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::istringstream first_line(line);
        first_line >> req.method >> req.path >> req.http_version;
    }

    // Cabeceras
    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) break; // línea vacía = fin de cabeceras

        size_t colon = line.find(':');
        if (colon != std::string::npos) {
            std::string key   = line.substr(0, colon);
            std::string value = line.substr(colon + 2); // saltar ": "
            req.headers[key] = value;
        }
    }

    // Body (todo lo que queda)
    std::string body_line;
    while (std::getline(stream, body_line)) {
        req.body += body_line + "\n";
    }

    // Decodificación básica de path: / → /index.html
    if (req.path == "/") {
        req.path = "/index.html";
    }

    return req;
}

// -------------------------------------------------------
// Construcción de la respuesta HTTP en texto
// -------------------------------------------------------

std::string HttpServer::build_response(const HttpResponse& resp) {
    std::ostringstream oss;
    oss << "HTTP/1.1 " << resp.status_code << " " << resp.status_text << "\r\n";
    oss << "Server: SIMP-HTTP/1.0\r\n";
    oss << "Connection: close\r\n";

    for (auto& kv : resp.headers) {
        oss << kv.first << ": " << kv.second << "\r\n";
    }

    oss << "\r\n";
    oss << resp.body;
    return oss.str();
}

// -------------------------------------------------------
// Servicio de archivos estáticos
// -------------------------------------------------------

HttpResponse HttpServer::serve_file(const std::string& url_path) {
    // Evitar path traversal: rechazar ".."
    if (url_path.find("..") != std::string::npos) {
        return http_error(403, "Forbidden", "Acceso denegado");
    }

    std::string filepath = web_root_ + url_path;

    if (!file_exists(filepath)) {
        return not_found();
    }

    std::string content = read_file(filepath);
    if (content.empty() && !file_exists(filepath)) {
        return http_error(500, "Internal Server Error", "No se pudo leer el archivo");
    }

    // Determinar extensión para MIME type
    std::string ext;
    size_t dot = filepath.rfind('.');
    if (dot != std::string::npos) {
        ext = filepath.substr(dot + 1);
    }

    HttpResponse resp(200, "OK");
    resp.body = content;
    resp.headers["Content-Type"]   = mime_type(ext) + "; charset=utf-8";
    resp.headers["Content-Length"] = std::to_string(content.size());
    return resp;
}

HttpResponse HttpServer::not_found() {
    return http_error(404, "Not Found", "El recurso solicitado no existe");
}

HttpResponse HttpServer::method_not_allowed() {
    HttpResponse resp = http_error(405, "Method Not Allowed",
                                   "Solo se aceptan peticiones GET");
    resp.headers["Allow"] = "GET";
    return resp;
}

// -------------------------------------------------------
// Utilidades
// -------------------------------------------------------

std::string HttpServer::mime_type(const std::string& ext) {
    if (ext == "html" || ext == "htm") return "text/html";
    if (ext == "css")                  return "text/css";
    if (ext == "js")                   return "application/javascript";
    if (ext == "json")                 return "application/json";
    if (ext == "png")                  return "image/png";
    if (ext == "jpg" || ext == "jpeg") return "image/jpeg";
    if (ext == "ico")                  return "image/x-icon";
    if (ext == "txt")                  return "text/plain";
    return "application/octet-stream";
}

std::string HttpServer::read_file(const std::string& filepath) {
    std::ifstream f(filepath, std::ios::binary);
    if (!f.is_open()) return "";
    return std::string((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());
}

bool HttpServer::file_exists(const std::string& filepath) {
    std::ifstream f(filepath);
    return f.good();
}
