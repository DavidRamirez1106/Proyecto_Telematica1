#!/bin/bash
# setup_ec2.sh — Instala todas las dependencias del proyecto en EC2 (Ubuntu 22.04 / Amazon Linux 2)
#
# Uso (como usuario ec2-user o ubuntu con sudo):
#   chmod +x setup_ec2.sh
#   sudo bash setup_ec2.sh
#
# Qué hace:
#   1. Actualiza el sistema
#   2. Instala g++, make, python3, pip
#   3. Instala dependencias Python (solo stdlib — no requiere pip externo)
#   4. Configura variables de entorno básicas

set -e   # detener ante cualquier error

echo "=================================================="
echo "  SIMP Monitor — Configuración de instancia EC2"
echo "=================================================="

# ── Detectar distribución ──────────────────────────────────────
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    DISTRO="unknown"
fi

echo "[1/5] Distribución detectada: $DISTRO"

# ── Actualizar paquetes e instalar herramientas ───────────────
if [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
    echo "[2/5] Actualizando sistema (apt)..."
    apt-get update -q
    apt-get install -y -q \
        g++ \
        make \
        python3 \
        python3-pip \
        python3-tk \
        net-tools \
        curl \
        git

elif [ "$DISTRO" = "amzn" ] || [ "$DISTRO" = "rhel" ] || [ "$DISTRO" = "centos" ]; then
    echo "[2/5] Actualizando sistema (yum)..."
    yum update -y -q
    yum install -y -q \
        gcc-c++ \
        make \
        python3 \
        python3-pip \
        net-tools \
        curl \
        git
else
    echo "[WARN] Distribución no reconocida. Instala manualmente: g++, make, python3"
fi

# ── Verificar versiones ───────────────────────────────────────
echo "[3/5] Verificando versiones instaladas..."
echo "  g++:     $(g++ --version | head -1)"
echo "  make:    $(make --version | head -1)"
echo "  python3: $(python3 --version)"

# ── Crear directorios de trabajo ──────────────────────────────
echo "[4/5] Creando estructura de directorios..."
mkdir -p /opt/iot-monitor/logs
chmod 755 /opt/iot-monitor/logs

# ── Configurar variables de entorno del sistema ───────────────
echo "[5/5] Configurando variables de entorno..."

ENV_FILE="/etc/profile.d/iot-monitor.sh"
cat > "$ENV_FILE" << 'EOF'
# Variables de entorno — SIMP Monitor
export SIMP_SERVER_PORT=9000
export AUTH_BIND_PORT=9002
export IOT_LOG_DIR=/opt/iot-monitor/logs
EOF

echo "  Variables escritas en $ENV_FILE"
echo "  Ejecuta 'source $ENV_FILE' o reinicia la sesión para aplicarlas."

echo ""
echo "=================================================="
echo "  Instalación completada."
echo ""
echo "  Próximos pasos:"
echo "  1. Sube el código:  scp -r iot-monitor/ ec2-user@<IP>:~/"
echo "  2. Compila:         cd ~/iot-monitor/server && make"
echo "  3. Configura DNS:   edita .env con tu dominio Route 53"
echo "  4. Inicia:          bash deploy/run_server.sh"
echo "=================================================="
