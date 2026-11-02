"""Seeded simulations must reproduce the numbers recorded from the pre-refactor code exactly."""
import json
from pathlib import Path

import pytest

import sim_harness

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "tests" / "golden" / "simulation_baseline.json").read_text())
SECTIONS = sorted(GOLDEN)


@pytest.fixture(scope="module")
def current():
    # round-trip through JSON so tuples/lists compare like the stored file
    return json.loads(json.dumps(sim_harness.run_all(str(ROOT))))


@pytest.mark.parametrize("section", SECTIONS)
def test_section_matches_baseline(current, section):
    assert current[section] == GOLDEN[section]
