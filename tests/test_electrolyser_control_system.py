"""Tests for electrolyser_control_system.py.

Expected values come from Faraday's law and water-splitting stoichiometry,
not from the code's own output:

    H2 [mol/s] = I * N_cells / (2 F),   F = 96485.33 C/mol
    2 H2O -> 2 H2 + O2   =>  O2 = H2 / 2 (by mole and by Nm3), water >= H2 mol

At constant Faradaic efficiency, production is therefore proportional to stack
current. The nameplate `hydrogen_production_rate` is the rate at the nominal
current, so 1 h at nominal current must give exactly the nameplate volume and
1 h at half current must give half of it.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from electrolyser_control_system import (  # noqa: E402
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

F = 96485.33212          # C/mol
NM3_PER_MOL = 22.414e-3  # ideal gas at 0 degC, 1 atm
HHV_H2_V = 1.481         # thermoneutral voltage (HHV basis), V/cell
CLASSES = [PEMElectrolyser, AEMElectrolyser, AlkalineElectrolyser]


def _inverter():
    return InverterController(InverterConfig(
        rated_power=5000.0, input_voltage_min=200.0, input_voltage_max=240.0,
        output_frequency=50.0, frequency_range=(40.0, 60.0), efficiency=95.0,
        switching_frequency=16000.0))


def _running(cls, current_A):
    """Electrolyser in NORMAL mode carrying `current_A` at nominal voltage."""
    e = cls(_inverter())
    e.start()
    e.transition_mode(OperatingMode.NORMAL)
    e.current_voltage = e.specs.nominal_voltage
    e.current_current = current_A
    e.current_power = current_A * e.specs.nominal_voltage
    return e


# ---------------------------------------------------------------- nameplate data

@pytest.mark.parametrize("cls", CLASSES)
def test_nameplate_o2_is_half_of_h2(cls):
    s = cls(_inverter()).specs
    assert s.oxygen_production_rate == pytest.approx(s.hydrogen_production_rate / 2)


@pytest.mark.parametrize("cls", CLASSES)
def test_nameplate_water_covers_stoichiometric_demand(cls):
    s = cls(_inverter()).specs
    mol_h2_per_h = s.hydrogen_production_rate / NM3_PER_MOL
    stoich_water_L_per_h = mol_h2_per_h * 18.015 / 1000.0   # 1 mol H2O per mol H2, ~1 kg/L
    assert s.water_consumption_rate >= stoich_water_L_per_h


@pytest.mark.parametrize("cls", CLASSES)
def test_nameplate_rate_implies_a_physical_cell_voltage(cls):
    """Faraday: N_cells = H2 / (I / 2F). Stack voltage / N_cells must sit
    between the thermoneutral voltage (1.48 V) and ~2.5 V for a real cell."""
    s = cls(_inverter()).specs
    h2_mol_s = s.hydrogen_production_rate / NM3_PER_MOL / 3600.0
    n_cells = h2_mol_s * 2 * F / s.nominal_current
    v_cell = s.nominal_voltage / n_cells
    assert HHV_H2_V < v_cell < 2.5


# ---------------------------------------------------------------- production

@pytest.mark.parametrize("cls", CLASSES)
def test_one_hour_at_nominal_current_gives_nameplate_h2(cls):
    e = _running(cls, cls(_inverter()).specs.nominal_current)
    e.update_state(3600.0)
    assert e.hydrogen_produced == pytest.approx(e.specs.hydrogen_production_rate)
    assert e.oxygen_produced == pytest.approx(e.specs.hydrogen_production_rate / 2)


@pytest.mark.parametrize("cls", CLASSES)
def test_h2_production_is_proportional_to_current_faraday(cls):
    """Prove-it for the constant-rate bug: half the current must give half the H2."""
    nominal = cls(_inverter()).specs.nominal_current
    full = _running(cls, nominal)
    half = _running(cls, nominal / 2)
    full.update_state(3600.0)
    half.update_state(3600.0)
    assert half.hydrogen_produced == pytest.approx(full.hydrogen_produced / 2)
    assert half.water_consumed == pytest.approx(full.water_consumed / 2)


def test_h2_absolute_value_from_faraday_with_implied_cell_count():
    """PEM, 75 A for 1 h: N_cells from the nameplate, then H2 = I*N*t/(2F)."""
    e = _running(PEMElectrolyser, 75.0)
    s = e.specs
    n_cells = (s.hydrogen_production_rate / NM3_PER_MOL / 3600.0) * 2 * F / s.nominal_current
    expected_nm3 = 75.0 * n_cells * 3600.0 / (2 * F) * NM3_PER_MOL
    e.update_state(3600.0)
    assert e.hydrogen_produced == pytest.approx(expected_nm3, rel=1e-9)


def test_no_production_while_idle_or_ramping():
    e = PEMElectrolyser(_inverter())
    e.current_current, e.current_power = 100.0, 4800.0
    e.update_state(3600.0)                 # IDLE
    assert e.hydrogen_produced == 0.0
    e.start()                              # RAMP_UP
    e.update_state(3600.0)
    assert e.hydrogen_produced == 0.0


def test_no_production_at_zero_current():
    e = _running(PEMElectrolyser, 0.0)
    e.update_state(3600.0)
    assert e.hydrogen_produced == 0.0


# ---------------------------------------------------------------- efficiency

@pytest.mark.parametrize("cls", CLASSES)
def test_efficiency_falls_as_load_rises(cls):
    """Cell voltage rises with current density (activation + ohmic overpotential),
    so voltage efficiency = 1.48 V / V_cell must fall with load, not rise."""
    lo = _running(cls, cls(_inverter()).specs.nominal_current * 0.25)
    hi = _running(cls, cls(_inverter()).specs.nominal_current)
    assert lo.calculate_efficiency() > hi.calculate_efficiency()


@pytest.mark.parametrize("cls", CLASSES)
def test_efficiency_stays_within_spec_band(cls):
    s = cls(_inverter()).specs
    for frac in (0.05, 0.5, 1.0, 1.2):
        e = _running(cls, s.nominal_current * frac)
        assert s.min_efficiency <= e.calculate_efficiency() <= s.max_efficiency


def test_efficiency_zero_when_off():
    assert PEMElectrolyser(_inverter()).calculate_efficiency() == 0.0


# ---------------------------------------------------------------- safety monitor

def test_safety_monitor_voltage_limits():
    s = PEMElectrolyser(_inverter()).specs
    m = SafetyMonitor(s)
    assert m.check_voltage(s.min_voltage) and m.check_voltage(s.max_voltage)
    assert not m.check_voltage(s.max_voltage + 0.1)
    assert not m.check_voltage(s.min_voltage - 0.1)
    assert len(m.alerts) == 2 and not m.get_status()["safe"]
    m.clear()
    assert m.get_status() == {"alerts": [], "warnings": [], "safe": True}


def test_safety_monitor_low_current_warns_high_current_alerts():
    m = SafetyMonitor(PEMElectrolyser(_inverter()).specs)
    assert m.check_current(5.0) is True and m.warnings and not m.alerts
    assert m.check_current(151.0) is False and m.alerts


def test_safety_monitor_temperature_and_pressure():
    m = SafetyMonitor(PEMElectrolyser(_inverter()).specs)
    assert m.check_temperature(80.0) and not m.check_temperature(80.1)
    assert m.check_pressure(35.0) and not m.check_pressure(35.1)


# ---------------------------------------------------------------- PID / inverter / modes

def test_voltage_regulator_clamps_to_spec():
    s = PEMElectrolyser(_inverter()).specs
    r = VoltageRegulator(s)
    assert r.regulate(1000.0, s.max_voltage) == s.max_voltage
    assert VoltageRegulator(s).regulate(0.0, s.min_voltage) == s.min_voltage


def test_voltage_regulator_moves_toward_target():
    s = PEMElectrolyser(_inverter()).specs
    r = VoltageRegulator(s, kp=0.5, ki=0.0, kd=0.0)
    v = 40.0
    for _ in range(50):
        v = r.regulate(50.0, v)
    assert v == pytest.approx(50.0, abs=1e-6)


def test_inverter_rejects_out_of_range_and_over_rated():
    inv = _inverter()
    assert not inv.set_frequency(39.9) and not inv.set_frequency(60.1)
    assert inv.set_frequency(55.0) and inv.current_frequency == 55.0
    assert not inv.set_power(5000.1) and inv.set_power(5000.0)
    inv.disable()
    assert inv.output_power == 0.0


def test_mode_transitions():
    e = PEMElectrolyser(_inverter())
    assert not e.transition_mode(OperatingMode.NORMAL)   # IDLE -> NORMAL not allowed
    assert e.start() and e.current_mode == OperatingMode.RAMP_UP
    assert not e.start()                                  # already running
    assert e.transition_mode(OperatingMode.NORMAL)
    assert e.stop() and e.current_mode == OperatingMode.IDLE
    assert e.current_current == 0.0


def test_power_setpoint_derives_current_from_p_over_v():
    e = PEMElectrolyser(_inverter())
    e.current_voltage = 40.0
    assert e.set_power_setpoint(4000.0)
    assert e.current_current == pytest.approx(100.0)
    assert not e.set_power_setpoint(4000.0 * 1.6)   # 160 A > 150 A max


def test_control_system_rejects_unsupported_type():
    with pytest.raises(ValueError):
        ElectrolyserControlSystem(ElectrolyserType.SOEC)


@pytest.mark.xfail(strict=True, reason=(
    "BUG (not fixed): ElectrolyserBase.set_voltage_setpoint passes the stack DC "
    "voltage (30-60 V) to InverterController.set_voltage, which validates against "
    "the inverter INPUT range 200-240 V, so it is always rejected; the return value "
    "is ignored and set_voltage() reports success while the inverter stays at 0 V."))
def test_voltage_setpoint_reaches_inverter():
    sys_ = ElectrolyserControlSystem(ElectrolyserType.PEM)
    sys_.start_operation()
    assert sys_.set_voltage(45.0)
    assert sys_.inverter.get_status()["voltage"] == sys_.electrolyser.current_voltage > 0
