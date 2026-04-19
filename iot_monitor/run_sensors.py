"""
run_sensors.py — Lanza todos los sensores IoT simulados simultáneamente.

Uso:
    python3 run_sensors.py                          # usa variables de entorno
    SIMP_SERVER_HOST=monitor.local python3 run_sensors.py
    python3 run_sensors.py --host 54.123.45.67 --port 9000

Detener: Ctrl+C  (hace DISCONNECT limpio de todos los sensores)
"""

import threading
import signal
import sys
import time
import argparse
import logging
import os

from sensor_types import (
    TemperatureSensor,
    HumiditySensor,
    PressureSensor,
    VibrationSensor,
    EnergySensor,
)

# ─── Logger principal ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("run_sensors")

# ─── Tokens de autenticación (en producción: usar variables de entorno) ───
TOKENS = {
    "sensor_temp_01":  os.getenv("TOKEN_TEMP",  "tok_temp_001"),
    "sensor_hum_01":   os.getenv("TOKEN_HUM",   "tok_hum_001"),
    "sensor_pres_01":  os.getenv("TOKEN_PRES",  "tok_pres_001"),
    "sensor_vib_01":   os.getenv("TOKEN_VIB",   "tok_vib_001"),
    "sensor_ener_01":  os.getenv("TOKEN_ENER",  "tok_ener_001"),
}


def build_sensors(host: str, port: int) -> list:
    """Construye la lista de instancias de sensores con sus parámetros."""
    common = dict(host=host, port=port)

    sensors = [
        TemperatureSensor(
            sensor_id="sensor_temp_01",
            token=TOKENS["sensor_temp_01"],
            interval=5.0,          # medición cada 5 segundos
            **common,
        ),
        HumiditySensor(
            sensor_id="sensor_hum_01",
            token=TOKENS["sensor_hum_01"],
            interval=7.0,          # medición cada 7 segundos
            **common,
        ),
        PressureSensor(
            sensor_id="sensor_pres_01",
            token=TOKENS["sensor_pres_01"],
            interval=10.0,         # la presión cambia lento
            **common,
        ),
        VibrationSensor(
            sensor_id="sensor_vib_01",
            token=TOKENS["sensor_vib_01"],
            interval=3.0,          # vibración necesita muestreo más rápido
            **common,
        ),
        EnergySensor(
            sensor_id="sensor_ener_01",
            token=TOKENS["sensor_ener_01"],
            interval=8.0,
            **common,
        ),
    ]
    return sensors


def main():
    parser = argparse.ArgumentParser(
        description="Lanza los sensores IoT simulados del sistema SIMP"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SIMP_SERVER_HOST", "monitor.iot-monitor.local"),
        help="Hostname o IP del servidor SIMP (default: variable SIMP_SERVER_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SIMP_SERVER_PORT", "9000")),
        help="Puerto TCP del servidor SIMP (default: 9000)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging (default: INFO)",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    log.info("=" * 55)
    log.info("  Sistema de Sensores IoT — SIMP v1.0")
    log.info(f"  Servidor: {args.host}:{args.port}")
    log.info("=" * 55)

    sensors = build_sensors(args.host, args.port)
    threads: list[threading.Thread] = []

    # ── Lanzar cada sensor en su propio hilo ──────────────────
    for sensor in sensors:
        t = threading.Thread(
            target=sensor.run,
            name=f"Thread-{sensor.sensor_id}",
            daemon=True,
        )
        threads.append(t)
        t.start()
        log.info(f"Sensor iniciado: {sensor.sensor_id} [{sensor.sensor_type}]")
        time.sleep(0.3)   # pequeño delay para no saturar el servidor al inicio

    log.info(f"\n{len(sensors)} sensores activos. Presiona Ctrl+C para detener.\n")

    # ── Manejador de señal para cierre limpio ─────────────────
    def shutdown(signum, frame):
        log.info("\nSeñal recibida. Deteniendo sensores...")
        for s in sensors:
            s.stop()
        log.info("Todos los sensores detenidos.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Monitoreo: muestra estado de hilos cada 30 segundos ──
    while True:
        alive = sum(1 for t in threads if t.is_alive())
        log.info(f"Sensores activos: {alive}/{len(threads)}")

        if alive == 0:
            log.warning("Todos los sensores se detuvieron. Saliendo.")
            break

        time.sleep(30)


if __name__ == "__main__":
    main()
