import csv
import json
import math
import threading
import time
from datetime import datetime, timedelta

import pytest

import electrolyser_advanced_control as eac
from electrolyser_advanced_control import (
    AdvancedElectrolyserController,
    DataLogger,
    OperationEvent,
    RampProfile,
    RampSchedule,
    SafetyInterlocks,
)
from electrolyser_control_system import ElectrolyserType

T0 = datetime(2026, 1, 1, 12, 0, 0)


def event(i=0, **kw):
    d = dict(timestamp=T0 + timedelta(seconds=i), mode="NORMAL", voltage=40.0, current=50.0, power=2000.0,
             temperature=25.0, pressure=1.0, efficiency=60.0, hydrogen_produced=0.5, oxygen_produced=0.25,
             water_consumed=0.4, event_type="normal", message=None)
    d.update(kw)
    return OperationEvent(**d)


# ------------------------------------------------------------------ RampSchedule
def sched(profile, a=100.0, b=300.0, d=10.0):
    return RampSchedule(a, b, d, profile)


@pytest.mark.parametrize("profile", [p for p in RampProfile])
def test_every_profile_returns_end_value_at_and_after_duration(profile):
    s = sched(profile)
    assert s.get_value_at_time(10.0) == 300.0
    assert s.get_value_at_time(99.0) == 300.0


def test_linear_ramp_is_proportional():
    s = sched(RampProfile.LINEAR)
    assert s.get_value_at_time(0.0) == 100.0
    assert s.get_value_at_time(5.0) == pytest.approx(200.0)
    assert s.get_value_at_time(2.5) == pytest.approx(150.0)


def test_linear_ramp_can_descend():
    s = RampSchedule(300.0, 100.0, 10.0, RampProfile.LINEAR)
    assert s.get_value_at_time(5.0) == pytest.approx(200.0)


def test_exponential_ramp_is_convex_and_hits_the_endpoints():
    s = sched(RampProfile.EXPONENTIAL)
    assert s.get_value_at_time(0.0) == pytest.approx(100.0)
    half = s.get_value_at_time(5.0)
    expected = 100.0 + 200.0 * (math.e ** 1 - 1) / (math.e ** 2 - 1)
    assert half == pytest.approx(expected, rel=1e-3)
    assert half < 200.0  # below the straight line: slow start, fast finish


def test_logarithmic_ramp_follows_log2_of_one_plus_progress():
    s = sched(RampProfile.LOGARITHMIC)
    assert s.get_value_at_time(0.0) == pytest.approx(100.0)
    assert s.get_value_at_time(5.0) == pytest.approx(100.0 + 200.0 * math.log2(1.5))


@pytest.mark.xfail(strict=True, reason="the comment says the logarithmic ramp is slower at the start, "
                   "but log2(1 + progress) rises faster than a straight line at the start")
def test_logarithmic_ramp_is_slower_than_linear_at_the_start():
    assert sched(RampProfile.LOGARITHMIC).get_value_at_time(2.0) < sched(RampProfile.LINEAR).get_value_at_time(2.0)


def test_logarithmic_ramp_needs_numpy(monkeypatch):
    monkeypatch.setattr(eac, "np", None)
    with pytest.raises(AttributeError):
        sched(RampProfile.LOGARITHMIC).get_value_at_time(1.0)


def test_step_ramp_jumps_at_half_duration():
    s = sched(RampProfile.STEP)
    assert s.get_value_at_time(4.99) == 100.0
    assert s.get_value_at_time(5.0) == 300.0


def test_custom_profile_holds_the_start_value():
    assert sched(RampProfile.CUSTOM).get_value_at_time(3.0) == 100.0


# ------------------------------------------------------------------ DataLogger
def test_logger_writes_header_once_then_formatted_rows(tmp_path):
    lg = DataLogger(prefix="t")
    lg.log_event(event(0, message="hello"))
    lg.log_event(event(1, voltage=41.234, efficiency=0.0, event_type="warning"))
    rows = list(csv.reader(open(lg.csv_file)))
    assert rows[0][:5] == ["timestamp", "mode", "voltage", "current", "power"] and len(rows[0]) == 13
    assert len(rows) == 3
    assert rows[1] == ["2026-01-01T12:00:00", "NORMAL", "40.00", "50.00", "2000.00", "25.00", "1.00",
                       "60.00", "0.5000", "0.2500", "0.40", "normal", "hello"]
    assert rows[2][2] == "41.23" and rows[2][-1] == ""
    assert lg.csv_file.startswith("t_") and lg.csv_file.endswith(".csv")
    assert lg.json_file.endswith(".json")


