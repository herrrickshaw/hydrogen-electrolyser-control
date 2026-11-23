import json
import logging

import pytest

import electrolyser_control_system as ecs
from electrolyser_control_system import (
    AEMElectrolyser,
    AlkalineElectrolyser,
    ElectrolyserControlSystem,
    ElectrolyserType,
    InverterConfig,
    InverterController,
    OperatingMode,
    PEMElectrolyser,
    SafetyMonitor,
    VoltageRegulator,
)

ALL_CLASSES = [PEMElectrolyser, AEMElectrolyser, AlkalineElectrolyser]
ALL_TYPES = [ElectrolyserType.PEM, ElectrolyserType.AEM, ElectrolyserType.ALKALINE]


def make_inverter(**kw):
    cfg = dict(rated_power=5000.0, input_voltage_min=200.0, input_voltage_max=240.0,
               output_frequency=50.0, frequency_range=(40.0, 60.0), efficiency=95.0,
               switching_frequency=16000.0)
    cfg.update(kw)
    return InverterController(InverterConfig(**cfg))


@pytest.fixture
def pem():
    return PEMElectrolyser(make_inverter())


# ------------------------------------------------------------------ SafetyMonitor
def test_voltage_limits_are_inclusive_and_alert_outside(pem):
    s = pem.specs
    m = SafetyMonitor(s)
    assert m.check_voltage(s.min_voltage) and m.check_voltage(s.max_voltage)
    assert m.alerts == []
    assert not m.check_voltage(s.min_voltage - 0.1)
    assert not m.check_voltage(s.max_voltage + 0.1)
    assert len(m.alerts) == 2 and "too low" in m.alerts[0] and "too high" in m.alerts[1]


@pytest.mark.parametrize("check,low_attr,high_attr,low_msg,high_msg", [
    ("check_current", "min_current", "max_current", "Current below minimum", "Current too high"),
    ("check_temperature", "temperature_min", "temperature_max", "Temperature below minimum", "Temperature too high"),
    ("check_pressure", "pressure_min", "pressure_max", "Pressure below minimum", "Pressure too high"),
])
def test_other_limits_warn_when_low_and_alert_when_high(pem, check, low_attr, high_attr, low_msg, high_msg):
    s = pem.specs
    m = SafetyMonitor(s)
    fn = getattr(m, check)
    lo, hi = getattr(s, low_attr), getattr(s, high_attr)
    assert fn(lo) and fn(hi) and fn((lo + hi) / 2)
    assert m.alerts == [] and m.warnings == []
    assert fn(lo - 1) is True  # below minimum is only a warning
    assert m.warnings and low_msg in m.warnings[0] and m.alerts == []
    assert fn(hi + 1) is False
    assert high_msg in m.alerts[0]


def test_safety_status_and_clear(pem):
    m = SafetyMonitor(pem.specs)
    assert m.get_status() == {"alerts": [], "warnings": [], "safe": True}
    m.check_voltage(1e6)
    m.check_current(0)
    st = m.get_status()
    assert st["safe"] is False and len(st["alerts"]) == 1 and len(st["warnings"]) == 1
    m.clear()
    assert m.get_status() == {"alerts": [], "warnings": [], "safe": True}


# ------------------------------------------------------------------ InverterController
def test_inverter_enable_disable_and_status():
    inv = make_inverter()
    assert inv.get_status() == {"enabled": False, "frequency": 50.0, "voltage": 0.0, "power": 0.0, "efficiency": 95.0}
    inv.enable()
    assert inv.set_power(1000.0)
    assert inv.get_status()["enabled"] and inv.get_status()["power"] == 1000.0
    inv.disable()
    assert inv.get_status()["enabled"] is False and inv.output_power == 0.0


def test_inverter_frequency_bounds_inclusive():
    inv = make_inverter()
    assert inv.set_frequency(40.0) and inv.set_frequency(60.0) and inv.current_frequency == 60.0
    assert not inv.set_frequency(39.9) and not inv.set_frequency(60.1)
    assert inv.current_frequency == 60.0


