# Guía de Despliegue en AWS — SIMP Monitor

**Curso:** Internet: Arquitectura y Protocolos  
**Objetivo:** Desplegar el servidor SIMP en una instancia EC2 con DNS via Route 53,
accesible desde Internet para clientes externos.

---

## Arquitectura desplegada en AWS

```
Internet
    │
    │  TCP :9000 (SIMP)   TCP :9001 (HTTP/Web)
    ▼
┌─────────────────────────────────────────────┐
│         AWS EC2  (Ubuntu 22.04)             │
│                                             │
│  ./server 9000 server.log   ← C++           │
│  python3 auth_server.py     ← Python        │
│                                             │
│  /opt/iot-monitor/                          │
│    server/server                            │
│    auth_service/auth_server.py              │
│    web/index.html                           │
│    logs/                                    │
└─────────────────────────────────────────────┘
    │
    │  DNS (Route 53)
    ▼
monitor.iot-monitor.local  →  <IP pública EC2>
auth.iot-monitor.local     →  <IP pública EC2>
```

---

## Parte 1 — Crear la instancia EC2

### 1.1 Acceder a la consola AWS

1. Ir a https://console.aws.amazon.com
2. Seleccionar región: `us-east-1` (N. Virginia) — capa gratuita disponible
3. Navegar a: **EC2 → Instances → Launch Instance**

### 1.2 Configurar la instancia

| Campo               | Valor recomendado                     |
|---------------------|---------------------------------------|
| Name                | `simp-monitor-server`                 |
| AMI                 | Ubuntu Server 22.04 LTS (Free Tier)   |
| Instance Type       | `t2.micro` (1 vCPU, 1 GB RAM)         |
| Key pair            | Crear nueva: `simp-key` (guardar .pem)|
| Storage             | 8 GB gp2 (suficiente)                 |

### 1.3 Configurar el Security Group

Crear un nuevo security group llamado `simp-monitor-sg` con estas reglas **de entrada**:

| Tipo         | Puerto | Protocolo | Origen      | Descripción          |
|--------------|--------|-----------|-------------|----------------------|
| SSH          | 22     | TCP       | Mi IP       | Acceso remoto        |
| Custom TCP   | 9000   | TCP       | 0.0.0.0/0  | Protocolo SIMP       |
| Custom TCP   | 9001   | TCP       | 0.0.0.0/0  | Interfaz web HTTP    |
| Custom TCP   | 9002   | TCP       | 0.0.0.0/0  | Auth service         |

> **Nota:** En producción real, el puerto 9002 solo debería ser accesible
> desde la propia instancia (source = security group), no desde Internet.
> Para este proyecto académico, abrirlo a 0.0.0.0/0 simplifica las pruebas.

### 1.4 Lanzar la instancia

1. Hacer clic en **Launch Instance**
2. Esperar ~2 minutos hasta que el estado sea `running`
3. Anotar la **IP pública** (Public IPv4 Address) — ejemplo: `54.123.45.67`

---

## Parte 2 — Configurar Route 53 (DNS)

### 2.1 Crear una zona alojada

1. AWS Console → **Route 53 → Hosted Zones → Create Hosted Zone**
2. Configurar:
   - **Domain name:** `iot-monitor.local`
   - **Type:** Public hosted zone (para acceso desde Internet)
3. Hacer clic en **Create hosted zone**

### 2.2 Crear registros DNS tipo A

Dentro de la zona `iot-monitor.local`, crear dos registros:

**Registro 1 — Servidor SIMP:**
1. **Create record**
2. Record name: `monitor`
3. Record type: `A`
4. Value: `<IP pública de la instancia EC2>`
5. TTL: `60`
6. **Create records**

**Registro 2 — Auth service:**
1. **Create record**
2. Record name: `auth`
3. Record type: `A`
4. Value: `<misma IP pública>`
5. TTL: `60`
6. **Create records**

### 2.3 Verificar la resolución DNS

Desde tu máquina local (después de unos minutos):

```bash
nslookup monitor.iot-monitor.local
# Debe responder con la IP pública de la instancia

nslookup auth.iot-monitor.local
# Debe responder con la misma IP
```

> **Importante:** Los dominios `.local` a veces interfieren con mDNS en
> macOS/Linux. Si hay problemas, usa un dominio como `iot-monitor.net`
> y registra los subdominios ahí.

---

## Parte 3 — Subir el código a EC2

### 3.1 Dar permisos correctos a la clave SSH

```bash
# En tu máquina local
chmod 400 simp-key.pem
```

### 3.2 Subir el proyecto completo

```bash
# Desde el directorio "Proyecto Telemática/"
scp -i simp-key.pem -r iot-monitor/ ubuntu@54.123.45.67:~/
```

### 3.3 Conectarse por SSH

```bash
ssh -i simp-key.pem ubuntu@54.123.45.67
```

---

## Parte 4 — Instalar dependencias en EC2

```bash
# Una vez conectado por SSH
cd ~/iot-monitor
sudo bash deploy/setup_ec2.sh
```

El script instala automáticamente: `g++`, `make`, `python3`.

Verificar instalación:

```bash
g++ --version    # debe mostrar g++ 11+
python3 --version # debe mostrar Python 3.10+
java -version    # opcional, para el cliente Java
```

---

## Parte 5 — Compilar el servidor en EC2