def test_logger_json_round_trip_and_empty(tmp_path):
    lg = DataLogger(prefix="j")
    lg.save_json()
    empty = json.load(open(lg.json_file))
    assert empty == {"total_events": 0, "start_time": None, "end_time": None, "events": []}
    lg.log_event(event(0))
    lg.log_event(event(5, voltage=42.0))
    lg.save_json()
    data = json.load(open(lg.json_file))
    assert data["total_events"] == 2
    assert data["start_time"] == "2026-01-01T12:00:00" and data["end_time"] == "2026-01-01T12:00:05"
    assert data["events"][1]["voltage"] == 42.0 and data["events"][0]["timestamp"] == "2026-01-01T12:00:00"


def test_summary_empty_is_empty_dict():
    assert DataLogger(prefix="s").get_summary() == {}


def test_summary_statistics():
    lg = DataLogger(prefix="s")
    lg.log_event(event(0, voltage=30.0, current=10.0, power=1000.0, efficiency=0.0))
    lg.log_event(event(10, voltage=50.0, current=30.0, power=3000.0, efficiency=60.0, hydrogen_produced=1.0,
                       oxygen_produced=0.5, water_consumed=0.8, event_type="alert"))
    lg.log_event(event(20, voltage=40.0, current=20.0, power=2000.0, efficiency=70.0, hydrogen_produced=2.0,
                       oxygen_produced=1.0, water_consumed=1.6, event_type="warning"))
    s = lg.get_summary()
    assert s["total_events"] == 3 and s["duration_seconds"] == 20.0
    assert (s["voltage_avg"], s["voltage_min"], s["voltage_max"]) == (40.0, 30.0, 50.0)
    assert (s["current_avg"], s["current_min"], s["current_max"]) == (20.0, 10.0, 30.0)
    assert (s["power_avg"], s["power_min"], s["power_max"]) == (2000.0, 1000.0, 3000.0)
    assert s["efficiency_avg"] == 65.0  # zero-efficiency (idle) samples are excluded
    assert (s["total_hydrogen"], s["total_oxygen"], s["total_water_consumed"]) == (2.0, 1.0, 1.6)
    assert (s["alerts"], s["warnings"]) == (1, 1)


def test_summary_efficiency_zero_when_no_positive_samples():
    lg = DataLogger(prefix="s")
    lg.log_event(event(0, efficiency=0.0))
    assert lg.get_summary()["efficiency_avg"] == 0


# ------------------------------------------------------------------ SafetyInterlocks
def test_ramp_rate_limit_triggers_emergency_stop_and_callbacks():
    si = SafetyInterlocks()
    calls = []
    si.register_callback(lambda kind, reason: calls.append((kind, reason)))
    assert si.check_voltage_ramp_rate(45.0, 40.0, dt=1.0, max_rate=5.0) is True  # exactly at the limit
    assert si.emergency_stop is False and calls == []
    assert si.check_voltage_ramp_rate(46.0, 40.0, dt=1.0, max_rate=5.0) is False
    assert si.emergency_stop is True
    assert calls[0][0] == "emergency_stop" and "6.00 V/s exceeds limit 5.00 V/s" in calls[0][1]


def test_ramp_rate_ignores_zero_dt_and_checks_both_directions():
    si = SafetyInterlocks()
    assert si.check_voltage_ramp_rate(100.0, 0.0, dt=0) is True and not si.emergency_stop
    assert si.check_voltage_ramp_rate(40.0, 46.0, dt=1.0) is False


def test_current_jump_limit():
    si = SafetyInterlocks()
    assert si.check_current_jump(150.0, 100.0) is True
    assert si.check_current_jump(100.0, 151.0) is False and si.emergency_stop
    assert si.check_current_jump(0.0, 10.0, max_jump=5.0) is False


def test_failing_callback_does_not_block_the_others():
    si = SafetyInterlocks()
    seen = []

    def bad(kind, reason):
        raise RuntimeError("boom")

    si.register_callback(bad)
    si.register_callback(lambda kind, reason: seen.append(reason))
    si.trigger_emergency_stop("why")
    assert seen == ["why"] and si.emergency_stop is True


def test_clear_emergency_stop():
    si = SafetyInterlocks()
    si.trigger_emergency_stop("x")
    si.clear_emergency_stop()
    assert si.emergency_stop is False


