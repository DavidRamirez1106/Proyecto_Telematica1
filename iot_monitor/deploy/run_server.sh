#!/bin/bash
# run_server.sh — Arranca el servidor SIMP y el auth service en EC2
#
# Uso:
#   chmod +x run_server.sh
#   bash run_server.sh              # primer plano (para pruebas)
#   bash run_server.sh --daemon     # segundo plano (para producción)
#   bash run_server.sh --stop       # detiene todos los procesos

set -e

# ── Cargar variables de entorno ───────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo "[env] Cargando $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
fi

# ── Valores por defecto ───────────────────────────────────────
SIMP_PORT="${SIMP_SERVER_PORT:-9000}"
HTTP_PORT="${HTTP_SERVER_PORT:-9001}"
AUTH_PORT="${AUTH_BIND_PORT:-9002}"
LOG_DIR="${IOT_LOG_DIR:-$PROJECT_DIR/logs}"
LOG_FILE="$LOG_DIR/server_$(date +%Y%m%d_%H%M%S).log"
SERVER_BIN="$PROJECT_DIR/server/server"
AUTH_SCRIPT="$PROJECT_DIR/auth_service/auth_server.py"

DAEMON=false
STOP=false

# ── Parsear argumentos ────────────────────────────────────────
for arg in "$@"; do
    case $arg in
        --daemon) DAEMON=true ;;
        --stop)   STOP=true   ;;
    esac
done

# ── Función STOP ──────────────────────────────────────────────
if [ "$STOP" = true ]; then
    echo "Deteniendo servicios SIMP..."
    pkill -f "server $SIMP_PORT" 2>/dev/null && echo "  Servidor SIMP detenido" || echo "  (no estaba corriendo)"
    pkill -f "auth_server.py"    2>/dev/null && echo "  Auth service detenido"  || echo "  (no estaba corriendo)"
    exit 0
fi

# ── Verificaciones previas ────────────────────────────────────
echo "=================================================="
echo "  SIMP Monitor — Iniciando servicios"
echo "=================================================="

if [ ! -f "$SERVER_BIN" ]; then
    echo "[ERROR] Binario no encontrado: $SERVER_BIN"
    echo "        Compila primero con: cd server && make"
    exit 1
fi

if [ ! -f "$AUTH_SCRIPT" ]; then
    echo "[ERROR] Auth service no encontrado: $AUTH_SCRIPT"
    exit 1
fi

mkdir -p "$LOG_DIR"

echo "  Puerto SIMP:    $SIMP_PORT"
echo "  Puerto HTTP:    $HTTP_PORT"
echo "  Puerto Auth:    $AUTH_PORT"
echo "  Log:            $LOG_FILE"
echo ""

# ── Iniciar auth service ──────────────────────────────────────
echo "[1/2] Iniciando auth service (puerto $AUTH_PORT)..."

if [ "$DAEMON" = true ]; then
    AUTH_HOST="${AUTH_BIND_HOST:-0.0.0.0}"
    python3 "$AUTH_SCRIPT" \
        --host "$AUTH_HOST" \
        --port "$AUTH_PORT" \
        >> "$LOG_DIR/auth.log" 2>&1 &
    AUTH_PID=$!
    echo "  PID auth service: $AUTH_PID"
    sleep 1

    # Verificar que arrancó
    if ! kill -0 "$AUTH_PID" 2>/dev/null; then
        echo "[ERROR] Auth service no arrancó. Revisa $LOG_DIR/auth.log"
        exit 1
    fi
else
    # Primer plano: auth en background para este script
    python3 "$AUTH_SCRIPT" \
        --host "0.0.0.0" \
        --port "$AUTH_PORT" &
    AUTH_PID=$!
    sleep 1
fi

# ── Iniciar servidor SIMP ─────────────────────────────────────
echo "[2/2] Iniciando servidor SIMP (puerto $SIMP_PORT)..."

if [ "$DAEMON" = true ]; then
    "$SERVER_BIN" "$SIMP_PORT" "$LOG_FILE" >> "$LOG_DIR/server_stdout.log" 2>&1 &
    SERVER_PID=$!
    echo "  PID servidor SIMP: $SERVER_PID"

    # Guardar PIDs para poder detenerlos
    echo "$SERVER_PID" > "$LOG_DIR/server.pid"
    echo "$AUTH_PID"   > "$LOG_DIR/auth.pid"

    echo ""
    echo "  Servicios iniciados en segundo plano."
    echo "  Para detener: bash deploy/run_server.sh --stop"
    echo "  Logs:         tail -f $LOG_FILE"
else
    echo ""
    echo "  Modo interactivo. Presiona Ctrl+C para detener todo."
    echo "  Logs del servidor en consola:"
    echo "=================================================="

    # Trap para limpiar auth service al salir
    trap "echo ''; echo 'Deteniendo...'; kill $AUTH_PID 2>/dev/null; exit 0" INT TERM

    # Servidor en primer plano
    "$SERVER_BIN" "$SIMP_PORT" "$LOG_FILE"
fi
