#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <string>
#include <vector>
#include <sstream>
#include <ctime>

/* =========================================================
   SIMP — Sensor IoT Monitoring Protocol  v1.0
   Protocolo de capa de aplicación basado en texto / TCP
   Separador de campos: '|'   Terminador: '\n'
   ========================================================= */

namespace SIMP {

// ---------------------------------------------------------
// Constantes del protocolo
// ---------------------------------------------------------
static const char   FIELD_SEP    = '|';
static const char   RECORD_SEP   = ';';
static const char   SUBFIELD_SEP = ':';
static const char   MSG_END      = '\n';
static const int    TIMEOUT_SECS = 60;   // timeout heartbeat
static const int    MAX_MSG_LEN  = 4096; // bytes máximos por mensaje

// ---------------------------------------------------------
// Tipos de mensaje (cliente → servidor)
// ---------------------------------------------------------
static const std::string T_REGISTER   = "REGISTER";
static const std::string T_DATA       = "DATA";
static const std::string T_QUERY      = "QUERY";
static const std::string T_PING       = "PING";
static const std::string T_DISCONNECT = "DISCONNECT";

// Tipos de mensaje (servidor → cliente)
static const std::string T_OK          = "OK";
static const std::string T_ERROR       = "ERROR";
static const std::string T_ALERT       = "ALERT";
static const std::string T_SENSOR_LIST = "SENSOR_LIST";
static const std::string T_STATUS_INFO = "STATUS_INFO";
static const std::string T_PONG        = "PONG";

// ---------------------------------------------------------
// Roles de cliente
// ---------------------------------------------------------
static const std::string ROLE_SENSOR   = "SENSOR";
static const std::string ROLE_OPERATOR = "OPERATOR";

// ---------------------------------------------------------
// Subtipos de QUERY
// ---------------------------------------------------------
static const std::string QUERY_STATUS  = "STATUS";
static const std::string QUERY_SENSORS = "SENSORS";
static const std::string QUERY_ALERTS  = "ALERTS";

// ---------------------------------------------------------
// Tipos de sensor
// ---------------------------------------------------------
static const std::string SENSOR_TEMP     = "TEMPERATURE";
static const std::string SENSOR_HUMIDITY = "HUMIDITY";
static const std::string SENSOR_PRESSURE = "PRESSURE";
static const std::string SENSOR_VIBRATION= "VIBRATION";
static const std::string SENSOR_ENERGY   = "ENERGY";

// ---------------------------------------------------------
// Códigos de error
// ---------------------------------------------------------
static const std::string E001 = "E001"; // Formato inválido
static const std::string E002 = "E002"; // Tipo desconocido
static const std::string E003 = "E003"; // Auth fallida
static const std::string E004 = "E004"; // Permiso denegado
static const std::string E005 = "E005"; // Sensor no registrado
static const std::string E006 = "E006"; // Operador no registrado
static const std::string E007 = "E007"; // Auth service no disponible

// ---------------------------------------------------------
// Umbrales de alerta por tipo de sensor
// ---------------------------------------------------------
struct SensorThreshold {
    double min_val;
    double max_val;
    std::string unit;
};

inline SensorThreshold get_threshold(const std::string& sensor_type) {
    if (sensor_type == SENSOR_TEMP)      return {-10.0,  90.0,   "Celsius"};
    if (sensor_type == SENSOR_HUMIDITY)  return {  0.0,  95.0,   "Percent"};
    if (sensor_type == SENSOR_PRESSURE)  return {800.0, 1100.0,  "hPa"};
    if (sensor_type == SENSOR_VIBRATION) return {  0.0,   2.0,   "g"};
    if (sensor_type == SENSOR_ENERGY)    return {  0.0,  50.0,   "kWh"};
    return {0.0, 0.0, ""};
}

// ---------------------------------------------------------
// Estructura de mensaje SIMP parseado
// ---------------------------------------------------------
struct Message {
    std::string type;
    std::string sender_id;
    long        timestamp;
    std::vector<std::string> fields; // campos del payload

    bool valid;
    std::string parse_error;

