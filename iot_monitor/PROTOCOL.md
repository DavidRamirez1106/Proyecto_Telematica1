# SIMP — Sensor IoT Monitoring Protocol

**Versión:** 1.0  
**Capa:** Aplicación (sobre TCP/IP)  
**Formato:** Texto plano (ASCII), basado en líneas  
**Puerto por defecto:** 9000 (servidor de monitoreo), 9001 (HTTP), 9002 (auth service)

---

## 1. Visión general

SIMP es un protocolo de capa de aplicación basado en texto diseñado para la
comunicación entre sensores IoT, operadores humanos y un servidor central de
monitoreo. Cada mensaje es una línea de texto terminada en `\n`. Los campos
dentro de un mensaje se separan con el carácter `|`.

El protocolo es **orientado a conexión** y utiliza **TCP** (SOCK_STREAM) para
garantizar entrega ordenada y confiable de los mensajes. Esto es crítico porque:

- Las mediciones de sensores no deben perderse ni reordenarse.
- Las alertas a operadores deben llegar con certeza.
- La autenticación requiere intercambio confiable de credenciales.

---

## 2. Formato general del mensaje

```
TIPO|SENDER_ID|TIMESTAMP|PAYLOAD\n
```

| Campo       | Descripción                                              | Ejemplo             |
|-------------|----------------------------------------------------------|---------------------|
| TIPO        | Identificador del tipo de mensaje (ver sección 3)        | `REGISTER`          |
| SENDER_ID   | Identificador único del cliente (sensor o operador)      | `sensor_temp_01`    |
| TIMESTAMP   | Epoch Unix en segundos (entero)                          | `1713500000`        |
| PAYLOAD     | Datos específicos del mensaje (formato depende del tipo) | `TEMP|23.5|Celsius` |

Todos los mensajes terminan con `\n` (newline).  
Los campos no pueden contener el carácter `|`.  
El TIMESTAMP es generado por el cliente que envía el mensaje.

---

## 3. Tipos de mensajes

### 3.1 Mensajes de cliente → servidor

#### REGISTER — Registro de cliente

Enviado por sensores y operadores al conectarse. El servidor valida el rol
consultando el servicio de autenticación.

```
REGISTER|<id>|<timestamp>|<rol>|<secret>\n
```

- `rol`: `SENSOR` u `OPERATOR`
- `secret`: token de autenticación (validado contra el auth service)

**Ejemplo:**
```
REGISTER|sensor_temp_01|1713500000|SENSOR|tok_abc123\n
REGISTER|operator_juan|1713500001|OPERATOR|tok_xyz789\n
```

---

#### DATA — Envío de medición (solo sensores)

Enviado periódicamente por cada sensor con su medición actual.

```
DATA|<sensor_id>|<timestamp>|<tipo_sensor>|<valor>|<unidad>\n
```

- `tipo_sensor`: `TEMPERATURE`, `HUMIDITY`, `PRESSURE`, `VIBRATION`, `ENERGY`
- `valor`: número decimal con punto como separador
- `unidad`: unidad de medida del valor

**Ejemplos:**
```
DATA|sensor_temp_01|1713500010|TEMPERATURE|23.5|Celsius\n
DATA|sensor_hum_01|1713500010|HUMIDITY|65.2|Percent\n
DATA|sensor_pres_01|1713500010|PRESSURE|1013.2|hPa\n
DATA|sensor_vib_01|1713500010|VIBRATION|0.03|g\n
DATA|sensor_ener_01|1713500010|ENERGY|4.7|kWh\n
```

---

#### QUERY — Consulta de estado (solo operadores)

Permite a los operadores solicitar información al servidor.

```
QUERY|<operator_id>|<timestamp>|<subtipo>\n
```

- `subtipo`: `STATUS` (estado general), `SENSORS` (lista de sensores activos), `ALERTS` (alertas recientes)

**Ejemplos:**
```
QUERY|operator_juan|1713500020|STATUS\n
QUERY|operator_juan|1713500025|SENSORS\n
QUERY|operator_juan|1713500030|ALERTS\n
```

---

#### PING — Heartbeat de conexión

Enviado por cualquier cliente para mantener la conexión activa.

```
PING|<id>|<timestamp>|OK\n
```

**Ejemplo:**
```
PING|sensor_temp_01|1713500060|OK\n
```

---

#### DISCONNECT — Desconexión voluntaria

Enviado por cualquier cliente antes de cerrar la conexión.

```
DISCONNECT|<id>|<timestamp>|BYE\n
```

**Ejemplo:**
```
DISCONNECT|sensor_temp_01|1713500999|BYE\n
```

---

### 3.2 Mensajes de servidor → cliente

#### OK — Confirmación exitosa

```
OK|SERVER|<timestamp>|<mensaje_descriptivo>\n
```

**Ejemplos:**
```
OK|SERVER|1713500001|Registro exitoso. Bienvenido sensor_temp_01\n
OK|SERVER|1713500011|Medicion recibida correctamente\n
```

---

#### ERROR — Error en la operación

```
ERROR|SERVER|<timestamp>|<codigo>|<descripcion>\n
```

| Código | Descripción                        |
|--------|------------------------------------|
| E001   | Formato de mensaje inválido        |
| E002   | Tipo de mensaje desconocido        |
| E003   | Autenticación fallida              |
| E004   | Permiso denegado (rol incorrecto)  |
| E005   | Sensor no registrado               |
| E006   | Operador no registrado             |
| E007   | Servicio de auth no disponible     |

