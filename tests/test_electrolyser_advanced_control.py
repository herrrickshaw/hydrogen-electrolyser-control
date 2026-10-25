"""Tests for the pure parts of electrolyser_advanced_control.py: ramp profiles,
safety interlocks and the DataLogger summary (written under tmp_path)."""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from electrolyser_advanced_control import (  # noqa: E402
    DataLogger,
    OperationEvent,
    RampProfile,
    RampSchedule,
    SafetyInterlocks,
)


@pytest.mark.parametrize("profile", [RampProfile.LINEAR, RampProfile.EXPONENTIAL,
                                     RampProfile.LOGARITHMIC, RampProfile.STEP])
def test_ramp_hits_both_endpoints(profile):
    r = RampSchedule(1000.0, 4000.0, 10.0, profile)
    assert r.get_value_at_time(0.0) == pytest.approx(1000.0)
    assert r.get_value_at_time(10.0) == 4000.0
    assert r.get_value_at_time(99.0) == 4000.0


def test_linear_ramp_midpoint():
    assert RampSchedule(0.0, 100.0, 10.0, RampProfile.LINEAR).get_value_at_time(2.5) == pytest.approx(25.0)


def test_exponential_ramp_is_below_linear_mid_ramp():
    # (e^(2*0.5) - 1) / (e^2 - 1) = 0.2689 with e ~ 2.718
    v = RampSchedule(0.0, 100.0, 10.0, RampProfile.EXPONENTIAL).get_value_at_time(5.0)
    assert v == pytest.approx(100 * (2.718 ** 1 - 1) / (2.718 ** 2 - 1))
    assert v < 50.0


def test_logarithmic_ramp_value():
    # log2(1.5) = 0.58496: concave, i.e. FASTER at the start (the inline comment
    # in the source says "slower at start" - the comment is wrong, not the maths).
    v = RampSchedule(0.0, 100.0, 10.0, RampProfile.LOGARITHMIC).get_value_at_time(5.0)
    assert v == pytest.approx(58.496, abs=1e-3)


def test_step_ramp_switches_at_half():
    r = RampSchedule(10.0, 20.0, 10.0, RampProfile.STEP)
    assert r.get_value_at_time(4.99) == 10.0 and r.get_value_at_time(5.0) == 20.0


def test_ramp_down_works():
    assert RampSchedule(4000.0, 0.0, 4.0, RampProfile.LINEAR).get_value_at_time(1.0) == pytest.approx(3000.0)


def test_interlock_voltage_ramp_rate():
    calls = []
    s = SafetyInterlocks()
    s.register_callback(lambda kind, msg: calls.append(kind))
    assert s.check_voltage_ramp_rate(40.5, 40.0, 0.1)          # 5 V/s == limit
    assert not s.emergency_stop
    assert not s.check_voltage_ramp_rate(41.0, 40.0, 0.1)      # 10 V/s
    assert s.emergency_stop and calls == ["emergency_stop"]
    s.clear_emergency_stop()
    assert not s.emergency_stop
    assert s.check_voltage_ramp_rate(99.0, 0.0, 0.0)           # dt=0 short-circuits


def test_interlock_current_jump_and_bad_callback_does_not_propagate():
    s = SafetyInterlocks()
    s.register_callback(lambda *_: 1 / 0)
    assert s.check_current_jump(150.0, 100.0)                  # 50 A == limit
    assert not s.check_current_jump(151.0, 100.0)
    assert s.emergency_stop


def _event(t, v, i, p, eff, h2, kind="normal"):
    return OperationEvent(timestamp=t, mode="NORMAL", voltage=v, current=i, power=p,
                          temperature=60.0, pressure=10.0, efficiency=eff,
                          hydrogen_produced=h2, oxygen_produced=h2 / 2,
                          water_consumed=h2, event_type=kind)


def test_datalogger_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = DataLogger(prefix="t")
    assert log.get_summary() == {}
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    log.log_event(_event(t0, 40.0, 0.0, 0.0, 0.0, 0.0, "transition"))
    log.log_event(_event(t0 + timedelta(seconds=30), 44.0, 90.0, 3960.0, 70.0, 0.5, "warning"))
    log.log_event(_event(t0 + timedelta(seconds=60), 48.0, 100.0, 4800.0, 66.0, 1.0, "alert"))
    s = log.get_summary()
    assert s["total_events"] == 3 and s["duration_seconds"] == 60.0
    assert s["voltage_avg"] == pytest.approx(44.0)
    assert s["efficiency_avg"] == pytest.approx(68.0)         # zero-efficiency rows excluded
    assert s["total_hydrogen"] == 1.0 and s["total_oxygen"] == 0.5
    assert s["alerts"] == 1 and s["warnings"] == 1
    rows = (tmp_path / log.csv_file).read_text().strip().splitlines()
    assert len(rows) == 4 and rows[0].startswith("timestamp,mode")
