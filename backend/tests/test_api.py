import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    import importlib
    import app.main as main
    importlib.reload(main)
    # Không có LLM thật trong test: chặn chạy nền để chỉ kiểm API.
    monkeypatch.setattr(main.orch, "schedule", lambda job_id: None)
    return TestClient(main.app), main


def test_create_list_detail(client):
    c, _ = client
    r = c.post("/jobs", data={"description": "viết script"}, files=[("files", ("a.txt", b"hi"))])
    jid = r.json()["id"]
    assert c.get("/jobs").json()[0]["state"] == "intake"
    d = c.get(f"/jobs/{jid}").json()
    assert d["step"] == 1 and d["brief"] is None
    assert any(f["path"] == "inputs/a.txt" for f in c.get(f"/jobs/{jid}/files").json())


def test_wrong_state_is_409_and_unknown_is_404(client):
    c, _ = client
    jid = c.post("/jobs", data={"description": "x"}).json()["id"]
    assert c.post(f"/jobs/{jid}/brief/approve").status_code == 409
    assert c.post("/jobs/nope/brief/approve").status_code == 404


def test_file_download_cannot_escape(client, tmp_path):
    c, _ = client
    (tmp_path / "secret.txt").write_text("s")
    jid = c.post("/jobs", data={"description": "x"}).json()["id"]
    assert c.get(f"/jobs/{jid}/files/inputs").status_code == 404
    assert c.get(f"/jobs/{jid}/files/..%5C..%5Csecret.txt").status_code == 404
    assert c.get(f"/jobs/{jid}/files/log.md").status_code == 200
