"""
sensor_types.py — Los 5 tipos de sensores IoT simulados.

Cada clase hereda de SensorClient e implementa:
  - sensor_type : tipo según protocolo SIMP
  - unit        : unidad de medición
  - measure()   : generación realista de datos simulados

Sensores implementados:
  1. TemperatureSensor   — TEMPERATURE  (Celsius)
  2. HumiditySensor      — HUMIDITY     (Percent)
  3. PressureSensor      — PRESSURE     (hPa)
  4. VibrationSensor     — VIBRATION    (g)
  5. EnergySensor        — ENERGY       (kWh)
"""

import random
import math
import time
from sensor_client import SensorClient


# ─────────────────────────────────────────────────────────────
# 1. Sensor de Temperatura
# ─────────────────────────────────────────────────────────────
class TemperatureSensor(SensorClient):
    """
    Simula un sensor de temperatura industrial.
    Rango normal: 15°C – 40°C
    Umbral de alerta: < -10°C  o  > 90°C

    Modelo: oscilación sinusoidal diaria + ruido gaussiano.
    Ocasionalmente genera picos para probar las alertas.
    """

    def __init__(self, sensor_id: str, token: str, **kwargs):
        super().__init__(sensor_id, token, **kwargs)
        self._base_temp   = random.uniform(20.0, 30.0)
        self._spike_prob  = 0.03   # 3% de probabilidad de pico
        self._start_time  = time.time()

    @property
    def sensor_type(self) -> str:
        return "TEMPERATURE"

    @property
    def unit(self) -> str:
        return "Celsius"

    def measure(self) -> float:
        # Oscilación sinusoidal: ciclo de 24 h simulado en 2 min
        elapsed  = time.time() - self._start_time
        period   = 120.0                        # 2 minutos = "1 día simulado"
        osc      = 8.0 * math.sin(2 * math.pi * elapsed / period)
        noise    = random.gauss(0, 0.5)
        value    = self._base_temp + osc + noise

        # Spike ocasional (para probar sistema de alertas)
        if random.random() < self._spike_prob:
            value += random.uniform(55.0, 70.0)
            self.log.warning(f"Pico de temperatura simulado: {value:.2f}°C")

        return max(-20.0, min(120.0, value))   # clamping físico


# ─────────────────────────────────────────────────────────────
# 2. Sensor de Humedad
# ─────────────────────────────────────────────────────────────
class HumiditySensor(SensorClient):
    """
    Simula un sensor de humedad relativa.
    Rango normal: 30% – 70%
    Umbral de alerta: > 95%

    Modelo: tendencia lenta + ruido + eventos de lluvia simulados.
    """

    def __init__(self, sensor_id: str, token: str, **kwargs):
        super().__init__(sensor_id, token, **kwargs)
        self._base_humidity = random.uniform(40.0, 60.0)
        self._trend         = 0.0
        self._rain_event    = False
        self._rain_duration = 0

    @property
    def sensor_type(self) -> str:
        return "HUMIDITY"

    @property
    def unit(self) -> str:
        return "Percent"

    def measure(self) -> float:
        # Evento de lluvia: aumenta humedad bruscamente
        if not self._rain_event and random.random() < 0.02:
            self._rain_event    = True
            self._rain_duration = random.randint(3, 8)
            self.log.info("Evento de lluvia simulado iniciado")

        if self._rain_event:
            self._trend = random.uniform(2.0, 5.0)
            self._rain_duration -= 1
            if self._rain_duration <= 0:
                self._rain_event = False
                self._trend      = -random.uniform(0.5, 1.5)  # secado gradual
        else:
            # Leve deriva aleatoria
            self._trend += random.gauss(0, 0.1)
            self._trend  = max(-0.5, min(0.5, self._trend))

        noise = random.gauss(0, 0.3)
        self._base_humidity = max(10.0, min(98.0,
                                    self._base_humidity + self._trend + noise))
        return self._base_humidity


