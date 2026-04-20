#!/bin/bash
# compile_and_run.sh — Compila y ejecuta el cliente de sensores Java
#
# Requisito: Java 17+ instalado
#   Ubuntu: sudo apt install default-jdk
#   Amazon Linux: sudo yum install java-17-amazon-corretto
#
# Uso:
#   bash compile_and_run.sh                          # compilar y ejecutar
#   bash compile_and_run.sh --compile-only           # solo compilar
#   bash compile_and_run.sh --host localhost --port 9000

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src/main/java"
OUT_DIR="$SCRIPT_DIR/out"
MAIN_CLASS="iot.Main"

COMPILE_ONLY=false
HOST="${SIMP_SERVER_HOST:-monitor.iot-monitor.local}"
PORT="${SIMP_SERVER_PORT:-9000}"

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --compile-only) COMPILE_ONLY=true ;;
        --host) HOST="$2"; shift ;;
        --port) PORT="$2"; shift ;;
    esac
    shift
done

# Verificar Java
if ! command -v javac &> /dev/null; then
    echo "[ERROR] javac no encontrado. Instala Java 17+:"
    echo "  Ubuntu:       sudo apt install default-jdk"
    echo "  Amazon Linux: sudo yum install java-17-amazon-corretto"
    exit 1
fi

JAVA_VER=$(java -version 2>&1 | head -1)
echo "Java: $JAVA_VER"

# Compilar
echo "Compilando fuentes Java..."
mkdir -p "$OUT_DIR"
find "$SRC_DIR" -name "*.java" | xargs javac -d "$OUT_DIR" --release 17
echo "Compilación exitosa. Clases en: $OUT_DIR"

if [ "$COMPILE_ONLY" = true ]; then
    echo "Modo --compile-only. Listo."
    exit 0
fi

# Ejecutar
echo ""
echo "Iniciando sensores Java → $HOST:$PORT"
echo "Ctrl+C para detener."
echo ""

cd "$OUT_DIR"
SIMP_SERVER_HOST="$HOST" \
SIMP_SERVER_PORT="$PORT" \
java "$MAIN_CLASS"