def test_inverter_voltage_bounds_inclusive():
    inv = make_inverter()
    assert inv.set_voltage(200.0) and inv.set_voltage(240.0) and inv.current_voltage == 240.0
    assert not inv.set_voltage(199.9) and not inv.set_voltage(240.1)
    assert inv.current_voltage == 240.0


def test_inverter_power_limited_by_rating_inclusive():
    inv = make_inverter(rated_power=1000.0)
    assert inv.set_power(1000.0)
    assert not inv.set_power(1000.1)
    assert inv.output_power == 1000.0


# ------------------------------------------------------------------ VoltageRegulator
def test_regulator_pid_step_matches_the_formula(pem):
    reg = VoltageRegulator(pem.specs, kp=0.1, ki=0.01, kd=0.05)
    out = reg.regulate(45.0, 40.0, dt=0.1)
    error, integral, derivative = 5.0, 5.0 * 0.1, 5.0 / 0.1
    assert out == pytest.approx(40.0 + 0.1 * error + 0.01 * integral + 0.05 * derivative)
    # second step uses the stored error/integral
    out2 = reg.regulate(45.0, out, dt=0.1)
    e2 = 45.0 - out
    i2 = integral + e2 * 0.1
    d2 = (e2 - error) / 0.1
    assert out2 == pytest.approx(out + 0.1 * e2 + 0.01 * i2 + 0.05 * d2)


def test_regulator_clamps_target_and_output_to_spec_range(pem):
    s = pem.specs
    reg = VoltageRegulator(s, kp=100.0, ki=0, kd=0)
    assert reg.regulate(s.max_voltage + 50, s.max_voltage - 1) == s.max_voltage
    reg2 = VoltageRegulator(s, kp=100.0, ki=0, kd=0)
    assert reg2.regulate(s.min_voltage - 50, s.min_voltage + 1) == s.min_voltage


def test_regulator_integral_anti_windup_and_zero_dt(pem):
    reg = VoltageRegulator(pem.specs, kp=0, ki=1.0, kd=0)
    for _ in range(50):
        reg.regulate(pem.specs.max_voltage, pem.specs.min_voltage, dt=1.0)
    assert reg.integral == 10
    reg_neg = VoltageRegulator(pem.specs, kp=0, ki=1.0, kd=0)
    for _ in range(50):
        reg_neg.regulate(pem.specs.min_voltage, pem.specs.max_voltage, dt=1.0)
    assert reg_neg.integral == -10
    z = VoltageRegulator(pem.specs, kp=0, ki=0, kd=5.0)
    assert z.regulate(50.0, 40.0, dt=0) == 40.0  # derivative term skipped for dt == 0


# ------------------------------------------------------------------ electrolyser lifecycle
def test_start_enters_ramp_up_once_and_enables_inverter(pem):
    assert pem.current_mode == OperatingMode.IDLE
    assert pem.start() is True
    assert pem.current_mode == OperatingMode.RAMP_UP and pem.inverter.is_enabled and pem.start_time
    assert pem.start() is False


def test_stop_zeroes_outputs_and_returns_to_idle(pem):
    pem.start()
    pem.set_voltage_setpoint(45.0)
    pem.set_power_setpoint(3000.0)
    assert pem.stop() is True
    assert pem.current_mode == OperatingMode.IDLE
    assert (pem.current_voltage, pem.current_current) == (0.0, 0.0)
    assert pem.inverter.is_enabled is False and pem.inverter.output_power == 0.0


def test_voltage_setpoint_rejects_out_of_range_without_moving(pem):
    assert pem.set_voltage_setpoint(pem.specs.max_voltage + 1) is False
    assert pem.current_voltage == 0.0
    assert pem.safety_monitor.get_status()["safe"] is False


def test_voltage_setpoint_is_one_pid_step_and_warns_when_not_reached(pem, caplog):
    target = 45.0
    with caplog.at_level(logging.WARNING, logger=ecs.logger.name):
        assert pem.set_voltage_setpoint(target) is True
    assert 0.0 < pem.current_voltage < target
    assert any("not reached in one step" in r.message for r in caplog.records)


