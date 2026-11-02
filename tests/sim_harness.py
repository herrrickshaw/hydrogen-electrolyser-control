"""Deterministic seeded simulations used to pin numeric behaviour of the control code.

``run_all(repo_dir)`` imports the control modules from *repo_dir*, replaces wall-clock
time with a fake clock, runs fixed scenarios and returns a JSON-serialisable dict.
The committed golden file was produced by running this against the original
(pre-refactor) code; ``tests/test_golden_simulation.py`` asserts exact equality.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import os
import random
import sys
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator


class FakeClock:
    """Monotonic fake clock advanced only by ``sleep``."""

    def __init__(self) -> None:
        self.t = 1_700_000_000.0

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class FakeDatetime(_dt.datetime):
    clock: FakeClock = FakeClock()

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return cls.fromtimestamp(cls.clock.t, tz)


@contextmanager
def _sandbox(repo_dir: str) -> Iterator[FakeClock]:
    clock = FakeClock()
    FakeDatetime.clock = clock
    orig_time, orig_sleep = time.time, time.sleep
    orig_cwd = os.getcwd()
    time.time, time.sleep = clock.time, clock.sleep
    sys.path.insert(0, repo_dir)
    for name in ("electrolyser_control_system", "electrolyser_advanced_control"):
        sys.modules.pop(name, None)
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield clock
        finally:
            os.chdir(orig_cwd)
            time.time, time.sleep = orig_time, orig_sleep
            sys.path.remove(repo_dir)


def _slim(status: Dict[str, Any]) -> Dict[str, Any]:
    """Collapse the (quadratically growing) alert/warning lists to count + first + last."""
    out = dict(status)
    safety = dict(status["safety"])
    for key in ("alerts", "warnings"):
        items = safety[key]
        safety[key] = [len(items), items[:1], items[-1:]]
    out["safety"] = safety
    return out


def run_all(repo_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    with _sandbox(repo_dir) as clock:
        cs = importlib.import_module("electrolyser_control_system")
        adv = importlib.import_module("electrolyser_advanced_control")
        adv.datetime = FakeDatetime  # type: ignore[attr-defined]

        # 1. PID voltage regulator trajectories (seeded noisy measurement).
        rng = random.Random(20260211)
        pid: Dict[str, Any] = {}
        for etype in (cs.ElectrolyserType.PEM, cs.ElectrolyserType.AEM, cs.ElectrolyserType.ALKALINE):
            system = cs.ElectrolyserControlSystem(etype)
            reg = system.electrolyser.voltage_regulator
            specs = system.electrolyser.specs
            v = specs.min_voltage
            traj = []
            for step in range(200):
                target = specs.nominal_voltage + 15.0 * (1 if step < 100 else -1) + rng.uniform(-2, 2)
                dt = 0.1 if step % 7 else 0.0
                v = reg.regulate(target, v + rng.uniform(-0.5, 0.5), dt)
                traj.append([v, reg.integral, reg.prev_error])
            pid[etype.value] = traj
        out["pid"] = pid

        # 2. Full ramp simulations per electrolyser type.
        sims: Dict[str, Any] = {}
        for etype in (cs.ElectrolyserType.PEM, cs.ElectrolyserType.AEM, cs.ElectrolyserType.ALKALINE):
            system = cs.ElectrolyserControlSystem(etype)
            ok = {"start": system.start_operation(), "start_again": system.start_operation()}
            system.ramp_to_voltage(system.electrolyser.specs.nominal_voltage - 3.0, ramp_rate=2.0, dt=0.05)
            system.ramp_to_power(3333.3, ramp_rate=250.0, dt=0.1)
            ok["freq_ok"] = system.set_frequency(52.5)
            ok["freq_bad"] = system.set_frequency(70.0)
            ok["volt_bad"] = system.set_voltage(1000.0)
            ok["power_over"] = system.set_power(6000.0)
            for _ in range(40):
                system.electrolyser.update_state(0.5)
            log = [_slim(entry["status"]) for entry in system.operation_log]
            sims[etype.value] = {
                "ok": ok,
                "final": _slim(system.get_status()),
                "log_len": len(log),
                "log_every_10th": log[::10],
            }
            ok["stop"] = system.stop_operation()
            sims[etype.value]["after_stop"] = _slim(system.get_status())
        out["ramp_sims"] = sims

        # 3. Ramp schedule profiles.
        sched: Dict[str, Any] = {}
        for prof in adv.RampProfile:
            rs = adv.RampSchedule(1000.0, 4000.0, 20.0, prof)
            sched[prof.value] = [rs.get_value_at_time(t * 0.5) for t in range(0, 45)]
        out["schedules"] = sched

        # 4. Safety monitor and inverter checks.
        system = cs.ElectrolyserControlSystem(cs.ElectrolyserType.PEM)
        mon = system.electrolyser.safety_monitor
        checks = []
        for fn, vals in (
            (mon.check_voltage, [10, 30, 45, 60, 61]),
            (mon.check_current, [5, 10, 100, 150, 151]),
            (mon.check_temperature, [0, 5, 50, 80, 81]),
            (mon.check_pressure, [0.5, 1, 20, 35, 36]),
        ):
            checks.append([fn(x) for x in vals])
        out["safety_checks"] = checks
        out["safety_status"] = mon.get_status()
        inv = system.inverter
        out["inverter"] = [inv.set_frequency(39.9), inv.set_frequency(40.0), inv.set_frequency(60.0),
                           inv.set_frequency(60.1), inv.set_voltage(199.0), inv.set_voltage(230.0),
                           inv.set_power(5000.0), inv.set_power(5000.1)]

        # 5. Advanced control loop, driven synchronously for a fixed number of ticks.
        ctl = adv.AdvancedElectrolyserController(cs.ElectrolyserType.PEM)
        ctl.system.start_operation()
        ctl.system.electrolyser.transition_mode(cs.OperatingMode.NORMAL)
        ctl.set_voltage_ramp(30.0, 48.0, 3.0, adv.RampProfile.LINEAR)
        ctl.set_power_ramp(1000.0, 4000.0, 3.0, adv.RampProfile.EXPONENTIAL)
        ticks = {"n": 0}
        real_sleep = time.sleep

        def counting_sleep(seconds: float) -> None:
            real_sleep(seconds)
            ticks["n"] += 1
            if ticks["n"] >= 60:
                ctl.is_running = False

        time.sleep = counting_sleep
        ctl.is_running = True
        ctl._control_loop()
        time.sleep = real_sleep
        out["control_loop"] = {
            "events": [
                {k: (v.isoformat() if isinstance(v, _dt.datetime) else v) for k, v in e.__dict__.items()}
                for e in ctl.logger.events
            ],
            "summary": ctl.logger.get_summary(),
            "csv": open(ctl.logger.csv_file).read(),
        }
        ctl.logger.save_json()
        import json
        out["control_loop"]["json"] = json.load(open(ctl.logger.json_file))

        # 6. Interlock arithmetic.
        il = adv.SafetyInterlocks()
        out["interlocks"] = [
            il.check_voltage_ramp_rate(50.0, 40.0, 1.0),
            il.check_voltage_ramp_rate(50.0, 40.0, 0.0),
            il.check_voltage_ramp_rate(40.0, 50.0, 1.0),
            il.check_current_jump(100.0, 40.0),
            il.check_current_jump(100.0, 60.0),
            il.emergency_stop,
        ]
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(run_all(os.path.abspath(sys.argv[1])), indent=1, sort_keys=True))