**Ejemplos:**
```
ERROR|SERVER|1713500001|E003|Autenticacion fallida: token invalido\n
ERROR|SERVER|1713500002|E001|Formato invalido: se esperaban 5 campos\n
```

---

#### ALERT — Notificación de anomalía (servidor → operadores)

Enviado por el servidor a todos los operadores conectados cuando detecta una
medición fuera del rango normal.

```
ALERT|SERVER|<timestamp>|<sensor_id>|<tipo>|<valor>|<descripcion>\n
```

**Ejemplo:**
```
ALERT|SERVER|1713500050|sensor_temp_01|TEMPERATURE|95.3|CRITICO: temperatura supera umbral maximo (90 C)\n
```

---

#### SENSOR_LIST — Respuesta a QUERY SENSORS

```
SENSOR_LIST|SERVER|<timestamp>|<n>|<id1>:<tipo1>:<valor1>:<unidad1>;<id2>:<tipo2>:<valor2>:<unidad2>;...\n
```

**Ejemplo:**
```
SENSOR_LIST|SERVER|1713500025|3|sensor_temp_01:TEMPERATURE:23.5:Celsius;sensor_hum_01:HUMIDITY:65.2:Percent;sensor_vib_01:VIBRATION:0.03:g\n
```

---

#### STATUS_INFO — Respuesta a QUERY STATUS

```
STATUS_INFO|SERVER|<timestamp>|sensores:<n>|operadores:<m>|alertas:<k>|uptime:<segundos>\n
```

**Ejemplo:**
```
STATUS_INFO|SERVER|1713500020|sensores:5|operadores:2|alertas:3|uptime:3600\n
```

---

#### PONG — Respuesta a PING

```
PONG|SERVER|<timestamp>|OK\n
```

---

## 4. Flujo de sesión típica

### Flujo de un sensor

```
Cliente (sensor)                    Servidor
     |                                 |
     |--- REGISTER|...|SENSOR|token -->|  (1) Registro
     |<-- OK|SERVER|...|Bienvenido ----|  (2) Confirmación
     |                                 |
     |--- DATA|...|TEMPERATURE|23.5 -->|  (3) Medición periódica
     |<-- OK|SERVER|...|Recibido ------|  (4) ACK
     |         (repite cada N seg)     |
     |--- PING|...|OK ---------------->|  (5) Heartbeat
     |<-- PONG|SERVER|...|OK ----------|  (6) Respuesta
     |                                 |
     |--- DISCONNECT|...|BYE --------->|  (7) Desconexión
     |         (cierra socket)         |
```

### Flujo de un operador

```
Cliente (operador)                  Servidor
     |                                 |
     |--- REGISTER|...|OPERATOR|tok -->|  (1) Registro
     |<-- OK|SERVER|...|Bienvenido ----|  (2) Confirmación
     |                                 |
     |--- QUERY|...|SENSORS ---------->|  (3) Consulta sensores
     |<-- SENSOR_LIST|SERVER|...|... --|  (4) Lista de sensores
     |                                 |
     |<-- ALERT|SERVER|...|TEMP|95.3 --|  (5) Alerta asíncrona
     |                                 |
     |--- QUERY|...|STATUS ----------->|  (6) Consulta estado
     |<-- STATUS_INFO|SERVER|...|... --|  (7) Estado del sistema
```

---

## 5. Umbrales de alerta

El servidor genera una alerta `ALERT` cuando una medición supera los siguientes umbrales:

| Tipo de sensor | Umbral mínimo | Umbral máximo | Unidad  |
|----------------|---------------|---------------|---------|
| TEMPERATURE    | -10.0         | 90.0          | Celsius |
| HUMIDITY       | 0.0           | 95.0          | Percent |
| PRESSURE       | 800.0         | 1100.0        | hPa     |
| VIBRATION      | 0.0           | 2.0           | g       |
| ENERGY         | 0.0           | 50.0          | kWh     |

---

## 6. Consideraciones de error y robustez

- Si un mensaje llega malformado, el servidor responde `ERROR|...|E001|...` y mantiene la conexión.
- Si el cliente no envía `PING` en más de 60 segundos, el servidor puede cerrar la conexión.
- Si el servicio de autenticación no está disponible, el servidor responde `ERROR|...|E007|...`.
- El servidor nunca termina su ejecución por errores de un cliente individual.
- La resolución DNS debe hacerse antes de intentar la conexión; si falla, el cliente reintenta.

---

## 7. Ejemplo completo de sesión

```
# Sensor se conecta y envía datos
C→S: REGISTER|sensor_temp_01|1713500000|SENSOR|tok_abc123\n
S→C: OK|SERVER|1713500000|Registro exitoso. Bienvenido sensor_temp_01\n
C→S: DATA|sensor_temp_01|1713500010|TEMPERATURE|23.5|Celsius\n
S→C: OK|SERVER|1713500010|Medicion recibida correctamente\n
C→S: DATA|sensor_temp_01|1713500020|TEMPERATURE|95.3|Celsius\n
S→C: OK|SERVER|1713500020|Medicion recibida correctamente\n
# El servidor detecta anomalía y notifica a todos los operadores:
S→Ops: ALERT|SERVER|1713500020|sensor_temp_01|TEMPERATURE|95.3|CRITICO: temperatura supera umbral maximo (90 C)\n
C→S: PING|sensor_temp_01|1713500060|OK\n
S→C: PONG|SERVER|1713500060|OK\n
C→S: DISCONNECT|sensor_temp_01|1713500999|BYE\n
```
