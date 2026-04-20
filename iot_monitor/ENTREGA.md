# Proyecto I — Sistema Distribuido de Monitoreo de Sensores IoT
## Internet: Arquitectura y Protocolos

---

## 1. Enlace al repositorio

```
https://github.com/<usuario>/<repositorio-privado>
```
> Reemplazar con el enlace real antes de entregar.  
> El repositorio debe ser **privado** y compartido con el docente.

---

## 2. Integrantes del equipo

| Nombre completo | Código |
|-----------------|--------|
|                 |        |
|                 |        |
|                 |        |

---

## 3. Descripción general del sistema

El sistema **SIMP Monitor** (Sensor IoT Monitoring Protocol) es una plataforma
distribuida de monitoreo industrial desplegada en AWS que simula el funcionamiento
de un sistema real tipo SIATA. Permite que múltiples sensores IoT reporten
mediciones a un servidor central, mientras operadores humanos supervisan el estado
del sistema en tiempo real y reciben alertas automáticas ante anomalías.

### Entidades del sistema

| Entidad | Implementación | Función |
|---------|---------------|---------|
| Sensores IoT | Python + Java | Envían mediciones periódicas al servidor vía TCP |
| Operadores | Python (tkinter) | Visualizan sensores y reciben alertas en tiempo real |
| Servidor central | C++ (Berkeley Sockets) | Recibe datos, detecta anomalías, notifica operadores |
| Auth service | Python (http.server) | Valida credenciales — los usuarios NO se almacenan en el servidor |
| Interfaz web | HTML/CSS/JS | Dashboard accesible desde el navegador |
| DNS | AWS Route 53 | Resolución de nombres — sin IPs hardcodeadas en el código |

---

## 4. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENTES (tu máquina)                     │
│                                                             │
│  sensors/run_sensors.py     operator/dashboard.py           │
│  sensor_java/Main.java      Navegador web                   │
│        │ TCP:9000                │ TCP:9000    │ HTTP:9001   │
└────────┼────────────────────────┼─────────────┼─────────────┘
         │                        │             │
         │       INTERNET         │             │
         │                        │             │
┌────────▼────────────────────────▼─────────────▼─────────────┐
│              AWS EC2 — Ubuntu 22.04                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  server/server  (C++)   Puerto 9000 SIMP             │   │
│  │                         Puerto 9001 HTTP             │   │
│  │  ┌─────────────────┐  ┌──────────────────────────┐  │   │
│  │  │  Manejador TCP  │  │  Servidor HTTP básico    │  │   │
│  │  │  Multi-hilo     │  │  GET /api/status         │  │   │
│  │  │  Berkeley Sock  │  │  GET /api/sensors        │  │   │
│  │  │  Protocolo SIMP │  │  GET /api/alerts         │  │   │
│  │  │  Logger (IP+msg)│  │  POST /api/login (proxy) │  │   │
│  │  └────────┬────────┘  └──────────────────────────┘  │   │
│  └───────────┼──────────────────────────────────────────┘   │
│              │ HTTP JSON                                     │
│  ┌───────────▼──────────────────────────────────────────┐   │
│  │  auth_service/auth_server.py   Puerto 9002           │   │
│  │  POST /validate  POST /login  GET /health            │   │
│  │  users.json  (usuarios y roles externos)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  Route 53:  monitor.iot-monitor.local → IP pública EC2     │
│             auth.iot-monitor.local    → IP pública EC2     │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Protocolo de aplicación — SIMP v1.0

### Justificación de diseño

**¿Por qué TCP (SOCK_STREAM)?**

Se eligió TCP para toda la comunicación porque:
- Las mediciones de sensores no deben perderse ni reordenarse (fiabilidad)
- Las alertas a operadores deben garantizarse (un alerta perdido puede ser crítico)
- El handshake de autenticación requiere intercambio confiable

**¿Por qué basado en texto?**

El enunciado lo exige. Además facilita el debugging (se puede leer con `telnet`)
y la implementación en múltiples lenguajes (Python, Java, C++) sin problemas
de serialización binaria.

### Formato del mensaje

```
TIPO|SENDER_ID|TIMESTAMP|PAYLOAD\n
```

- Separador de campos: `|`
- Terminador: `\n`  
- Codificación: UTF-8  
- Longitud máxima: 4096 bytes

### Tabla de mensajes

