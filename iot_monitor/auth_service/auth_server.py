"""
auth_server.py — Servicio de autenticación externo (Flask).

El servidor C++ consulta este servicio cada vez que un cliente
intenta registrarse. Nunca almacena usuarios en el servidor principal.

Endpoints:
  POST /validate   → valida id + role + token
  POST /login      → login para la interfaz web (devuelve info del usuario)
  GET  /health     → verificación de estado del servicio

Puerto por defecto: 9002
Protocolo: HTTP/JSON

Uso:
  python3 auth_server.py
  python3 auth_server.py --port 9002 --host 0.0.0.0
"""

import json
import logging
import argparse
import os
import time
import hashlib
from functools import wraps
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  AUTH — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("auth_server")

# ─── Carga de usuarios ────────────────────────────────────────
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")


def load_users() -> dict:
    """Carga y devuelve el índice de usuarios por ID."""
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {u["id"]: u for u in data["users"]}


# Índices en memoria (se recargan sin reiniciar el servicio)
_users_by_id:    dict = {}
_users_by_token: dict = {}
_last_load:      float = 0.0
RELOAD_INTERVAL  = 30.0   # recargar users.json cada 30 segundos


def get_users() -> tuple[dict, dict]:
    """Devuelve los índices de usuarios, recargando si es necesario."""
    global _users_by_id, _users_by_token, _last_load
    if time.time() - _last_load > RELOAD_INTERVAL:
        try:
            _users_by_id = load_users()
            _users_by_token = {u["token"]: u
                               for u in _users_by_id.values()
                               if u.get("token")}
            _last_load = time.time()
            log.info(f"Usuarios recargados: {len(_users_by_id)} registros")
        except Exception as e:
            log.error(f"Error recargando users.json: {e}")
    return _users_by_id, _users_by_token


# Precargar al inicio
get_users()

# ─── Estadísticas simples ─────────────────────────────────────
stats = {
    "requests_total":  0,
    "auth_ok":         0,
    "auth_failed":     0,
    "started_at":      time.time(),
}


# ─── Handler HTTP ─────────────────────────────────────────────

class AuthHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """Reemplaza el log de BaseHTTPRequestHandler con el nuestro."""
        log.info(f"{self.client_address[0]}:{self.client_address[1]}  "
                 f"{format % args}")

    # ── Lectura del body ──────────────────────────────────────

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            log.warning(f"JSON inválido: {e}")
            return None

    # ── Envío de respuesta ────────────────────────────────────

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # ── Routing ───────────────────────────────────────────────

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        stats["requests_total"] += 1
        path = urlparse(self.path).path

        if path == "/health":
            self._handle_health()
        elif path == "/stats":
            self._handle_stats()
        else:
            self._send_json(404, {"error": "Endpoint no encontrado"})

    def do_POST(self):
        stats["requests_total"] += 1
        path = urlparse(self.path).path

        if path == "/validate":
            self._handle_validate()
        elif path == "/login":
            self._handle_login()
        else:
            self._send_json(404, {"error": "Endpoint no encontrado"})

    # ── Endpoints ─────────────────────────────────────────────

    def _handle_validate(self):
        """
        Valida las credenciales de un cliente SIMP.

        Petición (JSON):
          {"id": "sensor_temp_01", "role": "SENSOR", "token": "tok_temp_001"}

        Respuesta exitosa:
          {"ok": true, "name": "Sensor Temperatura Planta A", "role": "SENSOR"}

        Respuesta fallida:
          {"ok": false, "reason": "Token inválido"}
        """
        data = self._read_json()
        if not data:
            self._send_json(400, {"ok": False, "reason": "Body JSON requerido"})
            return

        client_id = data.get("id",    "").strip()
        role      = data.get("role",  "").strip().upper()
        token     = data.get("token", "").strip()

        if not client_id or not role or not token:
            self._send_json(400, {
                "ok": False,
                "reason": "Campos requeridos: id, role, token"
            })
            return

        users_by_id, users_by_token = get_users()

        # Buscar usuario por ID
        user = users_by_id.get(client_id)

        if not user:
            stats["auth_failed"] += 1
            log.warning(f"RECHAZADO id='{client_id}' — usuario no existe")
            self._send_json(200, {
                "ok": False,
                "reason": f"Usuario '{client_id}' no registrado"
            })
            return

        if not user.get("active", False):
            stats["auth_failed"] += 1
            log.warning(f"RECHAZADO id='{client_id}' — cuenta inactiva")
            self._send_json(200, {
                "ok": False,
                "reason": "Cuenta inactiva"
            })
            return

        if user["token"] != token:
            stats["auth_failed"] += 1
            log.warning(f"RECHAZADO id='{client_id}' — token incorrecto")
            self._send_json(200, {
                "ok": False,
                "reason": "Token inválido"
            })
            return

        if user["role"] != role:
            stats["auth_failed"] += 1
            log.warning(
                f"RECHAZADO id='{client_id}' — rol incorrecto "
                f"(esperado={user['role']}, recibido={role})"
            )
            self._send_json(200, {
                "ok": False,
                "reason": f"Rol incorrecto. Esperado: {user['role']}"
            })
            return

        # Todo OK
        stats["auth_ok"] += 1
        log.info(f"ACEPTADO  id='{client_id}' rol={role}")
        self._send_json(200, {
            "ok":   True,
            "name": user.get("name", client_id),
            "role": user["role"],
        })

    def _handle_login(self):
        """
        Login para la interfaz web.

        Petición (JSON):
          {"id": "operator_01", "token": "tok_op_001"}

        Respuesta exitosa:
          {"ok": true, "name": "Juan Pérez", "role": "OPERATOR"}
        """
        data = self._read_json()
        if not data:
            self._send_json(400, {"ok": False, "reason": "Body JSON requerido"})
            return

        client_id = data.get("id",    "").strip()
        token     = data.get("token", "").strip()

        users_by_id, _ = get_users()
        user = users_by_id.get(client_id)

        if not user or user["token"] != token or not user.get("active"):
            stats["auth_failed"] += 1
            log.warning(f"LOGIN FALLIDO para id='{client_id}'")
            self._send_json(200, {
                "ok": False,
                "reason": "Credenciales inválidas"
            })
            return

        # Solo operadores pueden hacer login en la web
        if user["role"] != "OPERATOR":
            self._send_json(200, {
                "ok": False,
                "reason": "Solo operadores pueden acceder al panel web"
            })
            return

        stats["auth_ok"] += 1
        log.info(f"LOGIN OK  id='{client_id}' nombre='{user['name']}'")
        self._send_json(200, {
            "ok":   True,
            "id":   client_id,
            "name": user["name"],
            "role": user["role"],
        })

    def _handle_health(self):
        """Health check — el servidor C++ puede consultarlo."""
        uptime = int(time.time() - stats["started_at"])
        self._send_json(200, {
            "status":  "ok",
            "service": "SIMP Auth Service",
            "version": "1.0",
            "uptime":  uptime,
            "users":   len(get_users()[0]),
        })

    def _handle_stats(self):
        """Estadísticas de autenticación."""
        uptime = int(time.time() - stats["started_at"])
        self._send_json(200, {
            **stats,
            "uptime_seconds": uptime,
            "users_loaded":   len(get_users()[0]),
        })


# ─── Entry point ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Servicio de autenticación SIMP"
    )
    parser.add_argument("--host", default=os.getenv("AUTH_BIND_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int,
                        default=int(os.getenv("AUTH_BIND_PORT", "9002")))
    args = parser.parse_args()

    log.info("=" * 50)
    log.info("  SIMP Auth Service v1.0")
    log.info(f"  Escuchando en {args.host}:{args.port}")
    log.info(f"  Usuarios cargados: {len(get_users()[0])}")
    log.info("=" * 50)

    server = HTTPServer((args.host, args.port), AuthHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Auth service detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
