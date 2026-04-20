#include "logger.h"

// Definición de miembros estáticos
std::ofstream Logger::log_file_;
std::mutex    Logger::mutex_;
bool          Logger::initialized_ = false;

// -------------------------------------------------------
// Privados
// -------------------------------------------------------

std::string Logger::current_timestamp() {
    std::time_t now = std::time(nullptr);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
    return std::string(buf);
}

std::string Logger::level_tag(LogLevel lvl) {
    switch (lvl) {
        case LogLevel::INFO:      return "[INFO   ]";
        case LogLevel::WARNING:   return "[WARNING]";
        case LogLevel::ERROR_LVL: return "[ERROR  ]";
        case LogLevel::ALERT:     return "[ALERT  ]";
        default:                  return "[LOG    ]";
    }
}

void Logger::write(LogLevel lvl, const std::string& line) {
    std::lock_guard<std::mutex> lock(mutex_);

    std::string entry = current_timestamp() + "  " + level_tag(lvl) + "  " + line;

    // Siempre a consola
    if (lvl == LogLevel::ERROR_LVL || lvl == LogLevel::ALERT) {
        std::cerr << entry << std::endl;
    } else {
        std::cout << entry << std::endl;
    }

    // También a archivo si está inicializado
    if (initialized_ && log_file_.is_open()) {
        log_file_ << entry << std::endl;
        log_file_.flush();
    }
}

// -------------------------------------------------------
// Públicos
// -------------------------------------------------------

void Logger::init(const std::string& filepath) {
    std::lock_guard<std::mutex> lock(mutex_);
    log_file_.open(filepath, std::ios::app);
    if (!log_file_.is_open()) {
        std::cerr << "[ERROR] No se pudo abrir el archivo de logs: "
                  << filepath << std::endl;
        return;
    }
    initialized_ = true;

    // Encabezado de sesión en el archivo
    std::string sep(60, '=');
    log_file_ << sep << std::endl;
    log_file_ << "  Servidor SIMP iniciado: " << current_timestamp() << std::endl;
    log_file_ << sep << std::endl;
    log_file_.flush();

    std::cout << "[INFO   ]  Logger iniciado. Archivo: " << filepath << std::endl;
}

void Logger::close() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (log_file_.is_open()) {
        log_file_ << std::string(60, '=') << std::endl;
        log_file_ << "  Servidor SIMP detenido: " << current_timestamp() << std::endl;
        log_file_ << std::string(60, '=') << std::endl;
        log_file_.close();
    }
}

void Logger::log_request(const std::string& client_ip,
                         int                client_port,
                         const std::string& message) {
    std::ostringstream oss;
    oss << "RECV  " << client_ip << ":" << client_port
        << "  <<  " << message;
    write(LogLevel::INFO, oss.str());
}

void Logger::log_response(const std::string& client_ip,
                          int                client_port,
                          const std::string& response) {
    std::ostringstream oss;
    oss << "SEND  " << client_ip << ":" << client_port
        << "  >>  " << response;
    write(LogLevel::INFO, oss.str());
}

void Logger::log_error(const std::string& context,
                       const std::string& detail) {
    write(LogLevel::ERROR_LVL, context + ": " + detail);
}

void Logger::log_alert(const std::string& sensor_id,
                       const std::string& detail) {
    write(LogLevel::ALERT, "Sensor " + sensor_id + " — " + detail);
}

void Logger::log_info(const std::string& message) {
    write(LogLevel::INFO, message);
}

void Logger::log_connect(const std::string& client_ip,
                         int                client_port,
                         const std::string& client_id,
                         const std::string& role) {
    std::ostringstream oss;
    oss << "CONNECT  " << client_ip << ":" << client_port
        << "  id=" << client_id << "  rol=" << role;
    write(LogLevel::INFO, oss.str());
}

void Logger::log_disconnect(const std::string& client_ip,
                            int                client_port,
                            const std::string& client_id) {
    std::ostringstream oss;
    oss << "DISCONNECT  " << client_ip << ":" << client_port
        << "  id=" << client_id;
    write(LogLevel::INFO, oss.str());
}