| Mensaje | Dirección | Formato | Ejemplo |
|---------|-----------|---------|---------|
| `REGISTER` | Cliente→Srv | `REGISTER\|id\|ts\|rol\|token` | `REGISTER\|sensor_temp_01\|1713500000\|SENSOR\|tok_temp_001` |
| `DATA` | Sensor→Srv | `DATA\|id\|ts\|tipo\|valor\|unidad` | `DATA\|sensor_temp_01\|1713500010\|TEMPERATURE\|23.5\|Celsius` |
| `QUERY` | Operador→Srv | `QUERY\|id\|ts\|subtipo` | `QUERY\|operator_01\|1713500020\|SENSORS` |
| `PING` | Cliente→Srv | `PING\|id\|ts\|OK` | `PING\|sensor_temp_01\|1713500060\|OK` |
| `DISCONNECT` | Cliente→Srv | `DISCONNECT\|id\|ts\|BYE` | `DISCONNECT\|sensor_temp_01\|1713500999\|BYE` |
| `OK` | Srv→Cliente | `OK\|SERVER\|ts\|descripción` | `OK\|SERVER\|1713500001\|Registro exitoso` |
| `ERROR` | Srv→Cliente | `ERROR\|SERVER\|ts\|código\|descripción` | `ERROR\|SERVER\|1713500001\|E003\|Token inválido` |
| `ALERT` | Srv→Operador | `ALERT\|SERVER\|ts\|sensor_id\|tipo\|valor\|descripción` | `ALERT\|SERVER\|1713500050\|sensor_temp_01\|TEMPERATURE\|95.3\|CRITICO...` |
| `SENSOR_LIST` | Srv→Operador | `SENSOR_LIST\|SERVER\|ts\|n\|id:tipo:valor:unit;...` | — |
| `STATUS_INFO` | Srv→Operador | `STATUS_INFO\|SERVER\|ts\|sensores:N\|operadores:M\|alertas:K\|uptime:S` | — |
| `PONG` | Srv→Cliente | `PONG\|SERVER\|ts\|OK` | — |

### Umbrales de alerta

| Sensor | Mínimo | Máximo | Unidad |
|--------|--------|--------|--------|
| TEMPERATURE | -10.0 | 90.0 | Celsius |
| HUMIDITY | 0.0 | 95.0 | Percent |
| PRESSURE | 800.0 | 1100.0 | hPa |
| VIBRATION | 0.0 | 2.0 | g |
| ENERGY | 0.0 | 50.0 | kWh |

### Flujo de sesión completo

```
Sensor                          Servidor                    Operador
  │                                │                            │
  │── REGISTER|...|SENSOR|token ──►│                            │
  │◄── OK|SERVER|...|Bienvenido ───│                            │
  │                                │◄── REGISTER|...|OPERATOR ──│
  │                                │─── OK|SERVER|...|Bienvenido►│
  │                                │                            │
  │── DATA|...|TEMPERATURE|23.5 ──►│                            │
  │◄── OK|SERVER|...|Recibido ─────│                            │
  │                                │                            │
  │── DATA|...|TEMPERATURE|95.3 ──►│                            │
  │◄── OK|SERVER|...|Recibido ─────│                            │
  │                                │── ALERT|...|TEMPERATURE ──►│
  │                                │     (valor fuera de rango)  │
  │                                │                            │
  │── PING|...|OK ────────────────►│                            │
  │◄── PONG|SERVER|...|OK ─────────│                            │
  │                                │◄── QUERY|...|SENSORS ──────│
  │                                │─── SENSOR_LIST|... ───────►│
  │                                │                            │
  │── DISCONNECT|...|BYE ─────────►│                            │
```

---

## 6. Estructura de archivos del proyecto

```
iot-monitor/
│
├── server/                        ← SERVIDOR CENTRAL (C++)
│   ├── server.cpp                 Programa principal: sockets, hilos, protocolo
│   ├── protocol.h                 Constantes, structs y funciones del protocolo SIMP
│   ├── logger.h / logger.cpp      Sistema de logs thread-safe (consola + archivo)
│   ├── http_server.h / .cpp       Servidor HTTP básico: GET, cabeceras, códigos
│   └── Makefile                   Compilación con g++ -std=c++17 -pthread
│
├── sensors/                       ← CLIENTES SENSORES (Python)
│   ├── sensor_client.py           Clase base abstracta: TCP, SIMP, reconexión, heartbeat
│   ├── sensor_types.py            5 sensores: temperatura, humedad, presión, vibración, energía
│   └── run_sensors.py             Lanza los 5 sensores en hilos simultáneos
│
├── sensor_java/                   ← CLIENTES SENSORES (Java) — segundo lenguaje
│   ├── src/main/java/iot/
│   │   ├── SimpProtocol.java      Protocolo SIMP en Java (constantes, parser, constructores)
│   │   ├── SensorBase.java        Clase base abstracta: TCP, SIMP, reconexión
│   │   ├── SensorTypes.java       5 sensores (mismos tipos que Python)
│   │   └── Main.java              Punto de entrada: ExecutorService + shutdown hook
│   └── compile_and_run.sh         Compila y ejecuta con un solo comando
│
├── operator/                      ← CLIENTE OPERADOR (Python + tkinter)
│   ├── operator_client.py         Lógica de red: TCP, parsing SIMP, callbacks asíncronos
│   └── dashboard.py               GUI: tabla sensores, panel alertas, tarjetas de estado
│
├── auth_service/                  ← SERVICIO DE AUTENTICACIÓN EXTERNO (Python)
│   ├── auth_server.py             HTTP API: POST /validate, POST /login, GET /health
│   └── users.json                 Usuarios y roles (NO almacenados en el servidor principal)
│
├── web/                           ← INTERFAZ WEB (HTML/CSS/JS)
│   ├── index.html                 Login + dashboard: métricas, tabla sensores, alertas
│   └── style.css                  Tema oscuro, responsive, sin frameworks externos
│
├── deploy/                        ← DESPLIEGUE AWS
│   ├── setup_ec2.sh               Instala dependencias en EC2 (Ubuntu/Amazon Linux)
│   ├── run_server.sh              Arranca servidor SIMP + auth service
│   └── .env.example               Variables de entorno (puertos, tokens, DNS)
│
├── docs/
│   ├── PROTOCOL.md                Especificación completa del protocolo SIMP v1.0
│   ├── AWS_DEPLOYMENT.md          Guía paso a paso de despliegue en AWS
│   └── ENTREGA.md                 Este documento
│
├── README.md                      Instrucciones de inicio rápido
└── .gitignore                     Excluye binarios, logs, .env
```