def test_voltage_setpoint_reaching_target_does_not_warn(pem, caplog):
    pem.current_voltage = 45.0
    pem.voltage_regulator.prev_error = 0.0
    with caplog.at_level(logging.WARNING, logger=ecs.logger.name):
        pem.set_voltage_setpoint(45.0)
    assert pem.current_voltage == pytest.approx(45.0)
    assert not [r for r in caplog.records if "not reached" in r.message]


def test_power_setpoint_derives_current_from_voltage(pem):
    pem.current_voltage = 40.0
    assert pem.set_power_setpoint(2000.0) is True
    assert pem.current_power == 2000.0 and pem.current_current == pytest.approx(50.0)


def test_power_setpoint_without_voltage_leaves_current_zero(pem):
    assert pem.set_power_setpoint(2000.0) is True
    assert pem.current_current == 0.0


def test_power_setpoint_over_nominal_warns_but_over_inverter_rating_is_rejected(pem, caplog):
    nominal = pem.specs.nominal_power
    with caplog.at_level(logging.WARNING, logger=ecs.logger.name):
        assert pem.set_power_setpoint(nominal + 1) is True
    assert any("exceeds nominal" in r.message for r in caplog.records)
    assert pem.set_power_setpoint(pem.inverter.config.rated_power + 1) is False
    assert pem.current_power == nominal + 1


def test_power_setpoint_reports_current_limit_result(pem):
    pem.current_voltage = 1.0  # tiny voltage -> huge current
    assert pem.set_power_setpoint(1000.0) is False
    assert "Current too high" in pem.safety_monitor.alerts[0]


def test_update_state_idle_does_nothing(pem):
    pem.current_power = 1000.0
    pem.update_state(10.0)
    assert pem.hydrogen_produced == 0.0 and pem.run_time == 0.0


def test_update_state_tracks_run_time_from_wall_clock(pem, monkeypatch):
    pem.start()
    pem.start_time = 1000.0
    monkeypatch.setattr(ecs.time, "time", lambda: 1012.5)
    pem.update_state(1.0)
    assert pem.run_time == 12.5


def test_production_only_in_normal_mode_and_scales_with_load(pem):
    s = pem.specs
    pem.start()
    pem.current_power = s.nominal_power
    pem.update_state(3600.0)  # ramp-up: no production
    assert pem.hydrogen_produced == 0.0
    pem.transition_mode(OperatingMode.NORMAL)
    pem.update_state(3600.0)  # one hour at nominal power = one hour of nominal rate
    assert pem.hydrogen_produced == pytest.approx(s.hydrogen_production_rate)
    assert pem.oxygen_produced == pytest.approx(s.oxygen_production_rate)
    assert pem.water_consumed == pytest.approx(s.water_consumption_rate)
    pem.hydrogen_produced = 0.0
    pem.current_power = s.nominal_power / 2
    pem.update_state(3600.0)
    assert pem.hydrogen_produced == pytest.approx(s.hydrogen_production_rate / 2)


def test_no_production_at_zero_power_even_in_normal_mode(pem):
    pem.start()
    pem.transition_mode(OperatingMode.NORMAL)
    pem.update_state(3600.0)
    assert pem.hydrogen_produced == 0.0


@pytest.mark.parametrize("start_mode,target,ok,end_mode", [
    (OperatingMode.RAMP_UP, OperatingMode.NORMAL, True, OperatingMode.NORMAL),
    (OperatingMode.IDLE, OperatingMode.NORMAL, False, OperatingMode.IDLE),
    (OperatingMode.RAMP_DOWN, OperatingMode.NORMAL, False, OperatingMode.RAMP_DOWN),
    (OperatingMode.FAULT, OperatingMode.NORMAL, False, OperatingMode.FAULT),
    (OperatingMode.NORMAL, OperatingMode.NORMAL, False, OperatingMode.NORMAL),
    (OperatingMode.NORMAL, OperatingMode.RAMP_DOWN, True, OperatingMode.RAMP_DOWN),
    (OperatingMode.NORMAL, OperatingMode.IDLE, True, OperatingMode.IDLE),
    (OperatingMode.NORMAL, OperatingMode.FAULT, False, OperatingMode.NORMAL),
    (OperatingMode.NORMAL, OperatingMode.STANDBY, False, OperatingMode.NORMAL),
    (OperatingMode.NORMAL, OperatingMode.SHUTDOWN, False, OperatingMode.NORMAL),
])
def test_transition_mode(pem, start_mode, target, ok, end_mode):
    pem.current_mode = start_mode
    assert pem.transition_mode(target) is ok
    assert pem.current_mode == end_mode