# ------------------------------------------------------------------ AdvancedElectrolyserController
def one_iteration(ctrl, monkeypatch):
    """Run _control_loop for exactly one pass: the sleep at the end of the pass stops it."""
    def stop_after_sleep(seconds):
        ctrl.is_running = False

    ctrl.is_running = True
    monkeypatch.setattr(time, "sleep", stop_after_sleep)
    ctrl._control_loop()


def test_controller_defaults():
    c = AdvancedElectrolyserController(ElectrolyserType.AEM)
    assert c.system.electrolyser.specs.type == ElectrolyserType.AEM
    assert c.is_running is False and c.last_status is None and c.update_interval == 0.1
    assert c.logger.csv_file.startswith("electrolyser_aem_")
    assert c.get_real_time_status() is None


def test_set_ramps_store_schedules():
    c = AdvancedElectrolyserController()
    c.set_power_ramp(1000.0, 4000.0, 15.0, RampProfile.EXPONENTIAL)
    c.set_voltage_ramp(30.0, 48.0, 10.0)
    assert (c.power_schedule.start_value, c.power_schedule.end_value, c.power_schedule.duration_seconds,
            c.power_schedule.profile) == (1000.0, 4000.0, 15.0, RampProfile.EXPONENTIAL)
    assert c.voltage_schedule.profile == RampProfile.LINEAR


def test_register_safety_callback_reaches_interlocks():
    c = AdvancedElectrolyserController()
    got = []
    c.register_safety_callback(lambda k, r: got.append((k, r)))
    c.safety_interlocks.trigger_emergency_stop("r")
    assert got == [("emergency_stop", "r")]


def test_control_pass_applies_schedules_updates_and_logs(monkeypatch):
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.set_power_ramp(1000.0, 1000.0, 1000.0)
    c.set_voltage_ramp(45.0, 45.0, 1000.0)
    one_iteration(c, monkeypatch)
    assert c.last_status["power"] == 1000.0
    assert 0 < c.last_status["voltage"] <= 45.0
    assert len(c.logger.events) == 1
    ev = c.logger.events[0]
    assert ev.event_type == "normal" and ev.message is None and ev.mode == "RAMP_UP"


def test_control_pass_skips_expired_schedules(monkeypatch):
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.set_power_ramp(1000.0, 2000.0, -1.0)  # duration already elapsed on the first pass
    c.set_voltage_ramp(45.0, 45.0, -1.0)
    one_iteration(c, monkeypatch)
    assert c.last_status["power"] == 0.0 and c.last_status["voltage"] == 0.0


def test_control_pass_reports_alert_events(caplog, monkeypatch):
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.system.set_voltage(1e6)  # outside the spec range -> safety alert
    with caplog.at_level("WARNING", logger=eac.logger.name):
        one_iteration(c, monkeypatch)
    ev = c.logger.events[0]
    assert ev.event_type == "alert" and "Voltage too high" in ev.message
    assert any("Safety alert" in r.message for r in caplog.records)


def test_start_stop_with_background_thread_writes_logs():
    c = AdvancedElectrolyserController()
    c.start()
    assert c.is_running and isinstance(c.control_thread, threading.Thread)
    deadline = time.monotonic() + 5
    while not c.logger.events and time.monotonic() < deadline:
        threading.Event().wait(0.005)
    c.stop()
    assert not c.is_running and not c.control_thread.is_alive()
    assert c.logger.events
    data = json.load(open(c.logger.json_file))
    assert data["total_events"] == len(c.logger.events)
    assert c.system.electrolyser.current_mode.value == "IDLE"


def test_stop_without_start_still_saves_empty_log():
    c = AdvancedElectrolyserController()
    c.stop()
    assert json.load(open(c.logger.json_file))["total_events"] == 0


def test_print_live_status_formats_the_latest_status(capsys, monkeypatch):
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.system.set_power(1000.0)
    c.last_status = c.system.get_status()
    c.is_running = True

    def one_pass_then_stop(seconds):
        c.is_running = False

    monkeypatch.setattr(time, "sleep", one_pass_then_stop)
    c.print_live_status(interval=0.01)
    out = capsys.readouterr().out
    assert "V:" in out and "P:1000W" in out and "Eff:" in out and "H2:" in out


