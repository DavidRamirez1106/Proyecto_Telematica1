# SIMP Monitor — Sistema Distribuido de Monitoreo IoT

**INTEGRANTES**: Juan José Baron Osorio, Diego Mesa Ospina, David Alejandro Ramirez
**Protocolo:** SIMP v1.0 (Sensor IoT Monitoring Protocol)  
**Curso:** Internet: Arquitectura y Protocolos  
**Despliegue:** AWS EC2 + Route 53

---

## Inicio rápido

### Requisitos

| Componente | Requisito |
|---|---|
| Servidor C++ | g++ 17+, make, POSIX (Linux / EC2) |
| Sensores Python | Python 3.10+ |
| Sensores Java | Java 17+ (JDK) |
| Operador GUI | Python 3.10+, tkinter |
| Auth service | Python 3.10+ (solo stdlib) |

### 1 — Compilar el servidor

```bash
cd server/
make
```

### 2 — Configurar variables de entorno

```bash
cp deploy/.env.example .env
# Editar .env con tus hostnames DNS y tokens
```

### 3 — Iniciar auth service

```bash
python3 auth_service/auth_server.py --port 9002
```

### 4 — Iniciar servidor SIMP

```bash
mkdir -p logs
./server/server 9000 logs/server.log
```

### 5 — Lanzar sensores Python

```bash
cd sensors/
SIMP_SERVER_HOST=localhost python3 run_sensors.py
```

### 6 — Lanzar sensores Java

```bash
cd sensor_java/
bash compile_and_run.sh --host localhost --port 9000
```

### 7 — Dashboard del operador

```bash
cd operator/
SIMP_SERVER_HOST=localhost python3 dashboard.py
```

### 8 — Interfaz web

Abrir: `http://localhost:9001`  
Login: `operator_01` / `tok_op_001`

---

## Estructura del proyecto

```
iot-monitor/
├── server/          → Servidor central C++
├── sensors/         → Sensores Python (5 tipos)
├── sensor_java/     → Sensores Java (2° lenguaje)
├── operator/        → Dashboard operador (tkinter)
├── auth_service/    → Auth service externo
├── web/             → Interfaz web HTML/CSS/JS
├── deploy/          → Scripts AWS
└── docs/            → PROTOCOL.md · AWS_DEPLOYMENT.md · ENTREGA.md
```

---

## Despliegue en AWS

Ver [`docs/AWS_DEPLOYMENT.md`](docs/AWS_DEPLOYMENT.md) para la guía completa.

---

## Documentación

| Documento | Contenido |
|---|---|
| `docs/PROTOCOL.md` | Especificación completa del protocolo SIMP v1.0 |
| `docs/AWS_DEPLOYMENT.md` | Guía paso a paso de despliegue en AWS |
| `docs/ENTREGA.md` | Requisitos, arquitectura, checklist de entrega |