    Message() : timestamp(0), valid(false) {}
};

// ---------------------------------------------------------
// Utilidades de parsing y construcción
// ---------------------------------------------------------

// Divide una línea por el separador de campos
inline std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> tokens;
    std::stringstream ss(s);
    std::string token;
    while (std::getline(ss, token, delim)) {
        tokens.push_back(token);
    }
    return tokens;
}

// Parsea un mensaje SIMP crudo en la estructura Message
inline Message parse(const std::string& raw) {
    Message msg;
    std::string line = raw;

    // Eliminar \r\n o \n del final
    if (!line.empty() && line.back() == '\n') line.pop_back();
    if (!line.empty() && line.back() == '\r') line.pop_back();

    if (line.empty()) {
        msg.parse_error = "Mensaje vacío";
        return msg;
    }

    std::vector<std::string> parts = split(line, FIELD_SEP);

    if (parts.size() < 4) {
        msg.parse_error = "Faltan campos obligatorios (mínimo 4)";
        return msg;
    }

    msg.type      = parts[0];
    msg.sender_id = parts[1];

    try {
        msg.timestamp = std::stol(parts[2]);
    } catch (...) {
        msg.parse_error = "Timestamp inválido";
        return msg;
    }

    // El resto son campos del payload
    for (size_t i = 3; i < parts.size(); i++) {
        msg.fields.push_back(parts[i]);
    }

    msg.valid = true;
    return msg;
}

// Construye timestamp actual
inline long now_ts() {
    return static_cast<long>(std::time(nullptr));
}

// ---------------------------------------------------------
// Constructores de mensajes del servidor
// ---------------------------------------------------------

inline std::string make_ok(const std::string& description) {
    return T_OK + FIELD_SEP + "SERVER" + FIELD_SEP +
           std::to_string(now_ts()) + FIELD_SEP +
           description + MSG_END;
}

inline std::string make_error(const std::string& code,
                               const std::string& description) {
    return T_ERROR + FIELD_SEP + "SERVER" + FIELD_SEP +
           std::to_string(now_ts()) + FIELD_SEP +
           code + FIELD_SEP + description + MSG_END;
}

inline std::string make_pong() {
    return T_PONG + FIELD_SEP + "SERVER" + FIELD_SEP +
           std::to_string(now_ts()) + FIELD_SEP + "OK" + MSG_END;
}

inline std::string make_alert(const std::string& sensor_id,
                               const std::string& sensor_type,
                               double value,
                               const std::string& description) {
    return T_ALERT + FIELD_SEP + "SERVER" + FIELD_SEP +
           std::to_string(now_ts()) + FIELD_SEP +
           sensor_id + FIELD_SEP +
           sensor_type + FIELD_SEP +
           std::to_string(value) + FIELD_SEP +
           description + MSG_END;
}

inline std::string make_status_info(int n_sensors, int n_operators,
                                     int n_alerts, long uptime_secs) {
    return T_STATUS_INFO + FIELD_SEP + "SERVER" + FIELD_SEP +
           std::to_string(now_ts()) + FIELD_SEP +
           "sensores:" + std::to_string(n_sensors) + FIELD_SEP +
           "operadores:" + std::to_string(n_operators) + FIELD_SEP +
           "alertas:" + std::to_string(n_alerts) + FIELD_SEP +
           "uptime:" + std::to_string(uptime_secs) + MSG_END;
}

// ---------------------------------------------------------
// Validación de tipos conocidos
// ---------------------------------------------------------
inline bool is_valid_type(const std::string& t) {
    return t == T_REGISTER || t == T_DATA    || t == T_QUERY ||
           t == T_PING     || t == T_DISCONNECT;
}

inline bool is_valid_sensor_type(const std::string& t) {
    return t == SENSOR_TEMP     || t == SENSOR_HUMIDITY ||
           t == SENSOR_PRESSURE || t == SENSOR_VIBRATION ||
           t == SENSOR_ENERGY;
}

inline bool is_valid_role(const std::string& r) {
    return r == ROLE_SENSOR || r == ROLE_OPERATOR;
}

} // namespace SIMP

#endif // PROTOCOL_H
