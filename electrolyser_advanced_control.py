"""
Advanced Hydrogen Electrolyser Control Interface
Includes scheduling, real-time monitoring, and advanced safety features
"""

import threading
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from electrolyser_control_system import (
    ElectrolyserControlSystem,
    ElectrolyserType,
    OperatingMode,
    VoltageRegulator
)

logger = logging.getLogger(__name__)


class RampProfile(Enum):
    """Predefined ramp profiles"""
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"
    LOGARITHMIC = "LOGARITHMIC"
    STEP = "STEP"
    CUSTOM = "CUSTOM"


@dataclass
class RampSchedule:
    """Schedule for power/voltage ramping"""
    start_value: float
    end_value: float
    duration_seconds: float
    profile: RampProfile
    start_time: Optional[datetime] = None

    def get_value_at_time(self, elapsed_seconds: float) -> float:
        """Calculate value at given elapsed time"""
        if elapsed_seconds >= self.duration_seconds:
            return self.end_value

        progress = elapsed_seconds / self.duration_seconds

        if self.profile == RampProfile.LINEAR:
            return self.start_value + (self.end_value - self.start_value) * progress

        elif self.profile == RampProfile.EXPONENTIAL:
            # Exponential ramp
            exp_val = (2.718 ** (progress * 2) - 1) / (2.718 ** 2 - 1)
            return self.start_value + (self.end_value - self.start_value) * exp_val

        elif self.profile == RampProfile.LOGARITHMIC:
            # Logarithmic ramp (slower at start, faster at end)
            log_val = np.log(progress + 1) / np.log(2)
            return self.start_value + (self.end_value - self.start_value) * log_val

        elif self.profile == RampProfile.STEP:
            # Step increase halfway
            if progress < 0.5:
                return self.start_value
            else:
                return self.end_value

        return self.start_value


@dataclass
class OperationEvent:
    """Single operation event for logging"""
    timestamp: datetime
    mode: str
    voltage: float
    current: float
    power: float
    temperature: float
    pressure: float
    efficiency: float
    hydrogen_produced: float
    oxygen_produced: float
    water_consumed: float
    event_type: str  # 'normal', 'warning', 'alert', 'transition'
    message: Optional[str] = None


class DataLogger:
    """Logs electrolyser operation data to CSV and JSON"""

    def __init__(self, prefix: str = "electrolyser"):
        self.prefix = prefix
        self.csv_file = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.json_file = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        self.events: List[OperationEvent] = []
        self.csv_headers = None

        logger.info(f"DataLogger initialized: {self.csv_file}")

    def log_event(self, event: OperationEvent):
        """Log a single event"""
        self.events.append(event)

        # Append to CSV
        if self.csv_headers is None:
            self.csv_headers = [
                'timestamp', 'mode', 'voltage', 'current', 'power',
                'temperature', 'pressure', 'efficiency', 'hydrogen_produced',
                'oxygen_produced', 'water_consumed', 'event_type', 'message'
            ]
            self._write_csv_headers()

        self._append_to_csv(event)

    def _write_csv_headers(self):
        """Write CSV headers"""
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.csv_headers)

    def _append_to_csv(self, event: OperationEvent):
        """Append event to CSV"""
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                event.timestamp.isoformat(),
                event.mode,
                f"{event.voltage:.2f}",
                f"{event.current:.2f}",
                f"{event.power:.2f}",
                f"{event.temperature:.2f}",
                f"{event.pressure:.2f}",
                f"{event.efficiency:.2f}",
                f"{event.hydrogen_produced:.4f}",
                f"{event.oxygen_produced:.4f}",
                f"{event.water_consumed:.2f}",
                event.event_type,
                event.message or ""
            ])

    def save_json(self):
        """Save all events to JSON"""
        events_dict = [
            {
                **{k: v.isoformat() if isinstance(v, datetime) else v
                   for k, v in asdict(event).items()}
            }
            for event in self.events
        ]

        with open(self.json_file, 'w') as f:
            json.dump({
                "total_events": len(self.events),
                "start_time": self.events[0].timestamp.isoformat() if self.events else None,
                "end_time": self.events[-1].timestamp.isoformat() if self.events else None,
                "events": events_dict
            }, f, indent=2)

        logger.info(f"JSON log saved: {self.json_file}")

    def get_summary(self) -> Dict:
        """Get operation summary"""
        if not self.events:
            return {}

        voltages = [e.voltage for e in self.events]
        currents = [e.current for e in self.events]
        powers = [e.power for e in self.events]
        efficiencies = [e.efficiency for e in self.events if e.efficiency > 0]

        return {
            "total_events": len(self.events),
            "duration_seconds": (self.events[-1].timestamp - self.events[0].timestamp).total_seconds(),
            "voltage_avg": sum(voltages) / len(voltages),
            "voltage_min": min(voltages),
            "voltage_max": max(voltages),
            "current_avg": sum(currents) / len(currents),
            "current_min": min(currents),
            "current_max": max(currents),
            "power_avg": sum(powers) / len(powers),
            "power_min": min(powers),
            "power_max": max(powers),
            "efficiency_avg": sum(efficiencies) / len(efficiencies) if efficiencies else 0,
            "total_hydrogen": self.events[-1].hydrogen_produced,
            "total_oxygen": self.events[-1].oxygen_produced,
            "total_water_consumed": self.events[-1].water_consumed,
            "alerts": len([e for e in self.events if e.event_type == 'alert']),
            "warnings": len([e for e in self.events if e.event_type == 'warning'])
        }


