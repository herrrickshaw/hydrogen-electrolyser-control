# Hydrogen Electrolyser Control System

A comprehensive Python framework for controlling hydrogen electrolysers (PEM, AEM, Alkaline) with voltage regulation, inverter frequency management, and real-time monitoring.

## Overview

This control system provides:

- **Multiple Electrolyser Types**: PEM, AEM, Alkaline, SOEC support
- **Voltage & Power Control**: PID-based voltage regulation and power setpoint management
- **Inverter Control**: Frequency and voltage adjustment (40-60 Hz range)
- **Safety Monitoring**: Real-time safety interlocks, temperature/pressure/voltage/current checks
- **Advanced Scheduling**: Linear, exponential, logarithmic ramp profiles
- **Data Logging**: CSV and JSON operation logs with real-time monitoring
- **Web API**: RESTful interface for remote control and monitoring
- **Production Metrics**: Hydrogen/oxygen production rate tracking with efficiency calculation

## Files

### Core System

1. **`electrolyser_control_system.py`** (2000 lines)
   - Base electrolyser classes (PEM, AEM, Alkaline)
   - Voltage regulator with PID control
   - Safety monitoring system
   - Inverter controller
   - Basic operation and ramp-up/down sequences

2. **`electrolyser_advanced_control.py`** (600 lines)
   - Advanced controller with threading
   - Scheduling system (linear, exponential, logarithmic ramps)
   - Data logging to CSV and JSON
   - Safety interlocks with callbacks
   - Real-time monitoring and reporting

3. **`electrolyser_web_api.py`** (600 lines)
   - Flask-based REST API
   - Real-time streaming endpoints
   - Python client library
   - CORS support for web interfaces

## Installation

```bash
# Core dependencies
pip install flask flask-cors

# Optional
pip install numpy  # For advanced ramp profiles
```

## Quick Start

### Basic Usage

```python
from electrolyser_control_system import ElectrolyserControlSystem, ElectrolyserType

# Create control system
system = ElectrolyserControlSystem(ElectrolyserType.PEM)

# Start operation
system.start_operation()

# Set voltage
system.set_voltage(45.0)  # 45V

# Set power
system.set_power(3500.0)  # 3500W

# Set inverter frequency
system.set_frequency(50.0)  # 50 Hz

# Ramp power gradually
system.ramp_to_power(target_power=4000.0, ramp_rate=100.0)

# Stop
system.stop_operation()

# Print status
system.print_status()
```

### Advanced Control with Scheduling

```python
from electrolyser_advanced_control import (
    AdvancedElectrolyserController,
    RampProfile,
    ElectrolyserType
)

# Create advanced controller
controller = AdvancedElectrolyserController(ElectrolyserType.AEM)

# Register safety callback
def on_safety_event(event_type, message):
    print(f"Safety Alert: {event_type} - {message}")

controller.register_safety_callback(on_safety_event)

# Start
controller.start()

# Schedule power ramp: 1000W → 4000W over 15 seconds (exponential)
controller.set_power_ramp(
    start_power=1000.0,
    end_power=4000.0,
    duration=15.0,
    profile=RampProfile.EXPONENTIAL
)

# Schedule voltage ramp: 30V → 48V over 10 seconds (linear)
controller.set_voltage_ramp(
    start_voltage=30.0,
    end_voltage=48.0,
    duration=10.0,
    profile=RampProfile.LINEAR
)

# Monitor live status
controller.print_live_status(interval=1.0)

# Stop and export report
controller.stop()
report = controller.export_report("my_report.json")
```

## Web API

### Starting the API Server

```bash
# Start PEM electrolyser server on port 5000
python electrolyser_web_api.py PEM 5000

# Start AEM electrolyser server on port 5001
python electrolyser_web_api.py AEM 5001

# Start Alkaline electrolyser server
python electrolyser_web_api.py ALKALINE 5000
```

### API Endpoints

#### Health & Status
```bash
# Health check
curl http://localhost:5000/api/health

# Current status
curl http://localhost:5000/api/status

# Specifications
curl http://localhost:5000/api/specs
```

#### Control
```bash
# Start operation
curl -X POST http://localhost:5000/api/control/start

# Set voltage to 45V
curl -X POST http://localhost:5000/api/control/voltage \
  -H "Content-Type: application/json" \
  -d '{"voltage": 45.0}'

# Set power to 3500W
curl -X POST http://localhost:5000/api/control/power \
  -H "Content-Type: application/json" \
  -d '{"power": 3500.0}'

# Set frequency to 50 Hz
curl -X POST http://localhost:5000/api/control/frequency \
  -H "Content-Type: application/json" \
  -d '{"frequency": 50.0}'

# Stop operation
curl -X POST http://localhost:5000/api/control/stop
```

