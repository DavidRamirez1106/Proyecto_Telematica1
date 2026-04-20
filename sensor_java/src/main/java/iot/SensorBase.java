package iot;

import java.io.*;
import java.net.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.*;

/**
 * SensorBase.java — Clase base abstracta para sensores IoT en Java.
 *
 * Equivalente al sensor_client.py de Python.
 * Implementa: TCP, SIMP REGISTER/DATA/PING/DISCONNECT,
 * reconexión automática, heartbeat en hilo separado.
 *
 * Subclases deben implementar:
 *   getSensorType() → String
 *   getUnit()       → String
 *   measure()       → double
 */
public abstract class SensorBase implements Runnable {

    // ── Configuración ─────────────────────────────────────────
    protected static final int MAX_RETRIES   = 10;
    protected static final int RETRY_DELAY_S = 5;
    protected static final int PING_PERIOD_S = 30;
    protected static final int CONNECT_TIMEOUT_MS = 10_000;

    // ── Campos ────────────────────────────────────────────────
    protected final String sensorId;
    protected final String token;
    protected final String host;
    protected final int    port;
    protected final double intervalSecs;

    protected final AtomicBoolean running = new AtomicBoolean(false);
    protected final Logger log;

    private Socket                  socket;
    private BufferedReader          reader;
    private PrintWriter             writer;
    private final Object            socketLock = new Object();
    private ScheduledExecutorService pingScheduler;

    // ── Constructor ───────────────────────────────────────────

    protected SensorBase(String sensorId, String token,
                         String host, int port, double intervalSecs) {
        this.sensorId      = sensorId;
        this.token         = token;
        this.host          = host;
        this.port          = port;
        this.intervalSecs  = intervalSecs;
        this.log           = Logger.getLogger("Sensor." + sensorId);
    }

    // ── Métodos abstractos ────────────────────────────────────

    /** Tipo de sensor según protocolo SIMP. Ej: "TEMPERATURE" */
    public abstract String getSensorType();

    /** Unidad de medición. Ej: "Celsius" */
    public abstract String getUnit();

    /** Genera y devuelve la medición simulada actual. */
    public abstract double measure();

    // ── Implementación Runnable ───────────────────────────────

    @Override
    public void run() {
        running.set(true);
        int retries = 0;

        while (running.get() && retries < MAX_RETRIES) {
            try {
                connectAndRegister();
                retries = 0;
                dataLoop();

            } catch (ConnectException | SocketTimeoutException e) {
                retries++;
                log.warning(String.format(
                    "Conexión fallida (%s). Reintento %d/%d en %ds...",
                    e.getMessage(), retries, MAX_RETRIES, RETRY_DELAY_S));
                cleanupSocket();
                sleepSeconds(RETRY_DELAY_S);

            } catch (IOException e) {
                if (running.get()) {
                    retries++;
                    log.warning("Error de red: " + e.getMessage() +
                                " — reintentando en " + RETRY_DELAY_S + "s");
                    cleanupSocket();
                    sleepSeconds(RETRY_DELAY_S);
                }
            } catch (Exception e) {
                log.severe("Error inesperado: " + e);
                cleanupSocket();
                retries++;
                sleepSeconds(RETRY_DELAY_S);
            }
        }

        if (retries >= MAX_RETRIES) {
            log.severe("Máximo de reintentos alcanzado. Sensor detenido.");
        }
    }

    /** Detiene el sensor de forma limpia. */
    public void stop() {
        running.set(false);
        stopPingScheduler();
        try {
            sendMessage(SimpProtocol.makeDisconnect(sensorId));
        } catch (Exception ignored) {}
        cleanupSocket();
        log.info("Sensor detenido: " + sensorId);
    }

    // ── Conexión y registro ───────────────────────────────────

