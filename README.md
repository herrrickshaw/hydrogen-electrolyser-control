# Hydrogen Electrolyser Control (simulation framework)

A Python simulation and control-logic framework for PEM, AEM and alkaline water electrolysers: a PID voltage
regulator, an AC-inverter model (40-60 Hz), safety limit checks, power/voltage ramp schedules, CSV/JSON
operation logging and a Flask REST API with a small Python client. It is aimed at people prototyping
control strategies or teaching/demonstrating electrolyser operation. It outputs console status, CSV/JSON
logs and JSON reports in the working directory.

> Status: research-only / educational. All behaviour is simulated; the specs are illustrative figures, not vendor
> data, and nothing here has been validated on hardware (see `VALIDATION_SCOPE_CLARIFICATION.md`).
> Not suitable for controlling a real electrolyser or as a safety system.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/hydrogen-electrolyser-control/blob/main/notebooks/colab_test.ipynb)
New here? See [How to use this repo with AI](HOW_TO_USE_WITH_AI.md).

## What it does
- Models PEM (48 V / 100 A), AEM (40 V / 120 A) and alkaline (24 V / 200 A) units, each with a 4.8 kW nominal rating.
- Regulates voltage with a PID step (`kp=0.1, ki=0.01, kd=0.05`, integral clamped to +/-10) clipped to the unit's voltage band.
- Checks voltage, current, temperature and pressure against per-type limits and records alerts/warnings.
- Schedules power or voltage ramps (linear, exponential, logarithmic, step) in a background control thread.
- Accumulates H2/O2/water totals while in `NORMAL` mode and logs every tick to CSV/JSON.
- Exposes control, scheduling and monitoring over 20 REST endpoints (`electrolyser_web_api.py`).

## Quick start
```bash
git clone https://github.com/herrrickshaw/hydrogen-electrolyser-control.git
cd hydrogen-electrolyser-control
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python electrolyser_control_system.py     # PEM, AEM and alkaline demos (takes about a minute: real sleeps)
```

```python
from electrolyser_control_system import ElectrolyserControlSystem, ElectrolyserType

system = ElectrolyserControlSystem(ElectrolyserType.PEM)
system.start_operation()
system.ramp_to_voltage(45.0, ramp_rate=2.0)
system.ramp_to_power(4000.0, ramp_rate=200.0)   # W and W/s
system.print_status()
system.stop_operation()                          # writes electrolyser_pem_log.json
```

Other entry points: `python electrolyser_examples.py` (8 examples), `python electrolyser_advanced_control.py`
(scheduled ramps with live status; runs until Ctrl-C), `python electrolyser_web_api.py PEM 5000` (REST server; type, then port).

## How it works
| Stage | Module | Output |
|---|---|---|
| Specs, inverter, safety limits, PID, mode state machine | `electrolyser_control_system.py` | `ElectrolyserControlSystem`, status dicts |
| Ramp schedules, interlocks, threaded control loop, data logger | `electrolyser_advanced_control.py` | `electrolyser_<type>_<timestamp>.csv/.json` |
| HTTP interface and `ElectrolyserClient` | `electrolyser_web_api.py` | JSON responses |
| Runnable demonstrations | `electrolyser_examples.py` | console output |

Electrolyser types are registered in `ELECTROLYSER_CLASSES`; efficiency is a shared load-linear curve between each
type's min and max efficiency (`load_scaled_efficiency`). Details of the API and PID tuning are in
[ELECTROLYSER_README.md](ELECTROLYSER_README.md).

## Repository layout
| Path | Purpose |
|---|---|
| `electrolyser_*.py` | The four modules above |
| `tests/` | pytest suite; `tests/golden/simulation_baseline.json` pins seeded simulation output |
| `notebooks/colab_test.ipynb` | Colab smoke test |
| `*.md` reports | Earlier project write-ups; see Limitations before relying on their conclusions |

## Configuration
No secrets or environment variables. Defaults live in code: inverter 5 kW, 200-240 V, 50 Hz (40-60 Hz range);
control-loop interval 0.1 s (`/api/config/update-interval`); API on `0.0.0.0:5000`. Logs and reports are written
to the current working directory.

## Testing
```bash
pip install -r requirements.txt pytest ruff
pytest -q        # 30 tests, no network or hardware, about 1 s
ruff check .
```
The golden test replays seeded PID, ramp, schedule and control-loop scenarios on a fake clock and requires
bit-identical numbers to those recorded before the refactor.

## Limitations and known issues
- Simulation only. The performance and "validation" figures in `COMPLETE_PROJECT_SUMMARY.md` and
  `REAL_DATA_VALIDATION_REPORT.md` come from synthetic profiles whose scripts are not in this repository, so they
  cannot be reproduced from it; treat them as claims, not results.
- Temperature and pressure are fixed (25 C, 1 bar): there is no thermal or gas-pressure model.
- H2/O2/water production uses constant per-hour rates while in `NORMAL` mode, independent of power.
- `SafetyInterlocks` (ramp-rate and current-jump checks, emergency stop) are not called by the control loop, and
  an emergency stop only sets a flag and fires callbacks; it does not de-energise the unit.
- `set_voltage` applies a single PID step toward the setpoint, not an instant jump; setpoints outside the unit's
  voltage band are rejected, so `ramp_to_voltage` from 0 V makes no progress until the ramp enters the band.
- The `LOGARITHMIC` ramp needs NumPy and raises `AttributeError` if it is missing; its curve is concave (fast start).
- The REST API has no authentication and binds all interfaces by default; do not expose it on an untrusted network.
- `SOEC` and `CUSTOM` appear in `ElectrolyserType` but are not implemented (`ValueError`).
- Logging is configured at import time (`logging.basicConfig`) in two modules.

## Licence
No licence file yet — all rights reserved. (The previous README said "MIT" but the repository contains no
`LICENSE` file; the owner should confirm the intended licence.)