def test_status_dict_shape_and_values(pem):
    pem.start()
    st = pem.get_status()
    assert st["type"] == "PEM" and st["mode"] == "RAMP_UP"
    assert st["inverter"]["enabled"] is True and st["safety"]["safe"] is True
    assert set(st) == {"type", "mode", "voltage", "current", "power", "temperature", "pressure",
                       "efficiency", "hydrogen_produced", "oxygen_produced", "water_consumed",
                       "run_time", "inverter", "safety"}


# ------------------------------------------------------------------ per-type specs and efficiency
@pytest.mark.parametrize("cls,etype", list(zip(ALL_CLASSES, ALL_TYPES)))
def test_each_type_has_consistent_specs(cls, etype):
    s = cls(make_inverter()).specs
    assert s.type == etype
    assert s.min_voltage < s.nominal_voltage < s.max_voltage
    assert s.min_current < s.nominal_current < s.max_current
    assert s.min_efficiency < s.max_efficiency
    assert s.temperature_min < s.temperature_max and s.pressure_min < s.pressure_max
    # nominal power is the nominal voltage times the nominal current
    assert s.nominal_voltage * s.nominal_current == pytest.approx(s.nominal_power)


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_efficiency_zero_at_zero_power_linear_in_load_and_capped(cls):
    e = cls(make_inverter())
    s = e.specs
    assert e.calculate_efficiency() == 0.0
    e.current_power = s.nominal_power / 2
    assert e.calculate_efficiency() == pytest.approx((s.min_efficiency + s.max_efficiency) / 2)
    e.current_power = s.nominal_power
    assert e.calculate_efficiency() == pytest.approx(s.max_efficiency)
    e.current_power = s.nominal_power * 3
    assert e.calculate_efficiency() == s.max_efficiency


# ------------------------------------------------------------------ ElectrolyserControlSystem
@pytest.mark.parametrize("etype,cls", list(zip(ALL_TYPES, ALL_CLASSES)))
def test_control_system_builds_the_requested_type(etype, cls):
    cs = ElectrolyserControlSystem(etype)
    assert isinstance(cs.electrolyser, cls)
    assert cs.log_file == f"electrolyser_{etype.value.lower()}_log.json"


@pytest.mark.parametrize("etype", [ElectrolyserType.SOEC, ElectrolyserType.CUSTOM])
def test_control_system_rejects_unsupported_types(etype):
    with pytest.raises(ValueError, match="Unsupported electrolyser type"):
        ElectrolyserControlSystem(etype)


def test_default_type_is_pem():
    assert isinstance(ElectrolyserControlSystem().electrolyser, PEMElectrolyser)


def test_start_and_stop_operation_and_log_file(tmp_path):
    cs = ElectrolyserControlSystem()
    assert cs.start_operation() is True
    assert cs.start_operation() is False
    cs.operation_log.append({"k": 1})
    assert cs.stop_operation() is True
    assert json.loads((tmp_path / "electrolyser_pem_log.json").read_text()) == [{"k": 1}]
    assert cs.electrolyser.current_mode == OperatingMode.IDLE


def test_setters_delegate_to_components():
    cs = ElectrolyserControlSystem()
    assert cs.set_frequency(55.0) and cs.inverter.current_frequency == 55.0
    assert not cs.set_frequency(70.0)
    assert cs.set_power(1000.0) and cs.electrolyser.current_power == 1000.0
    assert not cs.set_power(1e6)
    assert cs.set_voltage(45.0) and cs.electrolyser.current_voltage > 0
    assert cs.get_status()["type"] == "PEM" and cs.get_status()["power"] == 1000.0


