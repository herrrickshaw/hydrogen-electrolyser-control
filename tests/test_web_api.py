"""Smoke tests for the Flask API using the in-process test client (no sockets, no network)."""
import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_cors")

import electrolyser_web_api as api  # noqa: E402
from electrolyser_control_system import ElectrolyserType  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api.init_api(ElectrolyserType.PEM)
    yield api.app.test_client()
    api.controller = None


def test_health_without_controller():
    api.controller = None
    body = api.app.test_client().get("/api/health").get_json()
    assert body["status"] == "healthy" and body["electrolyser_type"] is None


def test_health_and_specs(client):
    assert client.get("/api/health").get_json()["electrolyser_type"] == "PEM"
    assert client.get("/api/specs").status_code == 200


def test_status_unavailable_before_start(client):
    assert client.get("/api/status").status_code == 503


def test_ramp_validation(client):
    assert client.post("/api/schedule/power-ramp", json={"start_power": 1}).status_code == 400
    bad = client.post("/api/schedule/power-ramp",
                      json={"start_power": 1, "end_power": 2, "duration": 3, "profile": "NOPE"})
    assert bad.status_code == 400
    ok = client.post("/api/schedule/power-ramp",
                     json={"start_power": 1000, "end_power": 4000, "duration": 20, "profile": "linear"})
    assert ok.get_json()["status"] == "scheduled"


def test_emergency_stop_sets_flag(client):
    r = client.post("/api/emergency/stop", json={"reason": "test"})
    assert r.get_json()["status"] == "emergency_stop_triggered"
    assert api.controller.safety_interlocks.emergency_stop is True
    client.post("/api/emergency/clear")
    assert api.controller.safety_interlocks.emergency_stop is False
