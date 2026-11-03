"""Seeded simulations must reproduce the numbers recorded from the pre-refactor code exactly."""
import json
from pathlib import Path

import pytest
import sim_harness

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "tests" / "golden" / "simulation_baseline.json").read_text())
SECTIONS = sorted(GOLDEN)


def _close(a, b):
    """Deep equality with floats compared to 1e-9 relative (last-digit sums differ across numpy builds)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == pytest.approx(b, rel=1e-9, abs=1e-12)
    return a == b


@pytest.fixture(scope="module")
def current():
    # round-trip through JSON so tuples/lists compare like the stored file
    return json.loads(json.dumps(sim_harness.run_all(str(ROOT))))


@pytest.mark.parametrize("section", SECTIONS)
def test_section_matches_baseline(current, section):
    assert _close(current[section], GOLDEN[section])
