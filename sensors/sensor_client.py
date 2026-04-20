"""
sensor_client.py — Clase base para todos los sensores IoT simulados.

Implementa:
  - Conexión TCP al servidor SIMP
  - Registro con el protocolo SIMP (REGISTER)
  - Envío periódico de mediciones (DATA)
  - Heartbeat automático (PING/PONG)
  - Reconexión automática ante fallos de red
  - Desconexión limpia (DISCONNECT)
  - Resolución de nombres DNS (sin IPs hardcodeadas)
"""

import socket
import time
import threading
import logging
import os
from abc import ABC, abstractmethod

# ─── Configuración del logger de Python ───────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─── Constantes del protocolo SIMP ────────────────────────────
FIELD_SEP    = "|"
MSG_END      = "\n"
PING_INTERVAL = 30    # segundos entre PING
RETRY_DELAY   = 5     # segundos entre intentos de reconexión
MAX_RETRIES   = 10    # intentos máximos antes de rendirse


def simp_timestamp() -> str:
    """Retorna el timestamp Unix actual como string."""
    return str(int(time.time()))


def simp_message(*fields) -> str:
    """Construye un mensaje SIMP uniendo campos con '|' y agregando '\\n'."""
    return FIELD_SEP.join(str(f) for f in fields) + MSG_END