#### Scheduling
```bash
# Linear power ramp: 1000W → 4000W over 20 seconds
curl -X POST http://localhost:5000/api/schedule/power-ramp \
  -H "Content-Type: application/json" \
  -d '{
    "start_power": 1000,
    "end_power": 4000,
    "duration": 20,
    "profile": "LINEAR"
  }'

# Exponential voltage ramp: 30V → 48V over 15 seconds
curl -X POST http://localhost:5000/api/schedule/voltage-ramp \
  -H "Content-Type: application/json" \
  -d '{
    "start_voltage": 30,
    "end_voltage": 48,
    "duration": 15,
    "profile": "EXPONENTIAL"
  }'
```

#### Monitoring
```bash
# Safety status
curl http://localhost:5000/api/monitoring/safety

# Production metrics
curl http://localhost:5000/api/monitoring/production

# Performance metrics
curl http://localhost:5000/api/monitoring/performance

# Operation summary
curl http://localhost:5000/api/monitoring/summary
```

#### Emergency Control
```bash
# Emergency stop
curl -X POST http://localhost:5000/api/emergency/stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "Loss of coolant detected"}'

# Clear emergency
curl -X POST http://localhost:5000/api/emergency/clear
```

### Python Client

```python
from electrolyser_web_api import ElectrolyserClient

# Connect to API
client = ElectrolyserClient("http://localhost:5000")

# Health check
print(client.health_check())

# Start
client.start()

# Set voltage and power
client.set_voltage(45.0)
client.set_power(3500.0)

# Schedule ramp
client.set_power_ramp(1000, 4000, 20, "LINEAR")

# Get production
production = client.get_production()
print(f"H2 produced: {production['hydrogen_produced_nm3']} Nm³")

# Emergency stop
client.emergency_stop("Manual stop")
```

## Electrolyser Types

### PEM (Proton Exchange Membrane)
- **Voltage**: 30-60V (nominal 48V)
- **Current**: 10-150A (nominal 100A)
- **Power**: 4800W nominal
- **Efficiency**: 60-75%
- **Hydrogen Rate**: 0.95 Nm³/hour
- **Temperature**: 5-80°C
- **Pressure**: 1-35 bar

### AEM (Anion Exchange Membrane)
- **Voltage**: 25-55V (nominal 40V)
- **Current**: 15-180A (nominal 120A)
- **Power**: 4800W nominal
- **Efficiency**: 55-72%
- **Hydrogen Rate**: 0.90 Nm³/hour
- **Temperature**: 10-85°C
- **Pressure**: 1-30 bar

### Alkaline
- **Voltage**: 18-32V (nominal 24V)
- **Current**: 20-300A (nominal 200A)
- **Power**: 4800W nominal
- **Efficiency**: 52-68%
- **Hydrogen Rate**: 0.85 Nm³/hour
- **Temperature**: 0-70°C
- **Pressure**: 0.5-25 bar

## Voltage Regulation (PID Control)

The system uses a PID controller for voltage regulation:

```python
# Default PID parameters
Kp = 0.1  # Proportional gain
Ki = 0.01 # Integral gain
Kd = 0.05 # Derivative gain

# Customize PID tuning
voltage_regulator.kp = 0.15
voltage_regulator.ki = 0.02
voltage_regulator.kd = 0.08
```

### Tuning Guide

| Parameter | Effect | Tuning |
|-----------|--------|--------|
| **Kp** | Proportional response | Increase for faster response, decrease for stability |
| **Ki** | Steady-state error | Increase to eliminate offset, decrease for stability |
| **Kd** | Damping | Increase to reduce overshoot, decrease for faster response |

## Safety Features

### Monitoring

- **Voltage Check**: Ensures voltage stays within min/max limits
- **Current Check**: Monitors for overcurrent conditions
- **Temperature Check**: Tracks operating temperature range
- **Pressure Check**: Verifies pressure within safe limits
- **Ramp Rate Check**: Detects unsafe voltage ramp rates
- **Current Jump Detection**: Identifies potential short circuits

### Interlocks

```python
# Emergency stop system
controller.safety_interlocks.trigger_emergency_stop("Loss of coolant")

# Clear emergency
controller.safety_interlocks.clear_emergency_stop()

# Check specific conditions
is_safe = controller.safety_interlocks.check_voltage_ramp_rate(
    current_voltage=45.0,
    previous_voltage=44.0,
    dt=0.1,
    max_rate=5.0  # V/s
)
```

## Data Logging

### CSV Output

```
timestamp,mode,voltage,current,power,temperature,pressure,efficiency,hydrogen_produced,oxygen_produced,water_consumed,event_type,message
2024-01-15T10:30:45.123456,NORMAL,45.00,100.00,4500.00,55.00,5.00,72.50,0.0250,0.0125,0.0225,normal,
2024-01-15T10:30:46.234567,NORMAL,45.05,101.20,4560.00,55.50,5.05,73.10,0.0275,0.0138,0.0248,normal,
```

### JSON Summary

```json
{
  "total_events": 1500,
  "duration_seconds": 150.0,
  "voltage_avg": 45.2,
  "voltage_min": 30.0,
  "voltage_max": 50.0,
  "current_avg": 100.5,
  "power_avg": 4520.0,
  "efficiency_avg": 72.5,
  "total_hydrogen": 2.37,
  "total_oxygen": 1.19,
  "total_water_consumed": 1.88,
  "alerts": 0,
  "warnings": 3
}
```