def test_ramp_to_power_steps_logs_and_enters_normal_mode():
    cs = ElectrolyserControlSystem()
    cs.start_operation()
    cs.ramp_to_power(target_power=1000.0, ramp_rate=300.0, dt=1.0)
    # 300, 600, 900, then clipped to 1000
    assert len(cs.operation_log) == 4
    assert [e["status"]["power"] for e in cs.operation_log] == [300.0, 600.0, 900.0, 1000.0]
    assert cs.electrolyser.current_mode == OperatingMode.NORMAL


def test_ramp_to_power_zero_target_does_nothing_but_transition():
    cs = ElectrolyserControlSystem()
    cs.start_operation()
    cs.ramp_to_power(target_power=0.0)
    assert cs.operation_log == []
    assert cs.electrolyser.current_mode == OperatingMode.NORMAL


def test_ramp_to_voltage_moves_up_and_stops_at_or_above_target():
    cs = ElectrolyserControlSystem()
    cs.start_operation()
    cs.ramp_to_voltage(target_voltage=40.0, ramp_rate=10.0, dt=1.0)
    assert cs.electrolyser.current_voltage > 0
    cs.electrolyser.current_voltage = 50.0
    cs.ramp_to_voltage(target_voltage=40.0)  # already above: loop body never runs
    assert cs.electrolyser.current_voltage == 50.0


def test_print_status_safe_and_alert_layouts(capsys):
    cs = ElectrolyserControlSystem()
    cs.print_status()
    out = capsys.readouterr().out
    assert "ELECTROLYSER STATUS - PEM" in out and "Safety Status: SAFE" in out and "Mode: IDLE" in out
    cs.set_voltage(1e6)
    cs.print_status()
    out = capsys.readouterr().out
    assert "Safety Status: ALERT" in out and "Voltage too high" in out


@pytest.mark.parametrize("demo,marker", [
    (ecs.demo_pem_operation, "PEM ELECTROLYSER CONTROL DEMO"),
    (ecs.demo_aem_operation, "AEM ELECTROLYSER CONTROL DEMO"),
    (ecs.demo_alkaline_operation, "ALKALINE ELECTROLYSER CONTROL DEMO"),
])
def test_demos_run_end_to_end(demo, marker, capsys):
    demo()
    out = capsys.readouterr().out
    assert marker in out and "ELECTROLYSER STATUS" in out


def test_abstract_efficiency_hook_has_no_default_value(pem):
    assert ecs.ElectrolyserBase.calculate_efficiency(pem) is None
    with pytest.raises(TypeError):
        ecs.ElectrolyserBase(pem.specs, make_inverter())


def test_stop_operation_reports_false_and_skips_the_log_when_the_stop_fails(monkeypatch, tmp_path):
    cs = ElectrolyserControlSystem()
    monkeypatch.setattr(cs.electrolyser, "stop", lambda: False)
    assert cs.stop_operation() is False
    assert not (tmp_path / cs.log_file).exists()


def test_small_but_real_shortfall_still_warns(pem, caplog):
    pem.current_voltage = 44.5  # one PID step lands about 0.2 V short of 45 V
    with caplog.at_level(logging.WARNING, logger=ecs.logger.name):
        pem.set_voltage_setpoint(45.0)
    assert 0.01 < abs(pem.current_voltage - 45.0) < 1.0
    assert any("not reached in one step" in r.message for r in caplog.records)


def test_power_exactly_nominal_does_not_warn(pem, caplog):
    with caplog.at_level(logging.WARNING, logger=ecs.logger.name):
        pem.set_power_setpoint(pem.specs.nominal_power)
    assert not [r for r in caplog.records if "exceeds nominal" in r.message]


def test_ramp_to_voltage_never_requests_more_than_the_target():
    cs = ElectrolyserControlSystem()
    cs.start_operation()
    asked = []
    orig = cs.set_voltage
    cs.set_voltage = lambda v: (asked.append(v), orig(v))[1]
    cs.ramp_to_voltage(target_voltage=25.0, ramp_rate=10.0, dt=1.0)
    assert asked == [10.0, 20.0, 25.0]
