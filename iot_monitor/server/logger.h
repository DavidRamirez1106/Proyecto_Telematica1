#ifndef LOGGER_H
#define LOGGER_H

#include <string>
#include <fstream>
#include <mutex>
#include <iostream>
#include <ctime>
#include <sstream>

/* =========================================================
   Logger — Sistema de registro de eventos del servidor SIMP
   Escribe en consola y en archivo simultáneamente.
   Thread-safe (usa mutex).
   ========================================================= */

enum class LogLevel {
    INFO,
    WARNING,
    ERROR_LVL,
    ALERT
};

class Logger {
public:
    // Inicializa el logger con el archivo de salida
    static void init(const std::string& filepath);

    // Cierra el archivo de log
    static void close();

    // Registra una petición entrante de un cliente
    static void log_request(const std::string& client_ip,
                            int                client_port,
                            const std::string& message);

    // Registra una respuesta enviada a un cliente
    static void log_response(const std::string& client_ip,
                             int                client_port,
                             const std::string& response);

    // Registra un error
    static void log_error(const std::string& context,
                          const std::string& detail);

    // Registra una alerta generada por el sistema
    static void log_alert(const std::string& sensor_id,
                          const std::string& detail);

    // Mensaje informativo general
    static void log_info(const std::string& message);

    // Registra conexión de un cliente
    static void log_connect(const std::string& client_ip,
                            int                client_port,
                            const std::string& client_id,
                            const std::string& role);

    // Registra desconexión de un cliente
    static void log_disconnect(const std::string& client_ip,
                               int                client_port,
                               const std::string& client_id);

private:
    static std::ofstream  log_file_;
    static std::mutex     mutex_;
    static bool           initialized_;

    static std::string current_timestamp();
    static std::string level_tag(LogLevel lvl);
    static void write(LogLevel lvl, const std::string& line);
};

#endif // LOGGER_H