## Ramp Profiles

### Linear
Constant rate increase/decrease
```python
profile = RampProfile.LINEAR
# Value = start + (end - start) × progress
```

### Exponential
Slow start, accelerating increase
```python
profile = RampProfile.EXPONENTIAL
# More aggressive power ramp-up
```

### Logarithmic
Fast start, decelerating increase
```python
profile = RampProfile.LOGARITHMIC
# Smooth approach to target
```

### Step
Instant jump at 50% mark
```python
profile = RampProfile.STEP
# For testing step responses
```

## Real-Time Monitoring

### Live Status Printing

```python
controller.print_live_status(interval=1.0)
# Output:
# [10:30:45] V:45.2V | I:100.5A | P:4520W | Eff:72.5% | H2:2.37Nm³
```

### Status Dictionary

```python
status = system.get_status()

print(f"Voltage: {status['voltage']} V")
print(f"Current: {status['current']} A")
print(f"Power: {status['power']} W")
print(f"Temperature: {status['temperature']} °C")
print(f"Pressure: {status['pressure']} bar")
print(f"Efficiency: {status['efficiency']} %")
print(f"Mode: {status['mode']}")
print(f"H2 Produced: {status['hydrogen_produced']} Nm³")
print(f"Safe: {status['safety']['safe']}")
```

## Performance Metrics

### Efficiency Calculation

PEM Efficiency = 60% + (15% × load_factor)
- At 25% load: ~63.75%
- At 50% load: ~67.50%
- At 100% load: ~75.00%

### Production Rate Equations

```
Hydrogen (Nm³/hour) = 0.95 × (power / nominal_power)
Oxygen (Nm³/hour) = 0.475 × (power / nominal_power)
Water (L/hour) = 0.9 × (power / nominal_power)
```

## Example Use Cases

### Case 1: Renewable Energy Integration
```python
# Ramp power smoothly to absorb solar variation
controller.set_power_ramp(
    start_power=1000,
    end_power=3500,
    duration=300,  # 5 minutes
    profile=RampProfile.LOGARITHMIC
)
```

### Case 2: Grid Frequency Support
```python
# Adjust frequency with grid support
for freq in [48.5, 49.0, 49.5, 50.0, 50.5, 51.0]:
    system.set_frequency(freq)
    time.sleep(10)
```

### Case 3: Multi-Unit Coordination
```python
# Control multiple electrolysers from API
systems = [
    ElectrolyserClient(f"http://localhost:{5000+i}")
    for i in range(3)
]

# Synchronized start
for client in systems:
    client.start()

# Parallel ramp-up
for client in systems:
    client.set_power_ramp(1000, 3500, 20, "LINEAR")
```

### Case 4: Operational Testing
```python
# Test ramp response
controller.set_voltage_ramp(30, 55, 30, RampProfile.EXPONENTIAL)

# Get summary after 30 seconds
import time
time.sleep(30)
summary = controller.logger.get_summary()
print(f"Max voltage: {summary['voltage_max']} V")
```

## Troubleshooting

### Issue: Voltage Not Reaching Target

**Solution**: Check PID parameters
```python
# Increase proportional gain
regulator.kp = 0.2

# Check limits
print(f"Min: {specs.min_voltage}, Max: {specs.max_voltage}")
```

### Issue: Safety Alerts Triggered

**Check**:
```python
status = system.get_status()
print(status['safety'])
```

### Issue: CSV Not Updating

**Solution**: Ensure controller.stop() is called to flush logs
```python
controller.stop()  # Saves CSV and JSON
```

## Performance Benchmarks

| Operation | Time |
|-----------|------|
| Voltage ramp (30V → 50V) | 10s typical |
| Power ramp (1000W → 4000W) | 15s typical |
| API response time | <50ms |
| Data logging overhead | <5% CPU |

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│         Web API (Flask)                         │
│    REST endpoints + Python Client               │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────v────────────────────────────────┐
│   AdvancedElectrolyserController                │
│   - Scheduling (ramp profiles)                  │
│   - Real-time monitoring                        │
│   - Data logging (CSV/JSON)                     │
│   - Safety interlocks                           │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────v────────────────────────────────┐
│   ElectrolyserControlSystem                     │
│   - PEM/AEM/Alkaline logic                      │
│   - Voltage regulation (PID)                    │
│   - Inverter control                            │
│   - Safety monitoring                           │
└────────────────┬────────────────────────────────┘
                 │
         ┌───────v────────┬──────────┬────────────┐
         │                │          │            │
      ┌──v──┐        ┌────v─┐  ┌───v──┐  ┌──────v┐
      │ PEM │        │ AEM  │  │Alk.  │  │Safety │
      └─────┘        └──────┘  └──────┘  └───────┘
```

## License

This code is provided for educational and research purposes.

## Support

For issues or questions, refer to:
- Inline code documentation
- Example usage in each module
- API endpoint documentation

---

**Last Updated**: 2024-01-15
**Version**: 1.0.0
