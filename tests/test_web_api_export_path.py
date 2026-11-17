"""POST /api/export/report took the caller's ``filename`` verbatim and handed it to
``open(filename, "w")``: any client that can reach the (unauthenticated) API could
write the report JSON to an arbitrary path on the server — absolute paths and
``..`` traversal included. The endpoint must refuse anything that is not a plain
``*.json`` file name and must never create a file outside the working directory."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import electrolyser_web_api as api  # noqa: E402
from electrolyser_advanced_control import AdvancedElectrolyserController, ElectrolyserType  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(api, "controller", AdvancedElectrolyserController(ElectrolyserType.PEM))
    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c


def test_export_refuses_absolute_path_outside_cwd(client, tmp_path):
    target = tmp_path / "outside" / "evil.json"
    target.parent.mkdir()
    resp = client.post("/api/export/report", json={"filename": str(target)})
    assert resp.status_code == 400
    assert not target.exists()


def test_export_refuses_parent_traversal(client, tmp_path):
    resp = client.post("/api/export/report", json={"filename": "../escaped.json"})
    assert resp.status_code == 400
    assert not (tmp_path / "escaped.json").exists()


@pytest.mark.parametrize("bad", ["report.txt", ".hidden.json", "a/b.json", "", 42])
def test_export_refuses_non_plain_json_names(client, bad):
    resp = client.post("/api/export/report", json={"filename": bad})
    assert resp.status_code == 400


def test_export_plain_name_still_writes_into_cwd(client, tmp_path):
    resp = client.post("/api/export/report", json={"filename": "my_report.json"})
    assert resp.status_code == 200
    assert resp.get_json()["filename"] == "my_report.json"
    assert (tmp_path / "cwd" / "my_report.json").exists()


def test_export_default_name_unchanged(client, tmp_path):
    resp = client.post("/api/export/report", json={})
    assert resp.status_code == 200
    assert (tmp_path / "cwd" / "electrolyser_report.json").exists()
