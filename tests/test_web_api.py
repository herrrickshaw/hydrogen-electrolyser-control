import sys
import types

import pytest

import electrolyser_web_api as api
from electrolyser_control_system import ElectrolyserType


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "controller", None)
    return api.app.test_client()


@pytest.fixture
def live(client):
    api.init_api(ElectrolyserType.PEM)
    return client


def prime_status(c):
    """Run one control pass so there is a status to report."""
    c.system.start_operation()
    c.last_status = c.system.get_status()


# ------------------------------------------------------------------ before init
GET_PATHS = ["/api/status", "/api/specs", "/api/monitoring/safety", "/api/monitoring/summary",
             "/api/monitoring/production", "/api/monitoring/performance", "/api/export/csv", "/api/stream/status"]
POST_PATHS = ["/api/control/start", "/api/control/stop", "/api/control/voltage", "/api/control/power",
              "/api/control/frequency", "/api/schedule/power-ramp", "/api/schedule/voltage-ramp",
              "/api/export/report", "/api/config/update-interval", "/api/emergency/stop", "/api/emergency/clear"]


def test_health_without_controller(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "healthy" and body["electrolyser_type"] is None and body["running"] is False


@pytest.mark.parametrize("path", GET_PATHS)
def test_get_endpoints_report_uninitialised_controller(client, path):
    r = client.get(path)
    assert r.status_code == 500 and r.get_json() == {"error": "Controller not initialized"}


@pytest.mark.parametrize("path", POST_PATHS)
def test_post_endpoints_report_uninitialised_controller(client, path):
    r = client.post(path, json={})
    assert r.status_code == 500 and r.get_json() == {"error": "Controller not initialized"}


# ------------------------------------------------------------------ health, specs, status
def test_health_with_controller(live):
    body = live.get("/api/health").get_json()
    assert body["electrolyser_type"] == "PEM" and body["running"] is False


def test_specs_mirror_the_electrolyser(live):
    s = api.controller.system.electrolyser.specs
    body = live.get("/api/specs").get_json()
    assert body["type"] == "PEM" and body["nominal_power"] == s.nominal_power
    assert body["temperature_range"] == [s.temperature_min, s.temperature_max]
    assert body["pressure_range"] == [s.pressure_min, s.pressure_max]
    assert body["hydrogen_production_rate"] == s.hydrogen_production_rate


@pytest.mark.parametrize("path", ["/api/status", "/api/monitoring/safety", "/api/monitoring/production",
                                  "/api/monitoring/performance", "/api/stream/status"])
def test_status_endpoints_503_until_a_status_exists(live, path):
    r = live.get(path)
    assert r.status_code == 503 and r.get_json() == {"error": "No status available"}


def test_status_endpoints_with_status(live):
    prime_status(api.controller)
    st = live.get("/api/status").get_json()
    assert st["type"] == "PEM" and st["mode"] == "RAMP_UP"
    safety = live.get("/api/monitoring/safety").get_json()
    assert safety["safe"] is True and safety["alerts"] == [] and safety["warnings"] == []
    prod = live.get("/api/monitoring/production").get_json()
    assert set(prod) == {"hydrogen_produced_nm3", "oxygen_produced_nm3", "water_consumed_liters",
                         "efficiency_percent", "timestamp"}
    perf = live.get("/api/monitoring/performance").get_json()
    assert perf["mode"] == "RAMP_UP" and set(perf) >= {"voltage", "current", "power", "efficiency", "run_time"}
    stream = live.get("/api/stream/status").get_json()
    assert stream["data"]["type"] == "PEM" and "timestamp" in stream


def test_safety_endpoint_lists_alerts(live):
    api.controller.system.set_voltage(1e6)
    api.controller.last_status = api.controller.system.get_status()
    body = live.get("/api/monitoring/safety").get_json()
    assert body["safe"] is False and "Voltage too high" in body["alerts"][0]


def test_summary_endpoint_is_empty_then_populated(live):
    assert live.get("/api/monitoring/summary").get_json() == {}
    from test_advanced_control import event
    api.controller.logger.log_event(event(0))
    assert live.get("/api/monitoring/summary").get_json()["total_events"] == 1


def test_csv_endpoint_returns_log_paths(live):
    body = live.get("/api/export/csv").get_json()
    assert body == {"csv_file": api.controller.logger.csv_file, "json_file": api.controller.logger.json_file}


# ------------------------------------------------------------------ control
def test_start_and_stop_endpoints(live):
    r = live.post("/api/control/start")
    assert r.status_code == 200 and r.get_json()["status"] == "started"
    assert live.get("/api/health").get_json()["running"] is True
    r = live.post("/api/control/stop")
    assert r.status_code == 200 and r.get_json()["status"] == "stopped"
    assert live.get("/api/health").get_json()["running"] is False


def test_start_and_stop_errors_are_400(live, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(api.controller, "start", boom)
    monkeypatch.setattr(api.controller, "stop", boom)
    assert live.post("/api/control/start").get_json() == {"error": "nope"}
    r = live.post("/api/control/stop")
    assert r.status_code == 400 and r.get_json() == {"error": "nope"}


@pytest.mark.parametrize("path,key", [("/api/control/voltage", "voltage"), ("/api/control/power", "power"),
                                      ("/api/control/frequency", "frequency")])
def test_setpoint_endpoints_validate_their_body(live, path, key):
    for body in ({}, {"other": 1}):
        r = live.post(path, json=body)
        assert r.status_code == 400 and r.get_json() == {"error": f"Missing '{key}' parameter"}


@pytest.mark.parametrize("path,key,good,bad", [
    ("/api/control/voltage", "voltage", 45.0, 1e6),
    ("/api/control/power", "power", 1000.0, 1e6),
    ("/api/control/frequency", "frequency", 55.0, 70.0),
])
def test_setpoint_endpoints_report_success_flag(live, path, key, good, bad):
    ok = live.post(path, json={key: good}).get_json()
    assert ok["success"] is True and ok[key] == good and "timestamp" in ok
    rejected = live.post(path, json={key: bad})
    assert rejected.status_code == 200 and rejected.get_json()["success"] is False


@pytest.mark.parametrize("path,key", [("/api/control/voltage", "voltage"), ("/api/control/power", "power"),
                                      ("/api/control/frequency", "frequency")])
def test_setpoint_type_errors_are_400(live, path, key):
    r = live.post(path, json={key: "not a number"})
    assert r.status_code == 400 and "error" in r.get_json()


# ------------------------------------------------------------------ schedules
def test_power_ramp_endpoint(live):
    r = live.post("/api/schedule/power-ramp",
                  json={"start_power": 100, "end_power": 900, "duration": 8, "profile": "step"})
    body = r.get_json()
    assert r.status_code == 200 and body["status"] == "scheduled"
    assert body["power_ramp"] == {"start": 100, "end": 900, "duration": 8, "profile": "STEP"}
    sch = api.controller.power_schedule
    assert (sch.start_value, sch.end_value, sch.duration_seconds, sch.profile.value) == (100, 900, 8, "STEP")


def test_voltage_ramp_endpoint_defaults_to_linear(live):
    r = live.post("/api/schedule/voltage-ramp", json={"start_voltage": 30, "end_voltage": 45, "duration": 5})
    assert r.get_json()["voltage_ramp"]["profile"] == "LINEAR"
    assert api.controller.voltage_schedule.profile.value == "LINEAR"


@pytest.mark.parametrize("path,fields", [
    ("/api/schedule/power-ramp", {"start_power": 1, "end_power": 2}),
    ("/api/schedule/voltage-ramp", {"start_voltage": 1, "duration": 2}),
])
def test_ramp_endpoints_need_all_parameters(live, path, fields):
    r = live.post(path, json=fields)
    assert r.status_code == 400 and r.get_json()["error"].startswith("Missing parameters")
    assert live.post(path, json={}).status_code == 400


@pytest.mark.parametrize("path,fields", [
    ("/api/schedule/power-ramp", {"start_power": 1, "end_power": 2, "duration": 3}),
    ("/api/schedule/voltage-ramp", {"start_voltage": 1, "end_voltage": 2, "duration": 3}),
])
def test_ramp_endpoints_reject_unknown_profile(live, path, fields):
    r = live.post(path, json={**fields, "profile": "zigzag"})
    assert r.status_code == 400 and "Invalid profile" in r.get_json()["error"]


@pytest.mark.parametrize("path,fields,method", [
    ("/api/schedule/power-ramp", {"start_power": 1, "end_power": 2, "duration": 3}, "set_power_ramp"),
    ("/api/schedule/voltage-ramp", {"start_voltage": 1, "end_voltage": 2, "duration": 3}, "set_voltage_ramp"),
])
def test_ramp_endpoints_report_unexpected_errors(live, monkeypatch, path, fields, method):
    def boom(**k):
        raise RuntimeError("bad ramp")

    monkeypatch.setattr(api.controller, method, boom)
    r = live.post(path, json=fields)
    assert r.status_code == 400 and r.get_json() == {"error": "bad ramp"}


# ------------------------------------------------------------------ export / config
def test_export_report_endpoint(live, tmp_path):
    r = live.post("/api/export/report", json={"filename": "out.json"})
    body = r.get_json()
    assert body["status"] == "exported" and body["filename"] == "out.json"
    assert (tmp_path / "out.json").exists()
    default = live.post("/api/export/report", json={}).get_json()
    assert default["filename"] == "electrolyser_report.json"


def test_export_report_errors_are_400(live, monkeypatch):
    monkeypatch.setattr(api.controller, "export_report", lambda f: (_ for _ in ()).throw(OSError("disk")))
    r = live.post("/api/export/report", json={"filename": "x.json"})
    assert r.status_code == 400 and r.get_json() == {"error": "disk"}


def test_update_interval_endpoint(live):
    r = live.post("/api/config/update-interval", json={"interval": "0.25"})
    assert r.get_json()["interval"] == 0.25 and api.controller.update_interval == 0.25
    assert live.post("/api/config/update-interval", json={}).status_code == 400
    bad = live.post("/api/config/update-interval", json={"interval": "fast"})
    assert bad.status_code == 400 and bad.get_json() == {"error": "Invalid interval value"}


# ------------------------------------------------------------------ emergency
def test_emergency_stop_and_clear_with_json_body(live):
    seen = []
    api.controller.register_safety_callback(lambda k, r: seen.append((k, r)))
    r = live.post("/api/emergency/stop", json={"reason": "leak"})
    assert r.get_json()["status"] == "emergency_stop_triggered" and r.get_json()["reason"] == "leak"
    assert api.controller.safety_interlocks.emergency_stop is True and seen == [("emergency_stop", "leak")]
    r = live.post("/api/emergency/clear")
    assert r.get_json()["status"] == "emergency_cleared"
    assert api.controller.safety_interlocks.emergency_stop is False


def test_emergency_stop_with_empty_json_object_uses_the_default_reason(live):
    r = live.post("/api/emergency/stop", json={})
    assert r.get_json()["reason"] == "Manual emergency stop"
    assert api.controller.safety_interlocks.emergency_stop is True


@pytest.mark.xfail(strict=True, reason="POST /api/emergency/stop without a JSON content type raises 415 "
                   "from request.get_json() instead of falling back to the default reason")
def test_emergency_stop_without_a_body_still_stops(live):
    r = live.post("/api/emergency/stop")
    assert r.status_code == 200
    assert api.controller.safety_interlocks.emergency_stop is True


# ------------------------------------------------------------------ client + server runner
class FakeRequests:
    def __init__(self):
        self.calls = []

    def _resp(self, method, url, json=None):
        self.calls.append((method, url, json))
        return types.SimpleNamespace(json=lambda: {"echo": [method, url, json]})

    def get(self, url):
        return self._resp("GET", url)

    def post(self, url, json=None):
        return self._resp("POST", url, json)


def test_client_calls_the_expected_endpoints(monkeypatch):
    fake = FakeRequests()
    monkeypatch.setitem(sys.modules, "requests", fake)
    c = api.ElectrolyserClient("http://h:1")
    c.health_check(); c.get_status(); c.start(); c.stop()
    c.set_voltage(45.0); c.set_power(1000.0); c.set_frequency(51.0)
    c.set_power_ramp(1, 2, 3, "STEP"); c.get_production(); c.emergency_stop("r")
    assert fake.calls == [
        ("GET", "http://h:1/api/health", None),
        ("GET", "http://h:1/api/status", None),
        ("POST", "http://h:1/api/control/start", None),
        ("POST", "http://h:1/api/control/stop", None),
        ("POST", "http://h:1/api/control/voltage", {"voltage": 45.0}),
        ("POST", "http://h:1/api/control/power", {"power": 1000.0}),
        ("POST", "http://h:1/api/control/frequency", {"frequency": 51.0}),
        ("POST", "http://h:1/api/schedule/power-ramp",
         {"start_power": 1, "end_power": 2, "duration": 3, "profile": "STEP"}),
        ("GET", "http://h:1/api/monitoring/production", None),
        ("POST", "http://h:1/api/emergency/stop", {"reason": "r"}),
    ]
    assert c.health_check()["echo"][0] == "GET"


def test_client_default_base_url(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", FakeRequests())
    assert api.ElectrolyserClient().base_url == "http://localhost:5000"


def test_run_server_starts_flask_with_the_chosen_type(monkeypatch, capsys):
    started = {}
    monkeypatch.setattr(api.app, "run", lambda **kw: started.update(kw))
    api.run_server(host="127.0.0.1", port=5055, electrolyser_type="aem")
    assert started == {"host": "127.0.0.1", "port": 5055, "debug": False}
    assert api.controller.system.electrolyser.specs.type == ElectrolyserType.AEM
    assert "Starting on 127.0.0.1:5055" in capsys.readouterr().out


def test_run_server_rejects_unknown_type(monkeypatch, capsys):
    monkeypatch.setattr(api, "controller", None)
    monkeypatch.setattr(api.app, "run", lambda **kw: pytest.fail("must not start"))
    api.run_server(electrolyser_type="fusion")
    assert "Unknown electrolyser type: fusion" in capsys.readouterr().out
    assert api.controller is None
