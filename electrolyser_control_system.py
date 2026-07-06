"""
Hydrogen Electrolyser Control System
Supports PEM, AEM, and alkaline electrolysers with voltage and inverter frequency control
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from abc import ABC, abstractmethod
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ElectrolyserType(Enum):
    """Supported electrolyser types"""
    PEM = "PEM"  # Proton Exchange Membrane
    AEM = "AEM"  # Anion Exchange Membrane
    ALKALINE = "ALKALINE"
    SOEC = "SOEC"  # Solid Oxide Electrolysis Cell
    CUSTOM = "CUSTOM"


class OperatingMode(Enum):
    """Operating modes for the electrolyser"""
    IDLE = "IDLE"
    STANDBY = "STANDBY"
    RAMP_UP = "RAMP_UP"
    NORMAL = "NORMAL"
    RAMP_DOWN = "RAMP_DOWN"
    FAULT = "FAULT"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class ElectrolyserSpecs:
    """Specifications for electrolyser operation"""
    type: ElectrolyserType
    nominal_voltage: float  # Volts
    nominal_current: float  # Amps
    nominal_power: float  # Watts
    min_voltage: float
    max_voltage: float
    min_current: float
    max_current: float
    min_efficiency: float  # %
    max_efficiency: float  # %
    water_consumption_rate: float  # L/hour
    hydrogen_production_rate: float  # Nm³/hour
    oxygen_production_rate: float  # Nm³/hour
    temperature_min: float  # °C
    temperature_max: float  # °C
    pressure_min: float  # bar
    pressure_max: float  # bar


@dataclass
class InverterConfig:
    """Inverter configuration"""
    rated_power: float  # Watts
    input_voltage_min: float
    input_voltage_max: float
    output_frequency: float  # Hz (default)
    frequency_range: Tuple[float, float]  # Min and max frequency
    efficiency: float  # %
    switching_frequency: float  # Hz


class SafetyMonitor:
    """Monitors safety parameters and issues alerts"""

    def __init__(self, specs: ElectrolyserSpecs):
        self.specs = specs
        self.alerts = []
        self.warnings = []

    def check_voltage(self, voltage: float) -> bool:
        """Check if voltage is within safe limits"""
        if voltage < self.specs.min_voltage:
            self.alerts.append(f"Voltage too low: {voltage}V < {self.specs.min_voltage}V")
            return False
        if voltage > self.specs.max_voltage:
            self.alerts.append(f"Voltage too high: {voltage}V > {self.specs.max_voltage}V")
            return False
        return True

    def check_current(self, current: float) -> bool:
        """Check if current is within safe limits"""
        if current < self.specs.min_current:
            self.warnings.append(f"Current below minimum: {current}A < {self.specs.min_current}A")
            return True
        if current > self.specs.max_current:
            self.alerts.append(f"Current too high: {current}A > {self.specs.max_current}A")
            return False
        return True

    def check_temperature(self, temperature: float) -> bool:
        """Check if temperature is within safe limits"""
        if temperature < self.specs.temperature_min:
            self.warnings.append(f"Temperature below minimum: {temperature}°C")
            return True
        if temperature > self.specs.temperature_max:
            self.alerts.append(f"Temperature too high: {temperature}°C")
            return False
        return True

    def check_pressure(self, pressure: float) -> bool:
        """Check if pressure is within safe limits"""
        if pressure < self.specs.pressure_min:
            self.warnings.append(f"Pressure below minimum: {pressure} bar")
            return True
        if pressure > self.specs.pressure_max:
            self.alerts.append(f"Pressure too high: {pressure} bar")
            return False
        return True

    def get_status(self) -> Dict:
        """Get safety status"""
        return {
            "alerts": self.alerts,
            "warnings": self.warnings,
            "safe": len(self.alerts) == 0
        }

    def clear(self):
        """Clear alerts and warnings"""
        self.alerts = []
        self.warnings = []


class InverterController:
    """Controls AC inverter for power supply"""

    def __init__(self, config: InverterConfig):
        self.config = config
        self.current_frequency = config.output_frequency
        self.current_voltage = 0.0
        self.is_enabled = False
        self.output_power = 0.0

    def enable(self):
        """Enable inverter"""
        logger.info("Inverter enabled")
        self.is_enabled = True

    def disable(self):
        """Disable inverter"""
        logger.info("Inverter disabled")
        self.is_enabled = False
        self.output_power = 0.0

    def set_frequency(self, frequency: float) -> bool:
        """Set inverter output frequency"""
        if frequency < self.config.frequency_range[0] or frequency > self.config.frequency_range[1]:
            logger.error(f"Frequency {frequency} Hz out of range {self.config.frequency_range}")
            return False

        self.current_frequency = frequency
        logger.info(f"Inverter frequency set to {frequency} Hz")
        return True

    def set_voltage(self, voltage: float) -> bool:
        """Set inverter output voltage"""
        if voltage < self.config.input_voltage_min or voltage > self.config.input_voltage_max:
            logger.error(f"Voltage {voltage}V out of range")
            return False

        self.current_voltage = voltage
        logger.info(f"Inverter voltage set to {voltage}V")
        return True

    def set_power(self, power: float) -> bool:
        """Set inverter output power"""
        if power > self.config.rated_power:
            logger.error(f"Power {power}W exceeds rated {self.config.rated_power}W")
            return False

        self.output_power = power
        logger.info(f"Inverter power set to {power}W")
        return True

    def get_status(self) -> Dict:
        """Get inverter status"""
        return {
            "enabled": self.is_enabled,
            "frequency": self.current_frequency,
            "voltage": self.current_voltage,
            "power": self.output_power,
            "efficiency": self.config.efficiency
        }


class VoltageRegulator:
    """Regulates electrolyser voltage with PID control"""

    def __init__(self, specs: ElectrolyserSpecs, kp: float = 0.1, ki: float = 0.01, kd: float = 0.05):
        self.specs = specs
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain
        self.kd = kd  # Derivative gain
        self.prev_error = 0.0
        self.integral = 0.0
        self.current_voltage = specs.nominal_voltage

    def regulate(self, target_voltage: float, current_voltage: float, dt: float = 0.1) -> float:
        """
        PID control for voltage regulation

        Args:
            target_voltage: Desired voltage
            current_voltage: Measured voltage
            dt: Time step

        Returns:
            Adjusted voltage setpoint
        """
        # Clamp target voltage to safe range
        target_voltage = max(self.specs.min_voltage, min(target_voltage, self.specs.max_voltage))

        error = target_voltage - current_voltage

        # PID calculation
        self.integral += error * dt
        self.integral = max(-10, min(10, self.integral))  # Anti-windup

        derivative = (error - self.prev_error) / dt if dt > 0 else 0
        self.prev_error = error

        adjustment = self.kp * error + self.ki * self.integral + self.kd * derivative

        new_voltage = current_voltage + adjustment
        new_voltage = max(self.specs.min_voltage, min(new_voltage, self.specs.max_voltage))

        logger.debug(f"Voltage regulation: target={target_voltage}V, current={current_voltage}V, adjusted={new_voltage}V")

        return new_voltage


class ElectrolyserBase(ABC):
    """Base class for electrolyser"""

    def __init__(self, specs: ElectrolyserSpecs, inverter: InverterController):
        self.specs = specs
        self.inverter = inverter
        self.safety_monitor = SafetyMonitor(specs)
        self.voltage_regulator = VoltageRegulator(specs)

        self.current_mode = OperatingMode.IDLE
        self.current_voltage = 0.0
        self.current_current = 0.0
        self.current_power = 0.0
        self.current_temperature = 25.0
        self.current_pressure = 1.0

        self.hydrogen_produced = 0.0  # Nm³
        self.oxygen_produced = 0.0  # Nm³
        self.water_consumed = 0.0  # L

        self.start_time = None
        self.run_time = 0.0  # Seconds

        logger.info(f"Electrolyser initialized: {specs.type.value}")

    @abstractmethod
    def calculate_efficiency(self) -> float:
        """Calculate current efficiency"""
        pass

    def start(self) -> bool:
        """Start electrolyser"""
        if self.current_mode != OperatingMode.IDLE:
            logger.warning(f"Cannot start: already in {self.current_mode.value} mode")
            return False

        logger.info("Starting electrolyser...")
        self.inverter.enable()
        self.current_mode = OperatingMode.RAMP_UP
        self.start_time = time.time()
        return True

    def stop(self) -> bool:
        """Stop electrolyser"""
        logger.info("Stopping electrolyser...")
        self.current_mode = OperatingMode.RAMP_DOWN
        self.inverter.disable()
        self.current_voltage = 0.0
        self.current_current = 0.0
        self.current_mode = OperatingMode.IDLE
        return True

    def set_voltage_setpoint(self, voltage: float) -> bool:
        """Set target voltage"""
        if not self.safety_monitor.check_voltage(voltage):
            logger.error("Voltage check failed")
            return False

        # Regulate voltage
        self.current_voltage = self.voltage_regulator.regulate(voltage, self.current_voltage)
        self.inverter.set_voltage(self.current_voltage)
        return True

    def set_power_setpoint(self, power: float) -> bool:
        """Set target power"""
        if power > self.specs.nominal_power:
            logger.warning(f"Power {power}W exceeds nominal {self.specs.nominal_power}W")

        if not self.inverter.set_power(power):
            return False

        self.current_power = power
        # Calculate equivalent current from power: P = V * I
        if self.current_voltage > 0:
            self.current_current = power / self.current_voltage

        return self.safety_monitor.check_current(self.current_current)

    def update_state(self, dt: float = 1.0):
        """Update electrolyser state"""
        if self.current_mode == OperatingMode.IDLE:
            return

        if self.start_time:
            self.run_time = time.time() - self.start_time

        # Update energy production based on current operation
        if self.current_mode == OperatingMode.NORMAL and self.current_power > 0:
            # Production rate: mol/s → Nm³/hour conversion
            time_fraction = dt / 3600.0  # Convert dt from seconds to hours

            self.hydrogen_produced += self.specs.hydrogen_production_rate * time_fraction
            self.oxygen_produced += self.specs.oxygen_production_rate * time_fraction
            self.water_consumed += self.specs.water_consumption_rate * time_fraction

            logger.debug(f"H2: {self.hydrogen_produced:.2f} Nm³, O2: {self.oxygen_produced:.2f} Nm³")

    def transition_mode(self, target_mode: OperatingMode) -> bool:
        """Transition between operating modes"""
        logger.info(f"Transitioning from {self.current_mode.value} to {target_mode.value}")

        if target_mode == OperatingMode.NORMAL:
            if self.current_mode == OperatingMode.RAMP_UP:
                self.current_mode = OperatingMode.NORMAL
                return True
        elif target_mode == OperatingMode.RAMP_DOWN:
            self.current_mode = OperatingMode.RAMP_DOWN
            return True
        elif target_mode == OperatingMode.IDLE:
            self.current_mode = OperatingMode.IDLE
            return True

        return False

    def get_status(self) -> Dict:
        """Get current status"""
        return {
            "type": self.specs.type.value,
            "mode": self.current_mode.value,
            "voltage": self.current_voltage,
            "current": self.current_current,
            "power": self.current_power,
            "temperature": self.current_temperature,
            "pressure": self.current_pressure,
            "efficiency": self.calculate_efficiency(),
            "hydrogen_produced": self.hydrogen_produced,
            "oxygen_produced": self.oxygen_produced,
            "water_consumed": self.water_consumed,
            "run_time": self.run_time,
            "inverter": self.inverter.get_status(),
            "safety": self.safety_monitor.get_status()
        }


class PEMElectrolyser(ElectrolyserBase):
    """PEM (Proton Exchange Membrane) Electrolyser"""

    def __init__(self, inverter: InverterController):
        specs = ElectrolyserSpecs(
            type=ElectrolyserType.PEM,
            nominal_voltage=48.0,
            nominal_current=100.0,
            nominal_power=4800.0,
            min_voltage=30.0,
            max_voltage=60.0,
            min_current=10.0,
            max_current=150.0,
            min_efficiency=60.0,
            max_efficiency=75.0,
            water_consumption_rate=0.9,
            hydrogen_production_rate=0.95,
            oxygen_production_rate=0.475,
            temperature_min=5.0,
            temperature_max=80.0,
            pressure_min=1.0,
            pressure_max=35.0
        )
        super().__init__(specs, inverter)

    def calculate_efficiency(self) -> float:
        """Calculate PEM efficiency"""
        if self.current_power == 0:
            return 0.0

        # Efficiency based on load (typically 60-75%)
        load_factor = self.current_power / self.specs.nominal_power
        efficiency = self.specs.min_efficiency + (self.specs.max_efficiency - self.specs.min_efficiency) * load_factor
        return min(efficiency, self.specs.max_efficiency)


class AEMElectrolyser(ElectrolyserBase):
    """AEM (Anion Exchange Membrane) Electrolyser"""

    def __init__(self, inverter: InverterController):
        specs = ElectrolyserSpecs(
            type=ElectrolyserType.AEM,
            nominal_voltage=40.0,
            nominal_current=120.0,
            nominal_power=4800.0,
            min_voltage=25.0,
            max_voltage=55.0,
            min_current=15.0,
            max_current=180.0,
            min_efficiency=55.0,
            max_efficiency=72.0,
            water_consumption_rate=1.0,
            hydrogen_production_rate=0.90,
            oxygen_production_rate=0.45,
            temperature_min=10.0,
            temperature_max=85.0,
            pressure_min=1.0,
            pressure_max=30.0
        )
        super().__init__(specs, inverter)

    def calculate_efficiency(self) -> float:
        """Calculate AEM efficiency"""
        if self.current_power == 0:
            return 0.0

        load_factor = self.current_power / self.specs.nominal_power
        efficiency = self.specs.min_efficiency + (self.specs.max_efficiency - self.specs.min_efficiency) * load_factor
        return min(efficiency, self.specs.max_efficiency)


class AlkalineElectrolyser(ElectrolyserBase):
    """Alkaline Electrolyser"""

    def __init__(self, inverter: InverterController):
        specs = ElectrolyserSpecs(
            type=ElectrolyserType.ALKALINE,
            nominal_voltage=24.0,
            nominal_current=200.0,
            nominal_power=4800.0,
            min_voltage=18.0,
            max_voltage=32.0,
            min_current=20.0,
            max_current=300.0,
            min_efficiency=52.0,
            max_efficiency=68.0,
            water_consumption_rate=1.2,
            hydrogen_production_rate=0.85,
            oxygen_production_rate=0.425,
            temperature_min=0.0,
            temperature_max=70.0,
            pressure_min=0.5,
            pressure_max=25.0
        )
        super().__init__(specs, inverter)

    def calculate_efficiency(self) -> float:
        """Calculate alkaline efficiency"""
        if self.current_power == 0:
            return 0.0

        load_factor = self.current_power / self.specs.nominal_power
        efficiency = self.specs.min_efficiency + (self.specs.max_efficiency - self.specs.min_efficiency) * load_factor
        return min(efficiency, self.specs.max_efficiency)


class ElectrolyserControlSystem:
    """Main control system for managing electrolyser operation"""

    def __init__(self, electrolyser_type: ElectrolyserType = ElectrolyserType.PEM):
        # Initialize inverter
        inverter_config = InverterConfig(
            rated_power=5000.0,
            input_voltage_min=200.0,
            input_voltage_max=240.0,
            output_frequency=50.0,
            frequency_range=(40.0, 60.0),
            efficiency=95.0,
            switching_frequency=16000.0
        )
        self.inverter = InverterController(inverter_config)

        # Initialize electrolyser based on type
        if electrolyser_type == ElectrolyserType.PEM:
            self.electrolyser = PEMElectrolyser(self.inverter)
        elif electrolyser_type == ElectrolyserType.AEM:
            self.electrolyser = AEMElectrolyser(self.inverter)
        elif electrolyser_type == ElectrolyserType.ALKALINE:
            self.electrolyser = AlkalineElectrolyser(self.inverter)
        else:
            raise ValueError(f"Unsupported electrolyser type: {electrolyser_type}")

        self.log_file = f"electrolyser_{electrolyser_type.value.lower()}_log.json"
        self.operation_log = []

        logger.info(f"Control system initialized with {electrolyser_type.value} electrolyser")

    def start_operation(self):
        """Start electrolyser operation"""
        if self.electrolyser.start():
            logger.info("Electrolyser operation started")
            return True
        return False

    def stop_operation(self):
        """Stop electrolyser operation"""
        if self.electrolyser.stop():
            self.save_log()
            logger.info("Electrolyser operation stopped and log saved")
            return True
        return False

    def set_voltage(self, voltage: float) -> bool:
        """Set electrolyser voltage"""
        return self.electrolyser.set_voltage_setpoint(voltage)

    def set_power(self, power: float) -> bool:
        """Set electrolyser power"""
        return self.electrolyser.set_power_setpoint(power)

    def set_frequency(self, frequency: float) -> bool:
        """Set inverter frequency"""
        return self.inverter.set_frequency(frequency)

    def ramp_to_power(self, target_power: float, ramp_rate: float = 100.0, dt: float = 0.1):
        """
        Gradually ramp power to target

        Args:
            target_power: Target power in watts
            ramp_rate: Power increase rate in W/s
            dt: Time step in seconds
        """
        current_power = 0.0
        logger.info(f"Ramping power to {target_power}W at rate {ramp_rate}W/s")

        while current_power < target_power:
            current_power = min(current_power + ramp_rate * dt, target_power)
            self.set_power(current_power)
            self.electrolyser.update_state(dt)

            # Log status
            status = self.electrolyser.get_status()
            self.operation_log.append({
                "timestamp": datetime.now().isoformat(),
                "status": status
            })

            logger.info(f"Power: {current_power:.1f}W, Efficiency: {status['efficiency']:.1f}%")
            time.sleep(dt)

        # Transition to normal mode
        self.electrolyser.transition_mode(OperatingMode.NORMAL)
        logger.info("Electrolyser in normal operation mode")

    def ramp_to_voltage(self, target_voltage: float, ramp_rate: float = 1.0, dt: float = 0.1):
        """
        Gradually ramp voltage to target

        Args:
            target_voltage: Target voltage in volts
            ramp_rate: Voltage increase rate in V/s
            dt: Time step in seconds
        """
        current_voltage = self.electrolyser.current_voltage
        logger.info(f"Ramping voltage to {target_voltage}V at rate {ramp_rate}V/s")

        while current_voltage < target_voltage:
            current_voltage = min(current_voltage + ramp_rate * dt, target_voltage)
            self.set_voltage(current_voltage)
            self.electrolyser.update_state(dt)

            status = self.electrolyser.get_status()
            logger.info(f"Voltage: {current_voltage:.2f}V, Current: {status['current']:.1f}A")
            time.sleep(dt)

    def get_status(self) -> Dict:
        """Get complete system status"""
        return self.electrolyser.get_status()

    def save_log(self):
        """Save operation log to file"""
        with open(self.log_file, 'w') as f:
            json.dump(self.operation_log, f, indent=2)
        logger.info(f"Operation log saved to {self.log_file}")

    def print_status(self):
        """Print formatted status"""
        status = self.get_status()
        print("\n" + "="*50)
        print(f"ELECTROLYSER STATUS - {status['type']}")
        print("="*50)
        print(f"Mode: {status['mode']}")
        print(f"Voltage: {status['voltage']:.2f} V")
        print(f"Current: {status['current']:.2f} A")
        print(f"Power: {status['power']:.2f} W")
        print(f"Temperature: {status['temperature']:.1f} °C")
        print(f"Pressure: {status['pressure']:.2f} bar")
        print(f"Efficiency: {status['efficiency']:.1f} %")
        print(f"\nProduction:")
        print(f"  Hydrogen: {status['hydrogen_produced']:.3f} Nm³")
        print(f"  Oxygen: {status['oxygen_produced']:.3f} Nm³")
        print(f"  Water consumed: {status['water_consumed']:.2f} L")
        print(f"  Runtime: {status['run_time']:.1f} s")
        print(f"\nSafety Status: {'SAFE' if status['safety']['safe'] else 'ALERT'}")
        if status['safety']['alerts']:
            for alert in status['safety']['alerts']:
                print(f"  ⚠️  {alert}")
        print("="*50 + "\n")


def demo_pem_operation():
    """Demonstrate PEM electrolyser operation"""
    print("\n" + "="*50)
    print("PEM ELECTROLYSER CONTROL DEMO")
    print("="*50)

    system = ElectrolyserControlSystem(ElectrolyserType.PEM)

    # Start operation
    system.start_operation()
    time.sleep(0.5)

    # Ramp up voltage
    system.ramp_to_voltage(target_voltage=45.0, ramp_rate=2.0, dt=0.05)
    time.sleep(1)

    # Ramp up power
    system.ramp_to_power(target_power=4000.0, ramp_rate=200.0, dt=0.1)
    time.sleep(2)

    # Set specific frequency
    system.set_frequency(50.0)

    # Print final status
    system.print_status()

    # Stop operation
    system.stop_operation()


def demo_aem_operation():
    """Demonstrate AEM electrolyser operation"""
    print("\n" + "="*50)
    print("AEM ELECTROLYSER CONTROL DEMO")
    print("="*50)

    system = ElectrolyserControlSystem(ElectrolyserType.AEM)

    system.start_operation()
    time.sleep(0.5)

    # Set power directly (faster demo)
    system.set_voltage(40.0)
    system.set_power(3500.0)
    system.electrolyser.transition_mode(OperatingMode.NORMAL)

    # Simulate 5 seconds of operation
    for i in range(50):
        system.electrolyser.update_state(0.1)
        if i % 10 == 0:
            system.print_status()
        time.sleep(0.01)

    system.stop_operation()


def demo_alkaline_operation():
    """Demonstrate Alkaline electrolyser operation"""
    print("\n" + "="*50)
    print("ALKALINE ELECTROLYSER CONTROL DEMO")
    print("="*50)

    system = ElectrolyserControlSystem(ElectrolyserType.ALKALINE)

    system.start_operation()
    time.sleep(0.5)

    system.set_voltage(24.0)
    system.set_power(4000.0)
    system.electrolyser.transition_mode(OperatingMode.NORMAL)

    # Simulate operation with frequency variation
    for freq in [48.0, 50.0, 52.0, 50.0]:
        system.set_frequency(freq)
        for i in range(20):
            system.electrolyser.update_state(0.1)
            if i % 5 == 0:
                status = system.get_status()
                print(f"Freq: {freq} Hz, Power: {status['power']:.0f}W, H2: {status['hydrogen_produced']:.3f} Nm³")
            time.sleep(0.01)

    system.print_status()
    system.stop_operation()


if __name__ == "__main__":
    # Run demonstrations
    demo_pem_operation()
    time.sleep(2)

    demo_aem_operation()
    time.sleep(2)

    demo_alkaline_operation()

    print("\n✓ All demonstrations completed successfully")