def test_print_live_status_without_status_prints_nothing(capsys, monkeypatch):
    c = AdvancedElectrolyserController()
    c.is_running = True

    def stop(seconds):
        c.is_running = False

    monkeypatch.setattr(time, "sleep", stop)
    c.print_live_status()
    assert capsys.readouterr().out == ""


def test_print_live_status_handles_keyboard_interrupt(capsys, monkeypatch):
    c = AdvancedElectrolyserController()
    c.is_running = True

    def interrupt(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", interrupt)
    c.print_live_status()
    assert capsys.readouterr().out == "\n\n"


def test_export_report_contents(tmp_path):
    c = AdvancedElectrolyserController(ElectrolyserType.ALKALINE)
    c.logger.log_event(event(0))
    c.last_status = {"mode": "NORMAL"}
    rep = c.export_report("r.json")
    on_disk = json.load(open(tmp_path / "r.json"))
    assert on_disk == rep
    assert rep["electrolyser_type"] == "ALKALINE" and rep["final_status"] == {"mode": "NORMAL"}
    assert rep["summary"]["total_events"] == 1
    assert rep["csv_log"] == c.logger.csv_file and rep["json_log"] == c.logger.json_file


def test_demo_advanced_control_runs_until_interrupted(capsys, monkeypatch):
    calls = {"n": 0}
    main = threading.main_thread()

    def sleeper(seconds):
        if threading.current_thread() is main:
            calls["n"] += 1
            if calls["n"] > 2:
                raise KeyboardInterrupt
        else:
            threading.Event().wait(0.0005)

    monkeypatch.setattr(time, "sleep", sleeper)
    eac.demo_advanced_control()
    out = capsys.readouterr().out
    assert "OPERATION SUMMARY" in out and "Hydrogen produced" in out


def test_numpy_import_fallback_sets_np_to_none(monkeypatch, caplog):
    """Load a private copy of the module with numpy unimportable (the real module stays untouched)."""
    import importlib.util
    import sys

    monkeypatch.setitem(sys.modules, "numpy", None)  # makes `import numpy` raise ImportError
    spec = importlib.util.spec_from_file_location("eac_without_numpy", eac.__file__)
    private = importlib.util.module_from_spec(spec)
    with caplog.at_level("WARNING", logger=eac.logger.name):
        spec.loader.exec_module(private)
    assert private.np is None
    assert any("NumPy not available" in r.message for r in caplog.records)
    assert eac.np is not None


def test_demo_callbacks_are_wired_to_the_controller(monkeypatch, capsys):
    """The demo and example 4 register a printing safety callback; fire it through the interlocks."""
    import electrolyser_examples as ex

    captured = []
    orig = AdvancedElectrolyserController.register_safety_callback

    def spy(self, cb):
        captured.append(cb)
        return orig(self, cb)

    monkeypatch.setattr(AdvancedElectrolyserController, "register_safety_callback", spy)
    main = threading.main_thread()
    n = {"i": 0}

    def sleeper(seconds):
        if threading.current_thread() is main:
            n["i"] += 1
            if n["i"] > 1:
                raise KeyboardInterrupt
        else:
            threading.Event().wait(0.0005)

    monkeypatch.setattr(time, "sleep", sleeper)
    eac.demo_advanced_control()
    monkeypatch.setattr(time, "sleep", lambda seconds: None if threading.current_thread() is main
                        else threading.Event().wait(0.0005))
    ex.example_advanced_scheduling()
    assert len(captured) == 2
    capsys.readouterr()
    for cb in captured:
        cb("emergency_stop", "test reason")
    out = capsys.readouterr().out
    assert out.count("SAFETY EVENT: emergency_stop - test reason") == 2


def test_schedule_is_still_applied_at_exactly_its_duration(monkeypatch):
    class FrozenDatetime:
        @staticmethod
        def now():
            return T0

    monkeypatch.setattr(eac, "datetime", FrozenDatetime)  # elapsed is exactly 0.0
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.set_power_ramp(500.0, 1500.0, 0.0)  # elapsed == duration -> ramp is at its end value
    one_iteration(c, monkeypatch)
    assert c.last_status["power"] == 1500.0


def test_event_message_is_the_first_alert(monkeypatch):
    c = AdvancedElectrolyserController()
    c.system.start_operation()
    c.system.set_voltage(1e6)
    c.system.set_voltage(-5.0)
    assert len(c.system.electrolyser.safety_monitor.alerts) == 2
    one_iteration(c, monkeypatch)
    assert "too high" in c.logger.events[0].message
