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


def test_answer_really_schedules_job(client, monkeypatch):
    """Không chặn schedule: kiểm hành động của chủ studio thật sự khởi động lại job (không 500, không đứng im)."""
    import time
    c, main = client
    monkeypatch.undo()  # bỏ chặn schedule của fixture
    from app import config
    monkeypatch.setattr(config, "JOBS_DIR", main.orch.jobs_dir)

    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("không có LLM trong test")

    main.orch.llm = Boom()
    jid = main.orch.create_job("x")
    main.orch.set_state(jid, "waiting_answer", questions="CÂU HỎI: ?")
    r = c.post(f"/jobs/{jid}/answer", json={"text": "mặc định"})
    assert r.status_code == 200
    for _ in range(40):
        if main.orch.get(jid)["state"] != "intake":
            break
        time.sleep(0.1)
    assert main.orch.get(jid)["state"] == "blocked"   # job đã chạy (và dừng vì LLM giả báo lỗi)


def test_flow_shows_handoffs_between_staff(client):
    c, main = client
    o = main.orch
    jid = o.create_job("x")
    (o.job_dir(jid) / "plan.md").write_text("VAI: media\nT1", encoding="utf-8")
    for st in ("awaiting_brief", "planning", "executing", "qa", "handoff"):
        o.set_state(jid, st)
    f = c.get(f"/jobs/{jid}/flow").json()
    assert [s["state"] for s in f["segments"]] == ["intake", "awaiting_brief", "planning", "executing", "qa", "handoff"]
    assert [s["actor"] for s in f["segments"]][3] == "Chuyên viên media"     # vai lấy từ plan.md
    pairs = [(h["from"], h["to"]) for h in f["handoffs"]]
    assert ("Giám đốc điều phối", "Chủ studio") in pairs and ("Chuyên viên media", "Kiểm định") in pairs
    assert f["current"]["actor"] == "Giám đốc điều phối" and f["current"]["working"] is True


def test_staff_status(client):
    c, main = client
    o = main.orch
    jid = o.create_job("x")                       # intake -> Giám đốc đang làm
    st = {p["id"]: p for p in c.get("/staff").json()["staff"]}
    assert st["director"]["status"] == "working" and st["director"]["tasks"][0]["id"] == jid
    assert st["qa"]["status"] == "idle" and st["game"]["status"] == "planned"
    o.set_state(jid, "awaiting_brief")
    st = {p["id"]: p for p in c.get("/staff").json()["staff"]}
    assert st["owner"]["status"] == "waiting" and st["director"]["status"] == "idle"
