"""Unit tests for pure/local logic: safety limits, inverter limits, PID clamp, ramp shapes, loggers."""
import csv
from datetime import datetime

import pytest

from electrolyser_advanced_control import (
    DataLogger,
    OperationEvent,
    RampProfile,
    RampSchedule,
    SafetyInterlocks,
)
from electrolyser_control_system import (
    ElectrolyserControlSystem,
    ElectrolyserType,
    OperatingMode,
)


def make(kind=ElectrolyserType.PEM):
    return ElectrolyserControlSystem(kind)


def test_unsupported_type_rejected():
    with pytest.raises(ValueError):
        ElectrolyserControlSystem(ElectrolyserType.SOEC)


@pytest.mark.parametrize("kind,nominal", [
    (ElectrolyserType.PEM, 48.0), (ElectrolyserType.AEM, 40.0), (ElectrolyserType.ALKALINE, 24.0)])
def test_nominal_specs(kind, nominal):
    assert make(kind).electrolyser.specs.nominal_voltage == nominal


def test_safety_limits_pem():
    mon = make().electrolyser.safety_monitor
    assert mon.check_voltage(45) and not mon.check_voltage(61) and not mon.check_voltage(29)
    assert mon.check_current(5) and not mon.check_current(151)   # below-min is a warning only
    assert mon.check_temperature(81) is False and mon.check_pressure(36) is False
    assert mon.get_status()["safe"] is False
    mon.clear()
    assert mon.get_status() == {"alerts": [], "warnings": [], "safe": True}


def test_inverter_limits():
    inv = make().inverter
    assert inv.set_frequency(40.0) and inv.set_frequency(60.0)
    assert not inv.set_frequency(39.99) and not inv.set_frequency(60.01)
    assert not inv.set_power(5000.01)


def test_pid_output_stays_in_voltage_band():
    reg = make().electrolyser.voltage_regulator
    lo, hi = reg.specs.min_voltage, reg.specs.max_voltage
    v = 40.0
    for _ in range(100):
        v = reg.regulate(1e6, v)
        assert lo <= v <= hi
    assert -10 <= reg.integral <= 10


def test_start_stop_state_machine():
    system = make()
    assert system.electrolyser.current_mode is OperatingMode.IDLE
    assert system.start_operation() and not system.start_operation()
    assert system.electrolyser.transition_mode(OperatingMode.NORMAL)
    assert not system.electrolyser.transition_mode(OperatingMode.FAULT)
    system.electrolyser.stop()
    assert system.electrolyser.current_mode is OperatingMode.IDLE


def test_efficiency_is_load_linear_and_capped():
    e = make().electrolyser
    assert e.calculate_efficiency() == 0.0
    e.current_power = e.specs.nominal_power / 2
    assert e.calculate_efficiency() == pytest.approx(67.5)
    e.current_power = e.specs.nominal_power * 3
    assert e.calculate_efficiency() == e.specs.max_efficiency


@pytest.mark.parametrize("profile", [RampProfile.LINEAR, RampProfile.EXPONENTIAL,
                                     RampProfile.LOGARITHMIC, RampProfile.STEP])
def test_ramp_endpoints(profile):
    rs = RampSchedule(10.0, 20.0, 10.0, profile)
    assert rs.get_value_at_time(10.0) == 20.0 and rs.get_value_at_time(99.0) == 20.0
    assert rs.get_value_at_time(0.0) == 10.0


def test_custom_profile_holds_start_value():
    assert RampSchedule(1.0, 5.0, 10.0, RampProfile.CUSTOM).get_value_at_time(5.0) == 1.0


def test_interlock_callbacks_and_flag():
    il = SafetyInterlocks()
    seen = []
    il.register_callback(lambda kind, why: seen.append(kind))
    assert il.check_voltage_ramp_rate(40, 40, 1.0)
    assert not il.check_current_jump(100, 0)
    assert il.emergency_stop and seen == ["emergency_stop"]
    il.clear_emergency_stop()
    assert not il.emergency_stop


def test_data_logger_csv_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dl = DataLogger("t")
    ev = OperationEvent(datetime(2026, 1, 1), "NORMAL", 1, 2, 3, 4, 5, 6, 7, 8, 9, "normal")
    dl.log_event(ev)
    rows = list(csv.reader(open(dl.csv_file)))
    assert rows[0][0] == "timestamp" and rows[1][2] == "1.00"
    assert dl.get_summary()["total_events"] == 1


def test_examples_module_imports():
    import electrolyser_examples

    assert callable(electrolyser_examples.main)