```bash
cd ~/iot-monitor/server
make
```

Salida esperada:

```
g++ -std=c++17 -Wall -Wextra -pthread -O2 -c server.cpp -o server.o
g++ -std=c++17 -Wall -Wextra -pthread -O2 -c logger.cpp -o logger.o
g++ -std=c++17 -Wall -Wextra -pthread -O2 -c http_server.cpp -o http_server.o
g++ -std=c++17 -Wall -Wextra -pthread -O2 -o server ...

  Compilacion exitosa: ./server
```

---

## Parte 6 — Configurar variables de entorno

```bash
cd ~/iot-monitor
cp deploy/.env.example .env
nano .env
```

Editar con los valores reales:

```bash
# .env en EC2
SIMP_SERVER_PORT=9000
HTTP_SERVER_PORT=9001
AUTH_BIND_PORT=9002
AUTH_BIND_HOST=0.0.0.0

# Hostnames DNS (Route 53)
SIMP_SERVER_HOST=monitor.iot-monitor.local
AUTH_SERVICE_HOST=auth.iot-monitor.local

# Tokens — deben coincidir con users.json
TOKEN_TEMP=tok_temp_001
TOKEN_HUM=tok_hum_001
TOKEN_PRES=tok_pres_001
TOKEN_VIB=tok_vib_001
TOKEN_ENER=tok_ener_001

OPERATOR_ID=operator_01
OPERATOR_TOKEN=tok_op_001

IOT_LOG_DIR=/opt/iot-monitor/logs
```

---

## Parte 7 — Iniciar los servicios

### Opción A — Modo interactivo (para pruebas / sustentación)

Abrir **dos terminales SSH** a la instancia:

**Terminal 1 — Auth service:**
```bash
cd ~/iot-monitor
source deploy/.env.example
python3 auth_service/auth_server.py --port 9002
```

**Terminal 2 — Servidor SIMP:**
```bash
cd ~/iot-monitor
mkdir -p logs
source .env
./server/server 9000 logs/server.log
```

### Opción B — Modo daemon (producción)

```bash
cd ~/iot-monitor
bash deploy/run_server.sh --daemon

# Ver logs en tiempo real:
tail -f logs/server_*.log
tail -f logs/auth.log
```

### Verificar que están corriendo:

```bash
ps aux | grep server
ps aux | grep auth_server
# También:
curl http://localhost:9002/health
```

---

## Parte 8 — Conectar clientes desde fuera de AWS

### Desde tu máquina local:

```bash
cd "Proyecto Telemática/iot-monitor"

# Opción 1: Usar el hostname DNS
export SIMP_SERVER_HOST=monitor.iot-monitor.local

# Opción 2: Usar la IP directa (si DNS no resuelve aún)
export SIMP_SERVER_HOST=54.123.45.67

export SIMP_SERVER_PORT=9000
```

**Lanzar sensores Python:**
```bash
cd sensors/
python3 run_sensors.py
```

**Lanzar dashboard del operador:**
```bash
cd operator/
python3 dashboard.py
```

**Lanzar sensores Java:**
```bash
cd sensor_java/
bash compile_and_run.sh --host monitor.iot-monitor.local --port 9000
```

**Abrir interfaz web:**
```
http://54.123.45.67:9001
# o
http://monitor.iot-monitor.local:9001
```
Login: `operator_01` / `tok_op_001`

---

## Parte 9 — Verificación del sistema completo

### Checklist para la sustentación:

- [ ] Instancia EC2 corriendo (`running` en consola AWS)
- [ ] Security Groups con puertos 9000, 9001, 9002 abiertos
- [ ] Registros DNS en Route 53 resolviendo correctamente
- [ ] Auth service respondiendo: `curl http://<IP>:9002/health`
- [ ] Servidor SIMP compilado y corriendo en EC2
- [ ] Al menos 3 sensores Python conectados y enviando datos
- [ ] Cliente operador con dashboard mostrando sensores en tiempo real
- [ ] Una alerta generada y visible en el dashboard
- [ ] Logs del servidor mostrando IPs, puertos y mensajes
- [ ] Interfaz web accesible desde el navegador

### Comandos útiles para la sustentación:

```bash
# Ver logs en vivo
tail -f ~/iot-monitor/logs/server_*.log

# Ver conexiones TCP activas en el servidor
ss -tnp | grep 9000

# Probar el auth service manualmente
curl -X POST http://localhost:9002/validate \
  -H "Content-Type: application/json" \
  -d '{"id":"operator_01","role":"OPERATOR","token":"tok_op_001"}'
# Respuesta esperada: {"ok": true, "name": "Juan Pérez", "role": "OPERATOR"}

# Probar la API REST del servidor
curl http://localhost:9001/api/status
curl http://localhost:9001/api/sensors
curl http://localhost:9001/api/alerts
```

---

## Solución de problemas comunes

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| `Connection refused` en puerto 9000 | Servidor no arrancó | Verificar con `ps aux | grep server` |
| DNS no resuelve | TTL pendiente o zona mal configurada | Esperar 5 min o usar IP directa |
| `Registro rechazado` al conectar sensor | Auth service caído o token incorrecto | Verificar `curl :9002/health` y `users.json` |
| Web muestra datos vacíos | CORS o API no responde | Verificar puertos en Security Group |
| `make: g++: not found` | g++ no instalado | `sudo apt install g++` |