class SafetyInterlocks:
    """Advanced safety interlock system"""

    def __init__(self):
        self.interlocks_enabled = True
        self.emergency_stop = False
        self.callbacks: List[Callable] = []

    def register_callback(self, callback: Callable):
        """Register callback for safety events"""
        self.callbacks.append(callback)

    def trigger_emergency_stop(self, reason: str):
        """Trigger emergency stop"""
        logger.critical(f"EMERGENCY STOP triggered: {reason}")
        self.emergency_stop = True

        for callback in self.callbacks:
            try:
                callback("emergency_stop", reason)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def check_voltage_ramp_rate(self, current_voltage: float, previous_voltage: float, dt: float, max_rate: float = 5.0) -> bool:
        """Check if voltage ramp rate is safe"""
        if dt == 0:
            return True

        ramp_rate = abs(current_voltage - previous_voltage) / dt

        if ramp_rate > max_rate:
            self.trigger_emergency_stop(f"Voltage ramp rate {ramp_rate:.2f} V/s exceeds limit {max_rate:.2f} V/s")
            return False

        return True

    def check_current_jump(self, current_current: float, previous_current: float, max_jump: float = 50.0) -> bool:
        """Check for sudden current jumps (possible short circuit)"""
        jump = abs(current_current - previous_current)

        if jump > max_jump:
            self.trigger_emergency_stop(f"Current jump {jump:.2f}A detected - possible fault")
            return False

        return True

    def clear_emergency_stop(self):
        """Clear emergency stop condition"""
        logger.info("Emergency stop cleared")
        self.emergency_stop = False