---

## 7. Requisitos cumplidos del enunciado

### Servidor (C++) — 40%

| Requisito | Cumplido | Detalle |
|-----------|----------|---------|
| Implementado en C | ✅ | C++17, compilado con g++ |
| API de Sockets Berkeley | ✅ | `socket()`, `bind()`, `listen()`, `accept()`, `send()`, `recv()` |
| Múltiples clientes simultáneos | ✅ | Cada cliente en hilo separado con `std::thread::detach()` |
| Hilos para concurrencia | ✅ | `std::thread`, `std::mutex`, estado compartido protegido |
| Logging (IP + puerto + msg + resp) | ✅ | `Logger::log_request/log_response` en consola y archivo |
| `./server puerto archivoDeLogs` | ✅ | `./server 9000 server.log` |
| Ejecutado en EC2 | ✅ | Compilado directamente en la instancia |

### Clientes — 20%

| Requisito | Cumplido | Detalle |
|-----------|----------|---------|
| Dos lenguajes distintos | ✅ | Python (`sensors/`) y Java (`sensor_java/`) |
| Conexión al servidor | ✅ | TCP con resolución DNS |
| Construcción correcta de mensajes | ✅ | Protocolo SIMP en ambos lenguajes |
| Procesamiento de respuestas | ✅ | Parser en Python y Java |

### Funcionamiento del sistema — 20%

| Requisito | Cumplido | Detalle |
|-----------|----------|---------|
| Al menos 5 sensores simulados | ✅ | TEMPERATURE, HUMIDITY, PRESSURE, VIBRATION, ENERGY |
| Envío periódico de mediciones | ✅ | Intervalos configurables (3s a 10s según sensor) |
| Alertas en tiempo real | ✅ | Broadcast a todos los operadores conectados |
| Interfaz gráfica operador | ✅ | tkinter con tabla, alertas y métricas |
| Servidor HTTP básico | ✅ | GET, cabeceras HTTP, códigos de estado correctos |
| Servicio de autenticación externo | ✅ | Auth service independiente, usuarios no en servidor principal |
| Sin IPs hardcodeadas | ✅ | `getaddrinfo()` en C++, `gethostbyname()` en Python, `InetAddress.getByName()` en Java |
| Manejo de errores de red | ✅ | Reconexión automática, servidor no termina ante errores de cliente |

### Despliegue AWS — 10%

| Requisito | Cumplido | Detalle |
|-----------|----------|---------|
| Instancia EC2 | ✅ | Ubuntu 22.04 t2.micro |
| Configuración de puertos | ✅ | Security Group: 9000, 9001, 9002 |
| DNS Route 53 | ✅ | `monitor.iot-monitor.local`, `auth.iot-monitor.local` |
| Acceso desde Internet | ✅ | IP pública + Security Group abierto |
| Compilación en EC2 | ✅ | `make` ejecutado directamente en la instancia |

### Documentación — 10%

| Requisito | Cumplido | Detalle |
|-----------|----------|---------|
| Especificación del protocolo | ✅ | `docs/PROTOCOL.md` — formato, mensajes, flujos, umbrales |
| Repositorio con código fuente | ✅ | GitHub privado |

---

## 8. Cómo ejecutar el sistema completo

### En AWS EC2 (servidor):

```bash
# 1. Conectar por SSH
ssh -i simp-key.pem ubuntu@<IP-EC2>

# 2. Instalar dependencias (solo la primera vez)
sudo bash ~/iot-monitor/deploy/setup_ec2.sh

# 3. Compilar (solo la primera vez o tras cambios)
cd ~/iot-monitor/server && make

# 4. Iniciar auth service (Terminal 1)
python3 ~/iot-monitor/auth_service/auth_server.py --port 9002

# 5. Iniciar servidor SIMP (Terminal 2)
cd ~/iot-monitor && mkdir -p logs
./server/server 9000 logs/server.log
```

### En tu máquina local (clientes):

```bash
export SIMP_SERVER_HOST=monitor.iot-monitor.local   # o IP pública

# Sensores Python
cd sensors/ && python3 run_sensors.py

# Sensores Java
cd sensor_java/ && bash compile_and_run.sh

# Dashboard operador
cd operator/ && python3 dashboard.py

# Interfaz web
# Abrir: http://monitor.iot-monitor.local:9001
# Login: operator_01 / tok_op_001
```
