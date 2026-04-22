"""
operator_client.py — Lógica de red del cliente operador.

Responsabilidades:
  - Conectar al servidor SIMP via TCP
  - Registrarse como OPERATOR
  - Escuchar mensajes asíncronos del servidor (alertas en tiempo real)
  - Enviar consultas QUERY al servidor
  - Notificar a la GUI mediante callbacks
"""

import socket
import threading
import time
import logging
import os
from typing import Callable

log = logging.getLogger("Operator.Client")

# ─── Constantes SIMP ──────────────────────────────────────────
FIELD_SEP     = "|"
MSG_END       = "\n"
PING_INTERVAL = 25


def simp_ts() -> str:
    return str(int(time.time()))


def simp_msg(*fields) -> str:
    return FIELD_SEP.join(str(f) for f in fields) + MSG_END


class OperatorClient:
    """
    Cliente TCP para operadores del sistema SIMP.

    Callbacks que la GUI puede registrar:
      on_connected()
      on_disconnected()
      on_alert(alert_dict)
      on_sensor_list(sensors_list)
      on_status(status_dict)
      on_error(message_str)
    """

    def __init__(self, operator_id: str, token: str,
                 host: str = None, port: int = None):
        self.operator_id = operator_id
        self.token       = token
        self.host        = host or os.getenv("SIMP_SERVER_HOST",
                                             "monitor.iot-monitor.local")
        self.port        = port or int(os.getenv("SIMP_SERVER_PORT", "9000"))

        self._sock: socket.socket | None = None
        self._connected   = False
        self._running     = False
        self._lock        = threading.Lock()
        self._recv_thread: threading.Thread | None = None
        self._ping_timer:  threading.Timer  | None = None

        # Callbacks — la GUI los asigna
        self.on_connected:    Callable           | None = None
        self.on_disconnected: Callable           | None = None
        self.on_alert:        Callable[[dict], None] | None = None
        self.on_sensor_list:  Callable[[list], None] | None = None
        self.on_status:       Callable[[dict], None] | None = None
        self.on_error:        Callable[[str],  None] | None = None

    # ── Propiedad pública ─────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Conexión / Desconexión ────────────────────────────────

    def connect(self):
        """Resuelve DNS, conecta y registra. Llama on_connected si OK."""
        if self._connected:
            return

        try:
            ip = socket.gethostbyname(self.host)
            log.info(f"DNS: {self.host} → {ip}")
        except socket.gaierror as e:
            log.error(f"Fallo DNS '{self.host}': {e}")
            self._fire("on_error", f"Error DNS: {e}")
            return

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(10)
            self._sock.connect((ip, self.port))
            self._sock.settimeout(None)
            log.info(f"Conectado a {ip}:{self.port}")
        except OSError as e:
            log.error(f"Conexión fallida: {e}")
            self._fire("on_error", f"No se pudo conectar: {e}")
            return

        # Registro SIMP
        reg = simp_msg("REGISTER", self.operator_id, simp_ts(),
                       "OPERATOR", self.token)
        try:
            self._sock.sendall(reg.encode())
            resp = self._recv_line()
            log.info(f"REGISTER resp: {resp.strip()}")
            if not resp.startswith("OK"):
                self._fire("on_error", f"Registro rechazado: {resp.strip()}")
                self._close_socket()
                return
        except OSError as e:
            self._fire("on_error", f"Error en registro: {e}")
            self._close_socket()
            return

        self._connected = True
        self._running   = True

        # Hilo receptor de mensajes asíncronos
        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="OpRecv"
        )
        self._recv_thread.start()

        self._schedule_ping()
        self._fire("on_connected")

    def disconnect(self):
        """Desconexión limpia."""
        self._running = False
        self._cancel_ping()
        if self._connected and self._sock:
            try:
                bye = simp_msg("DISCONNECT", self.operator_id, simp_ts(), "BYE")
                self._sock.sendall(bye.encode())
            except Exception:
                pass
        self._close_socket()
        self._connected = False
        self._fire("on_disconnected")
        log.info("Operador desconectado.")

    # ── Consultas al servidor ─────────────────────────────────

    def query_sensors(self):
        """Solicita la lista de sensores activos."""
        self._send_query("SENSORS")

    def query_status(self):
        """Solicita el estado general del sistema."""
        self._send_query("STATUS")

    def query_alerts(self):
        """Solicita las últimas alertas."""
        self._send_query("ALERTS")

    def _send_query(self, subtype: str):
        if not self._connected:
            self._fire("on_error", "No conectado al servidor")
            return
        msg = simp_msg("QUERY", self.operator_id, simp_ts(), subtype)
        try:
            with self._lock:
                self._sock.sendall(msg.encode())
        except OSError as e:
            log.error(f"Error enviando QUERY {subtype}: {e}")
            self._fire("on_error", str(e))

    # ── Bucle receptor asíncrono ──────────────────────────────

    def _recv_loop(self):
        """Escucha mensajes del servidor de forma continua."""
        buf = ""
        while self._running:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="replace")

                # Procesar todos los mensajes completos
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._dispatch(line)

            except OSError:
                if self._running:
                    log.error("Conexión perdida con el servidor")
                break

        self._connected = False
        self._fire("on_disconnected")

    def _dispatch(self, line: str):
        """Clasifica y despacha un mensaje recibido del servidor."""
        parts = line.split(FIELD_SEP)
        if not parts:
            return

        msg_type = parts[0]
        log.debug(f"← {line}")

        if msg_type == "ALERT":
            # ALERT|SERVER|ts|sensor_id|tipo|valor|descripcion
            if len(parts) >= 7:
                alert = {
                    "timestamp":   parts[2],
                    "sensor_id":   parts[3],
                    "type":        parts[4],
                    "value":       parts[5],
                    "description": parts[6],
                }
                self._fire("on_alert", alert)

        elif msg_type == "SENSOR_LIST":
            # SENSOR_LIST|SERVER|ts|n|id:tipo:valor:unit;...
            sensors = []
            if len(parts) >= 5:
                records = parts[4].rstrip(";").split(";")
                for rec in records:
                    if rec:
                        fields = rec.split(":")
                        if len(fields) >= 4:
                            sensors.append({
                                "id":    fields[0],
                                "type":  fields[1],
                                "value": fields[2],
                                "unit":  fields[3],
                            })
            self._fire("on_sensor_list", sensors)

        elif msg_type == "STATUS_INFO":
            # STATUS_INFO|SERVER|ts|sensores:N|operadores:M|alertas:K|uptime:S
            status = {}
            for p in parts[3:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    status[k] = v
            self._fire("on_status", status)

        elif msg_type == "ALERTS":
            # ALERTS|SERVER|ts|id:tipo:valor:desc;...
            alerts = []
            if len(parts) >= 4:
                records = parts[3].rstrip(";").split(";")
                for rec in records:
                    if rec:
                        f = rec.split(":", 3)
                        if len(f) >= 4:
                            alerts.append({
                                "sensor_id": f[0],
                                "type":      f[1],
                                "value":     f[2],
                                "description": f[3],
                            })
            for alert in alerts:                
                self._fire("on_alert", alert)   # reutiliza el mismo callback

        elif msg_type == "PONG":
            log.debug("PONG recibido")

        elif msg_type == "OK":
            log.info(f"OK del servidor: {parts[-1] if len(parts) > 3 else ''}")

        elif msg_type == "ERROR":
            code = parts[3] if len(parts) > 3 else "?"
            desc = parts[4] if len(parts) > 4 else line
            log.warning(f"ERROR {code}: {desc}")
            self._fire("on_error", f"[{code}] {desc}")

    # ── Heartbeat ─────────────────────────────────────────────

    def _schedule_ping(self):
        if not self._running:
            return
        self._ping_timer = threading.Timer(PING_INTERVAL, self._do_ping)
        self._ping_timer.daemon = True
        self._ping_timer.start()

    def _do_ping(self):
        if self._connected and self._running:
            try:
                msg = simp_msg("PING", self.operator_id, simp_ts(), "OK")
                with self._lock:
                    self._sock.sendall(msg.encode())
                log.debug("PING enviado")
            except Exception:
                pass
        self._schedule_ping()

    def _cancel_ping(self):
        if self._ping_timer:
            self._ping_timer.cancel()
            self._ping_timer = None

    # ── Utilidades ────────────────────────────────────────────

    def _recv_line(self) -> str:
        buf = b""
        while True:
            ch = self._sock.recv(1)
            if not ch:
                raise ConnectionResetError("Servidor cerró conexión")
            buf += ch
            if buf.endswith(b"\n"):
                return buf.decode("utf-8")

    def _close_socket(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _fire(self, event: str, *args):
        """Llama al callback registrado de forma segura."""
        cb = getattr(self, event, None)
        if callable(cb):
            try:
                cb(*args)
            except Exception as e:
                log.error(f"Error en callback {event}: {e}")
