package iot;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.*;

/**
 * Main.java — Punto de entrada del cliente de sensores Java.
 *
 * Lanza los 5 tipos de sensores en hilos independientes.
 * Soporta cierre limpio con Ctrl+C (shutdown hook).
 *
 * Uso:
 *   java -cp . iot.Main
 *   java -cp . iot.Main monitor.iot-monitor.local 9000
 *
 * Variables de entorno:
 *   SIMP_SERVER_HOST  — hostname del servidor (default: monitor.iot-monitor.local)
 *   SIMP_SERVER_PORT  — puerto TCP (default: 9000)
 */
public class Main {

    private static final Logger log = Logger.getLogger("Main");

    public static void main(String[] args) throws InterruptedException {
        configureLogging();

        // ── Leer host y puerto ────────────────────────────────
        String host = System.getenv("SIMP_SERVER_HOST");
        if (host == null || host.isBlank()) {
            host = (args.length >= 1) ? args[0] : "monitor.iot-monitor.local";
        }

        int port = 9000;
        try {
            String portEnv = System.getenv("SIMP_SERVER_PORT");
            if (portEnv != null && !portEnv.isBlank()) {
                port = Integer.parseInt(portEnv.trim());
            } else if (args.length >= 2) {
                port = Integer.parseInt(args[1]);
            }
        } catch (NumberFormatException e) {
            log.warning("Puerto inválido, usando 9000");
        }

        // ── Tokens (leer de entorno o usar valores de prueba) ─
        String tokenTemp  = envOrDefault("TOKEN_TEMP",  "tok_temp_001");
        String tokenHum   = envOrDefault("TOKEN_HUM",   "tok_hum_001");
        String tokenPres  = envOrDefault("TOKEN_PRES",  "tok_pres_001");
        String tokenVib   = envOrDefault("TOKEN_VIB",   "tok_vib_001");
        String tokenEner  = envOrDefault("TOKEN_ENER",  "tok_ener_001");

        log.info("==================================================");
        log.info("  SIMP Sensor Client — Java");
        log.info("  Servidor: " + host + ":" + port);
        log.info("==================================================");

        // ── Crear sensores ────────────────────────────────────
        List<SensorBase> sensors = new ArrayList<>();
        sensors.add(new SensorTypes.TemperatureSensor("sensor_temp_java_01", tokenTemp,  host, port));
        sensors.add(new SensorTypes.HumiditySensor   ("sensor_hum_java_01",  tokenHum,   host, port));
        sensors.add(new SensorTypes.PressureSensor   ("sensor_pres_java_01", tokenPres,  host, port));
        sensors.add(new SensorTypes.VibrationSensor  ("sensor_vib_java_01",  tokenVib,   host, port));
        sensors.add(new SensorTypes.EnergySensor     ("sensor_ener_java_01", tokenEner,  host, port));

        // ── Ejecutar en pool de hilos ─────────────────────────
        ExecutorService pool = Executors.newFixedThreadPool(
            sensors.size(),
            r -> {
                Thread t = new Thread(r);
                t.setDaemon(false);
                return t;
            }
        );

        // Arranque escalonado para no saturar el servidor
        for (SensorBase sensor : sensors) {
            pool.submit(sensor);
            log.info("Sensor iniciado: " + sensor.sensorId +
                     " [" + sensor.getSensorType() + "]");
            Thread.sleep(400);
        }

        log.info(sensors.size() + " sensores activos. Ctrl+C para detener.\n");

        // ── Shutdown hook — cierre limpio con Ctrl+C ──────────
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            log.info("Señal de cierre recibida. Deteniendo sensores...");
            for (SensorBase s : sensors) {
                s.stop();
            }
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException ignored) {}
            log.info("Todos los sensores detenidos.");
        }, "ShutdownHook"));

        // Esperar indefinidamente hasta señal
        pool.awaitTermination(Long.MAX_VALUE, TimeUnit.DAYS);
    }

    // ── Utilidades ────────────────────────────────────────────

    private static String envOrDefault(String key, String def) {
        String val = System.getenv(key);
        return (val != null && !val.isBlank()) ? val.trim() : def;
    }

    private static void configureLogging() {
        // Formato de log legible en consola
        System.setProperty("java.util.logging.SimpleFormatter.format",
            "%1$tY-%1$tm-%1$td %1$tH:%1$tM:%1$tS  [%-8s]  %3$s — %5$s%n");

        Logger root = Logger.getLogger("");
        root.setLevel(Level.INFO);

        for (Handler h : root.getHandlers()) {
            h.setLevel(Level.INFO);
            h.setFormatter(new SimpleFormatter());
        }
    }
}