class SensorClient(ABC):
    """
    Clase base abstracta para sensores IoT.

    Subclases deben implementar:
      - sensor_type() → str   : tipo de sensor (TEMPERATURE, HUMIDITY, etc.)
      - measure()     → float : genera la medición simulada actual
      - unit()        → str   : unidad de la medición (Celsius, Percent, etc.)

    Uso:
      sensor = TemperatureSensor("sensor_temp_01", "tok_abc123")
      sensor.run()   # bucle bloqueante
      # o en hilo:
      t = threading.Thread(target=sensor.run)
      t.start()
    """

    def __init__(self, sensor_id: str, token: str,
                 host: str = None, port: int = None,
                 interval: float = 5.0):
        """
        Args:
            sensor_id : identificador único del sensor
            token     : token de autenticación para el auth service
            host      : hostname del servidor (lee AUTH_SERVICE_HOST si None)
            port      : puerto TCP del servidor SIMP (default 9000)
            interval  : segundos entre mediciones
        """
        self.sensor_id = sensor_id
        self.token     = token
        self.host      = host or os.getenv("SIMP_SERVER_HOST", "monitor.iot-monitor.local")
        self.port      = port or int(os.getenv("SIMP_SERVER_PORT", "9000"))
        self.interval  = interval

        self._sock: socket.socket | None = None
        self._running  = False
        self._lock     = threading.Lock()
        self._ping_timer: threading.Timer | None = None

        self.log = logging.getLogger(f"Sensor.{sensor_id}")

    # ── Métodos abstractos que cada sensor debe implementar ──

    @property
    @abstractmethod
    def sensor_type(self) -> str:
        """Ej: 'TEMPERATURE', 'HUMIDITY', etc."""

    @abstractmethod
    def measure(self) -> float:
        """Genera y retorna la medición simulada actual."""

    @property
    @abstractmethod
    def unit(self) -> str:
        """Ej: 'Celsius', 'Percent', 'hPa', 'g', 'kWh'."""

    # ── Interfaz pública ──────────────────────────────────────

    def run(self):
        """Bucle principal: conecta, registra y envía mediciones indefinidamente."""
        self._running = True
        retries = 0

        while self._running and retries < MAX_RETRIES:
            try:
                self._connect_and_register()
                retries = 0          # reset al conectar exitosamente
                self._data_loop()    # bloquea hasta error o stop()

            except (ConnectionRefusedError, OSError) as e:
                retries += 1
                self.log.warning(
                    f"Conexión fallida ({e}). Reintento {retries}/{MAX_RETRIES} "
                    f"en {RETRY_DELAY}s..."
                )
                self._cleanup_socket()
                time.sleep(RETRY_DELAY)

            except Exception as e:
                self.log.error(f"Error inesperado: {e}")
                self._cleanup_socket()
                time.sleep(RETRY_DELAY)
                retries += 1

        if retries >= MAX_RETRIES:
            self.log.error("Número máximo de reintentos alcanzado. Deteniendo sensor.")

    def stop(self):
        """Detiene el sensor de forma limpia."""
        self._running = False
        self._cancel_ping()
        try:
            if self._sock:
                msg = simp_message("DISCONNECT", self.sensor_id,
                                   simp_timestamp(), "BYE")
                self._send(msg)
        except Exception:
            pass
        self._cleanup_socket()
        self.log.info("Sensor detenido.")

    # ── Conexión y registro ───────────────────────────────────

    def _resolve_host(self) -> str:
        """Resuelve el hostname via DNS. Lanza excepción si falla."""
        try:
            ip = socket.gethostbyname(self.host)
            self.log.info(f"DNS resuelto: {self.host} → {ip}")
            return ip
        except socket.gaierror as e:
            self.log.error(f"Fallo DNS para '{self.host}': {e}")
            raise

    def _connect_and_register(self):
        """Resuelve DNS, conecta por TCP y envía REGISTER."""
        ip = self._resolve_host()

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(10)
        self._sock.connect((ip, self.port))
        self._sock.settimeout(None)   # modo bloqueante tras conectar

        self.log.info(f"Conectado a {ip}:{self.port}")

        # Enviar REGISTER
        reg_msg = simp_message(
            "REGISTER", self.sensor_id, simp_timestamp(),
            "SENSOR", self.token
        )
        self._send(reg_msg)

        # Leer respuesta del servidor
        resp = self._recv_line()
        self.log.info(f"Respuesta REGISTER: {resp.strip()}")

        if not resp.startswith("OK"):
            raise ConnectionError(f"Registro rechazado: {resp.strip()}")

        # Iniciar heartbeat periódico
        self._schedule_ping()

    # ── Bucle de envío de datos ───────────────────────────────

    def _data_loop(self):
        """Envía mediciones periódicamente hasta que se detenga."""
        self.log.info(
            f"Iniciando envío de mediciones cada {self.interval}s "
            f"[tipo={self.sensor_type}]"
        )

        while self._running:
            try:
                value = round(self.measure(), 4)
                data_msg = simp_message(
                    "DATA", self.sensor_id, simp_timestamp(),
                    self.sensor_type, value, self.unit
                )
                self._send(data_msg)

                resp = self._recv_line()
                if resp.startswith("ERROR"):
                    self.log.warning(f"Error del servidor: {resp.strip()}")
                else:
                    self.log.debug(
                        f"Medición enviada: {value} {self.unit} → {resp.strip()}"
                    )

            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                self.log.error(f"Conexión perdida: {e}")
                raise   # sube al bucle de run() para reconectar

            time.sleep(self.interval)

    # ── Heartbeat ─────────────────────────────────────────────

    def _schedule_ping(self):
        """Programa el próximo PING."""
        if not self._running:
            return
        self._ping_timer = threading.Timer(PING_INTERVAL, self._send_ping)
        self._ping_timer.daemon = True
        self._ping_timer.start()

    def _send_ping(self):
        """Envía PING y programa el siguiente."""
        try:
            if self._sock and self._running:
                msg = simp_message("PING", self.sensor_id,
                                   simp_timestamp(), "OK")
                self._send(msg)
                self.log.debug("PING enviado")
        except Exception as e:
            self.log.warning(f"PING falló: {e}")
        finally:
            self._schedule_ping()   # siempre reprogramar

    def _cancel_ping(self):
        if self._ping_timer:
            self._ping_timer.cancel()
            self._ping_timer = None

    # ── Utilidades de red ─────────────────────────────────────

    def _send(self, message: str):
        """Envía un mensaje SIMP al servidor."""
        with self._lock:
            if self._sock:
                self._sock.sendall(message.encode("utf-8"))

    def _recv_line(self) -> str:
        """Lee bytes del socket hasta encontrar '\\n'."""
        buf = b""
        while True:
            chunk = self._sock.recv(1)
            if not chunk:
                raise ConnectionResetError("El servidor cerró la conexión")
            buf += chunk
            if buf.endswith(b"\n"):
                return buf.decode("utf-8")

    def _cleanup_socket(self):
        """Cierra el socket de forma segura."""
        self._cancel_ping()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