# ─────────────────────────────────────────────────────────────
# 3. Sensor de Presión Atmosférica
# ─────────────────────────────────────────────────────────────
class PressureSensor(SensorClient):
    """
    Simula un sensor de presión atmosférica.
    Rango normal: 980 hPa – 1030 hPa
    Umbral de alerta: < 800 hPa  o  > 1100 hPa

    Modelo: random walk suave (presión cambia lentamente).
    """

    def __init__(self, sensor_id: str, token: str, **kwargs):
        super().__init__(sensor_id, token, **kwargs)
        self._pressure = random.uniform(1000.0, 1020.0)

    @property
    def sensor_type(self) -> str:
        return "PRESSURE"

    @property
    def unit(self) -> str:
        return "hPa"

    def measure(self) -> float:
        # Random walk con tendencia de retorno al valor base
        mean_reversion = (1013.25 - self._pressure) * 0.01
        delta = random.gauss(mean_reversion, 0.3)
        self._pressure = max(750.0, min(1100.0, self._pressure + delta))
        return self._pressure


# ─────────────────────────────────────────────────────────────
# 4. Sensor de Vibración Mecánica
# ─────────────────────────────────────────────────────────────
class VibrationSensor(SensorClient):
    """
    Simula un sensor de vibración en maquinaria industrial.
    Rango normal: 0 g – 0.5 g
    Umbral de alerta: > 2.0 g (fallo mecánico inminente)

    Modelo: nivel base bajo + picos de vibración por fallas simuladas.
    """

    def __init__(self, sensor_id: str, token: str, **kwargs):
        super().__init__(sensor_id, token, **kwargs)
        self._base_vibration = random.uniform(0.01, 0.1)
        self._failure_prob   = 0.04   # 4% de probabilidad de fallo

    @property
    def sensor_type(self) -> str:
        return "VIBRATION"

    @property
    def unit(self) -> str:
        return "g"

    def measure(self) -> float:
        # Vibración base (ruido de máquina normal)
        noise = abs(random.gauss(0, 0.02))
        value = self._base_vibration + noise

        # Fallo mecánico simulado
        if random.random() < self._failure_prob:
            spike = random.uniform(1.5, 4.0)
            value += spike
            self.log.warning(f"Fallo mecánico simulado: {value:.3f}g")

        return max(0.0, value)


# ─────────────────────────────────────────────────────────────
# 5. Sensor de Consumo Energético
# ─────────────────────────────────────────────────────────────
class EnergySensor(SensorClient):
    """
    Simula un sensor de consumo energético (medidor inteligente).
    Rango normal: 0.5 kWh – 15 kWh
    Umbral de alerta: > 50 kWh (consumo anormal)

    Modelo: patrón de consumo diario realista (picos mañana/tarde).
    """

    def __init__(self, sensor_id: str, token: str, **kwargs):
        super().__init__(sensor_id, token, **kwargs)
        self._base_consumption = random.uniform(2.0, 8.0)
        self._start_time       = time.time()
        self._overload_prob    = 0.02

    @property
    def sensor_type(self) -> str:
        return "ENERGY"

    @property
    def unit(self) -> str:
        return "kWh"

    def measure(self) -> float:
        # Patrón de consumo simulado: dos picos en el "día"
        elapsed = time.time() - self._start_time
        period  = 120.0   # 2 min = "1 día simulado"
        t       = (elapsed % period) / period   # 0.0 a 1.0

        # Pico matutino (~25%) y vespertino (~75%)
        morning   = math.exp(-((t - 0.25) ** 2) / 0.005)
        afternoon = math.exp(-((t - 0.75) ** 2) / 0.005)
        pattern   = self._base_consumption * (1 + 1.5 * morning + 2.0 * afternoon)

        noise = random.gauss(0, 0.2)
        value = max(0.1, pattern + noise)

        # Sobrecarga simulada
        if random.random() < self._overload_prob:
            value += random.uniform(40.0, 55.0)
            self.log.warning(f"Sobrecarga energética simulada: {value:.2f} kWh")

        return value
