package iot;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * SimpProtocol.java — Constantes y utilidades del protocolo SIMP v1.0
 *
 * Equivalente en Java del protocol.h del servidor C++.
 * Uso compartido por todos los clientes Java del sistema.
 */
public class SimpProtocol {

    // ── Separadores ───────────────────────────────────────────
    public static final char   FIELD_SEP    = '|';
    public static final char   RECORD_SEP   = ';';
    public static final char   SUBFIELD_SEP = ':';
    public static final String MSG_END      = "\n";
    public static final int    MAX_MSG_LEN  = 4096;
    public static final int    TIMEOUT_SECS = 60;

    // ── Tipos de mensaje ──────────────────────────────────────
    public static final String T_REGISTER    = "REGISTER";
    public static final String T_DATA        = "DATA";
    public static final String T_QUERY       = "QUERY";
    public static final String T_PING        = "PING";
    public static final String T_DISCONNECT  = "DISCONNECT";
    public static final String T_OK          = "OK";
    public static final String T_ERROR       = "ERROR";
    public static final String T_ALERT       = "ALERT";
    public static final String T_SENSOR_LIST = "SENSOR_LIST";
    public static final String T_STATUS_INFO = "STATUS_INFO";
    public static final String T_PONG        = "PONG";

    // ── Roles ─────────────────────────────────────────────────
    public static final String ROLE_SENSOR   = "SENSOR";
    public static final String ROLE_OPERATOR = "OPERATOR";

    // ── Tipos de sensor ───────────────────────────────────────
    public static final String SENSOR_TEMP      = "TEMPERATURE";
    public static final String SENSOR_HUMIDITY  = "HUMIDITY";
    public static final String SENSOR_PRESSURE  = "PRESSURE";
    public static final String SENSOR_VIBRATION = "VIBRATION";
    public static final String SENSOR_ENERGY    = "ENERGY";

    // ── Umbrales de alerta ────────────────────────────────────
    public record Threshold(double min, double max, String unit) {}

    public static Threshold getThreshold(String sensorType) {
        return switch (sensorType) {
            case SENSOR_TEMP      -> new Threshold(-10.0,   90.0, "Celsius");
            case SENSOR_HUMIDITY  -> new Threshold(  0.0,   95.0, "Percent");
            case SENSOR_PRESSURE  -> new Threshold(800.0, 1100.0, "hPa");
            case SENSOR_VIBRATION -> new Threshold(  0.0,    2.0, "g");
            case SENSOR_ENERGY    -> new Threshold(  0.0,   50.0, "kWh");
            default               -> new Threshold(  0.0,    0.0, "");
        };
    }

    // ── Timestamp Unix actual ─────────────────────────────────
    public static long nowTs() {
        return Instant.now().getEpochSecond();
    }

    // ── Construcción de mensajes ──────────────────────────────

    /** REGISTER|id|ts|rol|token\n */
    public static String makeRegister(String id, String role, String token) {
        return join(T_REGISTER, id, nowTs(), role, token);
    }

    /** DATA|id|ts|tipo|valor|unidad\n */
    public static String makeData(String id, String sensorType,
                                   double value, String unit) {
        return join(T_DATA, id, nowTs(), sensorType, value, unit);
    }

    /** PING|id|ts|OK\n */
    public static String makePing(String id) {
        return join(T_PING, id, nowTs(), "OK");
    }

    /** DISCONNECT|id|ts|BYE\n */
    public static String makeDisconnect(String id) {
        return join(T_DISCONNECT, id, nowTs(), "BYE");
    }

    /** QUERY|id|ts|subtipo\n */
    public static String makeQuery(String id, String subtype) {
        return join(T_QUERY, id, nowTs(), subtype);
    }

    // ── Parsing ───────────────────────────────────────────────

    /** Mensaje SIMP parseado. */
    public record Message(
        String       type,
        String       senderId,
        long         timestamp,
        List<String> fields,
        boolean      valid,
        String       parseError
    ) {
        /** Devuelve el campo i-ésimo del payload o "" si no existe. */
        public String field(int i) {
            return (fields != null && i < fields.size()) ? fields.get(i) : "";
        }
    }

    /** Parsea un mensaje SIMP crudo (puede incluir \n al final). */
    public static Message parse(String raw) {
        String line = raw.strip();
        if (line.isEmpty()) {
            return invalid("Mensaje vacío");
        }

        String[] parts = line.split("\\|", -1);
        if (parts.length < 4) {
            return invalid("Faltan campos (mínimo 4), recibido: " + parts.length);
        }

        long ts;
        try {
            ts = Long.parseLong(parts[2]);
        } catch (NumberFormatException e) {
            return invalid("Timestamp inválido: " + parts[2]);
        }

        List<String> fields = new ArrayList<>();
        for (int i = 3; i < parts.length; i++) {
            fields.add(parts[i]);
        }

        return new Message(parts[0], parts[1], ts, fields, true, null);
    }

    // ── Validación ────────────────────────────────────────────

    public static boolean isValidSensorType(String t) {
        return SENSOR_TEMP.equals(t)      || SENSOR_HUMIDITY.equals(t) ||
               SENSOR_PRESSURE.equals(t) || SENSOR_VIBRATION.equals(t) ||
               SENSOR_ENERGY.equals(t);
    }

    // ── Privados ──────────────────────────────────────────────

    private static Message invalid(String reason) {
        return new Message(null, null, 0, null, false, reason);
    }

    private static String join(Object... parts) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) sb.append(FIELD_SEP);
            sb.append(parts[i]);
        }
        sb.append(MSG_END);
        return sb.toString();
    }

    private SimpProtocol() {}   // no instanciar
}
