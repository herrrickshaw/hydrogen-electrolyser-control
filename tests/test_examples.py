"""Smoke-run every example (sleeps are shortened by conftest; logs go to a temp cwd)."""
import threading
import time

import pytest

import electrolyser_examples as ex


@pytest.mark.parametrize("name,marker", [
    ("example_basic_pem_operation", "Example 1 complete"),
    ("example_voltage_ramp_up", "Example 2 complete"),
    ("example_power_ramp_up", "Example 3 complete"),
    ("example_electrolyser_comparison", "Example 5 complete"),
    ("example_frequency_variation", "Example 6 complete"),
    ("example_safety_monitoring", "Example 7 complete"),
    ("example_production_calculation", "Example 8 complete"),
])
def test_example_runs_to_completion(name, marker, capsys):
    getattr(ex, name)()
    assert marker in capsys.readouterr().out


def test_example_advanced_scheduling_runs(capsys, monkeypatch, tmp_path):
    ex.example_advanced_scheduling()
    out = capsys.readouterr().out
    assert "Example 4 complete" in out and "Operation Summary" in out
    assert list(tmp_path.glob("electrolyser_pem_*.csv")) and list(tmp_path.glob("electrolyser_pem_*.json"))


def test_safety_example_reports_the_voltage_alert(capsys):
    ex.example_safety_monitoring()
    out = capsys.readouterr().out
    assert "Voltage too high" in out and "Setpoint accepted: False" in out


def test_production_example_prints_one_row_per_power_level(capsys):
    ex.example_production_calculation()
    rows = [l for l in capsys.readouterr().out.splitlines() if l[:1].isdigit()]
    assert [r.split()[0] for r in rows] == ["500", "1000", "2000", "3000", "4000", "4500"]


@pytest.mark.parametrize("choice,marker", [("1", "Example 1 complete"), ("7", "Example 7 complete")])
def test_main_runs_the_selected_example(monkeypatch, capsys, choice, marker):
    monkeypatch.setattr("sys.argv", ["electrolyser_examples.py", choice])
    ex.main()
    out = capsys.readouterr().out
    assert "Available Examples" in out and marker in out


def test_main_prompts_when_no_argument_is_given(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["electrolyser_examples.py"])
    monkeypatch.setattr("builtins.input", lambda prompt="": " 1 ")
    ex.main()
    assert "Example 1 complete" in capsys.readouterr().out


def test_main_rejects_an_unknown_choice(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["electrolyser_examples.py", "zzz"])
    ex.main()
    assert "Invalid choice" in capsys.readouterr().out


def test_main_all_runs_every_example_in_order(monkeypatch, capsys):
    calls = []
    for n in range(1, 9):
        fn = (lambda n=n: calls.append(n))
        monkeypatch.setattr(ex, f"example_{['basic_pem_operation','voltage_ramp_up','power_ramp_up','advanced_scheduling','electrolyser_comparison','frequency_variation','safety_monitoring','production_calculation'][n-1]}", fn)
    monkeypatch.setattr("sys.argv", ["electrolyser_examples.py", "all"])
    ex.main()
    assert calls == [1, 2, 3, 4, 5, 6, 7, 8]
