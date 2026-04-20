package iot;

import java.util.Random;
import java.util.logging.Logger;

/**
 * SensorTypes.java — Implementaciones de los 5 tipos de sensores IoT.
 *
 * Cada clase interna estática hereda de SensorBase e implementa
 * getSensorType(), getUnit() y measure() con datos simulados realistas.
 *
 * Sensores implementados:
 *   1. TemperatureSensor  — TEMPERATURE (Celsius)
 *   2. HumiditySensor     — HUMIDITY    (Percent)
 *   3. PressureSensor     — PRESSURE    (hPa)
 *   4. VibrationSensor    — VIBRATION   (g)
 *   5. EnergySensor       — ENERGY      (kWh)
 */
public class SensorTypes {

    private static final Random RNG = new Random();

    // ─────────────────────────────────────────────────────────
    // 1. Sensor de Temperatura
    // ─────────────────────────────────────────────────────────
    public static class TemperatureSensor extends SensorBase {

        private final double baseTemp;
        private final long   startMs;
        private static final double SPIKE_PROB = 0.03;

        public TemperatureSensor(String id, String token,
                                  String host, int port) {
            super(id, token, host, port, 5.0);
            this.baseTemp = 20.0 + RNG.nextDouble() * 10.0;
            this.startMs  = System.currentTimeMillis();
        }

        @Override public String getSensorType() { return SimpProtocol.SENSOR_TEMP; }
        @Override public String getUnit()        { return "Celsius"; }

        @Override
        public double measure() {
            // Oscilación sinusoidal: ciclo de 2 min = "1 día simulado"
            double elapsed = (System.currentTimeMillis() - startMs) / 1000.0;
            double osc     = 8.0 * Math.sin(2 * Math.PI * elapsed / 120.0);
            double noise   = RNG.nextGaussian() * 0.5;
            double value   = baseTemp + osc + noise;

            // Pico ocasional para probar alertas
            if (RNG.nextDouble() < SPIKE_PROB) {
                double spike = 55.0 + RNG.nextDouble() * 15.0;
                value += spike;
                log.warning(String.format("Pico de temperatura: %.2f°C", value));
            }
            return Math.max(-20.0, Math.min(120.0, value));
        }
    }

    // ─────────────────────────────────────────────────────────
    // 2. Sensor de Humedad
    // ─────────────────────────────────────────────────────────
    public static class HumiditySensor extends SensorBase {

        private double humidity;
        private double trend     = 0.0;
        private int    rainLeft  = 0;

        public HumiditySensor(String id, String token,
                               String host, int port) {
            super(id, token, host, port, 7.0);
            this.humidity = 40.0 + RNG.nextDouble() * 20.0;
        }

        @Override public String getSensorType() { return SimpProtocol.SENSOR_HUMIDITY; }
        @Override public String getUnit()        { return "Percent"; }

        @Override
        public double measure() {
            if (rainLeft == 0 && RNG.nextDouble() < 0.02) {
                rainLeft = 3 + RNG.nextInt(6);
                log.info("Evento de lluvia simulado iniciado");
            }

            if (rainLeft > 0) {
                trend = 2.0 + RNG.nextDouble() * 3.0;
                rainLeft--;
                if (rainLeft == 0) trend = -(0.5 + RNG.nextDouble());
            } else {
                trend += RNG.nextGaussian() * 0.1;
                trend  = Math.max(-0.5, Math.min(0.5, trend));
            }

            humidity = Math.max(10.0, Math.min(98.0,
                       humidity + trend + RNG.nextGaussian() * 0.3));
            return humidity;
        }
    }

    // ─────────────────────────────────────────────────────────
    // 3. Sensor de Presión Atmosférica
    // ─────────────────────────────────────────────────────────
    public static class PressureSensor extends SensorBase {

        private double pressure;
        private static final double MEAN = 1013.25;

        public PressureSensor(String id, String token,
                               String host, int port) {
            super(id, token, host, port, 10.0);
            this.pressure = 1000.0 + RNG.nextDouble() * 20.0;
        }

        @Override public String getSensorType() { return SimpProtocol.SENSOR_PRESSURE; }
        @Override public String getUnit()        { return "hPa"; }

        @Override
        public double measure() {
            // Random walk con reversión a la media
            double reversion = (MEAN - pressure) * 0.01;
            double delta     = reversion + RNG.nextGaussian() * 0.3;
            pressure = Math.max(750.0, Math.min(1100.0, pressure + delta));
            return pressure;
        }
    }

    // ─────────────────────────────────────────────────────────
    // 4. Sensor de Vibración
    // ─────────────────────────────────────────────────────────
    public static class VibrationSensor extends SensorBase {

        private final double baseVibration;
        private static final double FAILURE_PROB = 0.04;

        public VibrationSensor(String id, String token,
                                String host, int port) {
            super(id, token, host, port, 3.0);
            this.baseVibration = 0.01 + RNG.nextDouble() * 0.09;
        }

        @Override public String getSensorType() { return SimpProtocol.SENSOR_VIBRATION; }
        @Override public String getUnit()        { return "g"; }

        @Override
        public double measure() {
            double noise = Math.abs(RNG.nextGaussian() * 0.02);
            double value = baseVibration + noise;

            if (RNG.nextDouble() < FAILURE_PROB) {
                double spike = 1.5 + RNG.nextDouble() * 2.5;
                value += spike;
                log.warning(String.format("Fallo mecánico simulado: %.3fg", value));
            }
            return Math.max(0.0, value);
        }
    }

    // ─────────────────────────────────────────────────────────
    // 5. Sensor de Consumo Energético
    // ─────────────────────────────────────────────────────────
    public static class EnergySensor extends SensorBase {

        private final double baseConsumption;
        private final long   startMs;
        private static final double OVERLOAD_PROB = 0.02;

        public EnergySensor(String id, String token,
                             String host, int port) {
            super(id, token, host, port, 8.0);
            this.baseConsumption = 2.0 + RNG.nextDouble() * 6.0;
            this.startMs         = System.currentTimeMillis();
        }

        @Override public String getSensorType() { return SimpProtocol.SENSOR_ENERGY; }
        @Override public String getUnit()        { return "kWh"; }

        @Override
        public double measure() {
            double elapsed  = (System.currentTimeMillis() - startMs) / 1000.0;
            double t        = (elapsed % 120.0) / 120.0;

            // Picos matutino y vespertino
            double morning   = Math.exp(-Math.pow(t - 0.25, 2) / 0.005);
            double afternoon = Math.exp(-Math.pow(t - 0.75, 2) / 0.005);
            double pattern   = baseConsumption * (1 + 1.5 * morning + 2.0 * afternoon);
            double value     = Math.max(0.1, pattern + RNG.nextGaussian() * 0.2);

            if (RNG.nextDouble() < OVERLOAD_PROB) {
                value += 40.0 + RNG.nextDouble() * 15.0;
                log.warning(String.format("Sobrecarga energética: %.2f kWh", value));
            }
            return value;
        }
    }

    private SensorTypes() {}   // utilidades estáticas — no instanciar
}