    private void connectAndRegister() throws IOException {
        // Resolución DNS — sin IPs hardcodeadas
        InetAddress addr = InetAddress.getByName(host);
        log.info("DNS: " + host + " → " + addr.getHostAddress());

        Socket sock = new Socket();
        sock.connect(new InetSocketAddress(addr, port), CONNECT_TIMEOUT_MS);
        sock.setSoTimeout(0);   // bloqueante tras conectar
        sock.setKeepAlive(true);

        synchronized (socketLock) {
            this.socket = sock;
            this.reader = new BufferedReader(
                new InputStreamReader(sock.getInputStream()));
            this.writer = new PrintWriter(
                new OutputStreamWriter(sock.getOutputStream()), true);
        }

        log.info("Conectado a " + addr.getHostAddress() + ":" + port);

        // Enviar REGISTER
        sendMessage(SimpProtocol.makeRegister(sensorId, SimpProtocol.ROLE_SENSOR, token));

        String resp = readLine();
        log.info("REGISTER resp: " + resp.strip());

        if (resp == null || !resp.startsWith("OK")) {
            throw new IOException("Registro rechazado: " + resp);
        }

        startPingScheduler();
    }

    // ── Bucle de envío de datos ───────────────────────────────

    private void dataLoop() throws IOException, InterruptedException {
        log.info(String.format(
            "Enviando mediciones cada %.1fs [tipo=%s]",
            intervalSecs, getSensorType()));

        while (running.get()) {
            double value = Math.round(measure() * 10000.0) / 10000.0;

            String msg = SimpProtocol.makeData(
                sensorId, getSensorType(), value, getUnit());
            sendMessage(msg);

            String resp = readLine();
            if (resp != null && resp.startsWith("ERROR")) {
                log.warning("Error del servidor: " + resp.strip());
            } else {
                log.fine(String.format("Enviado: %.4f %s", value, getUnit()));
            }

            // Espera con verificación de running
            long waitMs = (long)(intervalSecs * 1000);
            long end    = System.currentTimeMillis() + waitMs;
            while (running.get() && System.currentTimeMillis() < end) {
                Thread.sleep(200);
            }
        }
    }

    // ── Heartbeat ─────────────────────────────────────────────

    private void startPingScheduler() {
        stopPingScheduler();
        pingScheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "Ping-" + sensorId);
            t.setDaemon(true);
            return t;
        });
        pingScheduler.scheduleAtFixedRate(() -> {
            try {
                if (running.get()) {
                    sendMessage(SimpProtocol.makePing(sensorId));
                    log.fine("PING enviado");
                }
            } catch (Exception e) {
                log.warning("PING falló: " + e.getMessage());
            }
        }, PING_PERIOD_S, PING_PERIOD_S, TimeUnit.SECONDS);
    }

    private void stopPingScheduler() {
        if (pingScheduler != null && !pingScheduler.isShutdown()) {
            pingScheduler.shutdownNow();
            pingScheduler = null;
        }
    }

    // ── Utilidades de red ─────────────────────────────────────

    protected void sendMessage(String message) throws IOException {
        synchronized (socketLock) {
            if (writer != null) {
                writer.print(message);
                writer.flush();
                if (writer.checkError()) {
                    throw new IOException("Error al escribir en el socket");
                }
            }
        }
    }

    protected String readLine() throws IOException {
        synchronized (socketLock) {
            if (reader != null) {
                String line = reader.readLine();
                if (line == null) {
                    throw new IOException("Servidor cerró la conexión");
                }
                return line;
            }
        }
        return null;
    }

    private void cleanupSocket() {
        stopPingScheduler();
        synchronized (socketLock) {
            try { if (reader != null) reader.close(); } catch (Exception ignored) {}
            try { if (writer != null) writer.close(); } catch (Exception ignored) {}
            try { if (socket != null) socket.close(); } catch (Exception ignored) {}
            reader = null;
            writer = null;
            socket = null;
        }
    }

    private void sleepSeconds(int secs) {
        try { Thread.sleep(secs * 1000L); } catch (InterruptedException ignored) {}
    }
}