class AdvancedElectrolyserController:
    """Advanced controller with scheduling and monitoring"""

    def __init__(self, electrolyser_type: ElectrolyserType = ElectrolyserType.PEM):
        self.system = ElectrolyserControlSystem(electrolyser_type)
        self.logger = DataLogger(prefix=f"electrolyser_{electrolyser_type.value.lower()}")
        self.safety_interlocks = SafetyInterlocks()

        self.is_running = False
        self.control_thread = None

        self.power_schedule: Optional[RampSchedule] = None
        self.voltage_schedule: Optional[RampSchedule] = None

        self.last_status = None
        self.update_interval = 0.1  # seconds

        logger.info(f"AdvancedElectrolyserController initialized")

    def register_safety_callback(self, callback: Callable):
        """Register callback for safety events"""
        self.safety_interlocks.register_callback(callback)

    def set_power_ramp(self, start_power: float, end_power: float, duration: float, profile: RampProfile = RampProfile.LINEAR):
        """Set power ramp schedule"""
        self.power_schedule = RampSchedule(start_power, end_power, duration, profile)
        logger.info(f"Power ramp set: {start_power}W → {end_power}W over {duration}s ({profile.value})")

    def set_voltage_ramp(self, start_voltage: float, end_voltage: float, duration: float, profile: RampProfile = RampProfile.LINEAR):
        """Set voltage ramp schedule"""
        self.voltage_schedule = RampSchedule(start_voltage, end_voltage, duration, profile)
        logger.info(f"Voltage ramp set: {start_voltage}V → {end_voltage}V over {duration}s ({profile.value})")

    def start(self):
        """Start control system"""
        self.system.start_operation()
        self.is_running = True
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
        logger.info("Advanced controller started")

    def stop(self):
        """Stop control system"""
        self.is_running = False
        self.system.stop_operation()

        if self.control_thread:
            self.control_thread.join(timeout=5)

        self.logger.save_json()
        summary = self.logger.get_summary()
        logger.info(f"Operation summary: {json.dumps(summary, indent=2)}")

    def _control_loop(self):
        """Main control loop running in separate thread"""
        start_time = datetime.now()

        while self.is_running:
            elapsed = (datetime.now() - start_time).total_seconds()

            # Apply schedules if active
            if self.power_schedule and elapsed <= self.power_schedule.duration_seconds:
                target_power = self.power_schedule.get_value_at_time(elapsed)
                self.system.set_power(target_power)

            if self.voltage_schedule and elapsed <= self.voltage_schedule.duration_seconds:
                target_voltage = self.voltage_schedule.get_value_at_time(elapsed)
                self.system.set_voltage(target_voltage)

            # Update state
            self.system.electrolyser.update_state(self.update_interval)

            # Get status
            status = self.system.get_status()
            self.last_status = status

            # Log event
            safety = status['safety']
            event_type = 'alert' if not safety['safe'] else 'normal'

            event = OperationEvent(
                timestamp=datetime.now(),
                mode=status['mode'],
                voltage=status['voltage'],
                current=status['current'],
                power=status['power'],
                temperature=status['temperature'],
                pressure=status['pressure'],
                efficiency=status['efficiency'],
                hydrogen_produced=status['hydrogen_produced'],
                oxygen_produced=status['oxygen_produced'],
                water_consumed=status['water_consumed'],
                event_type=event_type,
                message=safety['alerts'][0] if safety['alerts'] else None
            )

            self.logger.log_event(event)

            # Check safety interlocks
            if safety['alerts']:
                logger.warning(f"Safety alert: {safety['alerts']}")

            import time
            time.sleep(self.update_interval)

    def get_real_time_status(self) -> Dict:
        """Get real-time status"""
        return self.last_status

    def print_live_status(self, interval: float = 1.0):
        """Print live status updates"""
        try:
            while self.is_running:
                status = self.get_real_time_status()
                if status:
                    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                          f"V:{status['voltage']:.1f}V | "
                          f"I:{status['current']:.1f}A | "
                          f"P:{status['power']:.0f}W | "
                          f"Eff:{status['efficiency']:.1f}% | "
                          f"H2:{status['hydrogen_produced']:.3f}Nm³", end='')
                import time
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n")

    def export_report(self, filename: str = "electrolyser_report.json"):
        """Export comprehensive report"""
        summary = self.logger.get_summary()

        report = {
            "timestamp": datetime.now().isoformat(),
            "electrolyser_type": self.system.electrolyser.specs.type.value,
            "summary": summary,
            "final_status": self.last_status,
            "csv_log": self.logger.csv_file,
            "json_log": self.logger.json_file
        }

        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report exported: {filename}")
        return report


# Example numpy import for advanced ramp profiles
try:
    import numpy as np
except ImportError:
    np = None
    logger.warning("NumPy not available - some ramp profiles may not work")


def demo_advanced_control():
    """Demonstrate advanced control features"""
    print("\n" + "="*70)
    print("ADVANCED ELECTROLYSER CONTROL DEMONSTRATION")
    print("="*70)

    controller = AdvancedElectrolyserController(ElectrolyserType.PEM)

    # Register safety callback
    def safety_alert(event_type: str, message: str):
        print(f"\n🚨 SAFETY EVENT: {event_type} - {message}")

    controller.register_safety_callback(safety_alert)

    # Start controller
    controller.start()

    # Set ramp schedules
    controller.set_voltage_ramp(30.0, 48.0, duration=10.0, profile=RampProfile.LINEAR)
    controller.set_power_ramp(1000.0, 4000.0, duration=15.0, profile=RampProfile.EXPONENTIAL)

    # Monitor for 20 seconds
    print("\nRunning controlled ramp-up sequence...")
    controller.print_live_status(interval=0.5)

    # Stop and generate report
    controller.stop()

    # Export report
    report = controller.export_report("demo_report.json")

    print("\n" + "="*70)
    print("OPERATION SUMMARY")
    print("="*70)
    summary = report['summary']
    print(f"Duration: {summary['duration_seconds']:.1f} seconds")
    print(f"Power: {summary['power_avg']:.0f}W avg ({summary['power_min']:.0f}W - {summary['power_max']:.0f}W)")
    print(f"Voltage: {summary['voltage_avg']:.2f}V avg ({summary['voltage_min']:.2f}V - {summary['voltage_max']:.2f}V)")
    print(f"Efficiency: {summary['efficiency_avg']:.1f}%")
    print(f"Hydrogen produced: {summary['total_hydrogen']:.3f} Nm³")
    print(f"Oxygen produced: {summary['total_oxygen']:.3f} Nm³")
    print(f"Water consumed: {summary['total_water_consumed']:.2f} L")
    print(f"Alerts: {summary['alerts']}, Warnings: {summary['warnings']}")
    print("="*70 + "\n")


if __name__ == "__main__":
    demo_advanced_control()
