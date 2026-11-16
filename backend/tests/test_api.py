import json

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


def test_flow_shows_handoffs_between_staff(client):
    c, main = client
    o = main.orch
    jid = o.create_job("x")
    # Hai task: Kỹ sư rồi Chuyên viên media (giả lập đang chạy)
    o.set_state(jid, "brief_review")
    o.set_state(jid, "planning")
    o.set_state(jid, "executing", round=1)
    for tid, role, st in (("T1", "software", "done"), ("T2", "media", "running")):
        main.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, status, started, ended) VALUES (?,?,?,?,?,?,?,?)",
                        (jid, 1, tid, role, "việc " + tid, st, __import__("time").time(), None if st == "running" else __import__("time").time()))
    f = c.get(f"/jobs/{jid}/flow").json()
    assert [s["actor"] for s in f["segments"]][:3] == ["Giám đốc điều phối", "Giám đốc điều phối", "Giám đốc điều phối"]
    ex = [s for s in f["segments"] if s["state"] == "executing"]
    assert [s["actor"] for s in ex] == ["Kỹ sư phần mềm", "Chuyên viên media"]          # mỗi task một đoạn, đúng vai
    pairs = [(h["from"], h["to"]) for h in f["handoffs"]]
    assert ("Giám đốc điều phối", "Kỹ sư phần mềm") in pairs and ("Kỹ sư phần mềm", "Chuyên viên media") in pairs
    assert f["current"]["actor"] == "Chuyên viên media" and f["current"]["working"] is True


def test_staff_status_and_models(client):
    c, main = client
    o = main.orch
    jid = o.create_job("x")                       # intake -> Giám đốc đang làm
    st = {p["id"]: p for p in c.get("/staff").json()["staff"]}
    assert st["director"]["status"] == "working" and st["director"]["tasks"][0]["id"] == jid
    assert st["qa"]["status"] == "idle" and st["tester"]["status"] == "idle" and st["game"]["status"] == "planned"
    assert st["director"]["models"][0].startswith("anthropic/claude-opus")        # Giám đốc gắn với Claude Opus (bị bỏ qua nếu chưa có khoá)
    o.set_state(jid, "waiting_answer", questions="CÂU HỎI: ?")
    st = {p["id"]: p for p in c.get("/staff").json()["staff"]}
    assert st["owner"]["status"] == "waiting" and st["director"]["status"] == "idle"


def test_answer_really_schedules_job(client, monkeypatch):
    """Không chặn schedule: hành động của chủ phải thật sự khởi động lại job (không 500, không đứng im)."""
    import time
    c, main = client
    monkeypatch.undo()
    from app import config
    monkeypatch.setattr(config, "JOBS_DIR", main.orch.jobs_dir)

    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("không có LLM trong test")

    main.orch.llm = Boom()
    jid = main.orch.create_job("x")
    main.orch.set_state(jid, "waiting_answer", questions="CÂU HỎI: ?")
    r = c.post(f"/jobs/{jid}/answer", data={"text": "mặc định"}, files=[("files", ("a.txt", b"1"))])
    assert r.status_code == 200
    for _ in range(40):
        if main.orch.get(jid)["state"] != "intake":
            break
        time.sleep(0.1)
    assert main.orch.get(jid)["state"] == "blocked"
    assert any("a.txt" in f["path"] for f in c.get(f"/jobs/{jid}/files").json())     # file đính kèm khi trả lời đã được lưu


def test_message_endpoint_and_conversation(client):
    c, main = client
    jid = c.post("/jobs", data={"description": "x"}).json()["id"]
    assert c.post(f"/jobs/{jid}/message", data={"text": ""}).status_code == 422
    assert c.post(f"/jobs/{jid}/message", data={"text": "thêm yêu cầu"}, files=[("files", ("y.pdf", b"%PDF"))]).status_code == 200
    conv = c.get(f"/jobs/{jid}/conversation").json()
    assert [m["sender"] for m in conv] == ["owner", "owner"] and conv[1]["files"][0].endswith("y.pdf")


def test_create_job_with_bad_workspace_is_400(client):
    c, _ = client
    r = c.post("/jobs", data={"description": "x", "workspace": "C:/Windows"})
    assert r.status_code == 400 and "thư mục" in r.json()["detail"]
    assert c.post("/workspace/check", data={"path": "C:/Windows"}).json()["ok"] is False


def test_settings_roundtrip_hides_keys_and_presets(client):
    c, _ = client
    s = c.get("/settings").json()
    assert s["roles"]["director"][0] == {"connection": "anthropic", "model": "claude-opus-5-5"}    # mặc định: Opus làm Giám đốc
    assert s["roles"]["qa_author"][0]["model"] == "claude-sonnet-5-5" and s["roles"]["qa_runner"][0]["model"] == "claude-haiku-5-5"
    r = c.put("/settings", json={"connections": {"anthropic": {"api_key": "sk-ant-SECRET-1234"}}, "owner_approves_brief": True}).json()
    assert "SECRET" not in json.dumps(r) and r["connections"]["anthropic"]["has_key"] and r["connections"]["anthropic"]["key_hint"] == "…1234"
    assert r["owner_approves_brief"] is True
    # Preset "chỉ local" thay chuỗi của mọi vai
    local = next(p for p in r["presets"] if p["id"] == "local")
    r = c.put("/settings", json={"roles": local["roles"]}).json()
    assert r["roles"]["director"] == [{"connection": "ollama", "model": "studio-gemma4-12b"}]
    assert c.put("/settings", json={"roles": {"nope": [["ollama", "x"]]}}).status_code == 422
    # Khoá không bao giờ nằm trong repo hay trong phản hồi; chỉ trong file cài đặt của người dùng
    from app import settings
    assert "sk-ant-SECRET-1234" in settings.SETTINGS_FILE.read_text(encoding="utf-8")


def test_git_endpoint_lists_job_commits(client):
    c, main = client
    jid = main.orch.create_job("x")
    main.orch._commit(jid, "thử")
    g = c.get(f"/jobs/{jid}/git").json()
    assert g["commits"][0]["message"].endswith("thử") and g["job_repo"][0]["subject"].endswith("thử")
    rev = g["job_repo"][0]["hash"]
    assert "thử" in c.get(f"/jobs/{jid}/git/{rev}").json()["text"]
    assert c.get(f"/jobs/{jid}/git/zzzz").status_code == 400
    assert c.get(f"/jobs/{jid}/files/.git/HEAD").status_code == 404                  # không tải được ruột .git


def test_job_detail_survives_broken_testcases_json(client):
    c, main = client
    jid = main.orch.create_job("x")
    (main.orch.job_dir(jid) / "qa" / "testcases.json").write_text('{"cases": [ {"id": "TC1" ', encoding="utf-8")   # JSON dở dang
    r = c.get(f"/jobs/{jid}")
    assert r.status_code == 200 and r.json()["testcases"] == []


def test_workspace_files_show_real_code_with_changed_flags_even_uncommitted(client, tmp_path):
    import subprocess
    c, main = client
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "app").mkdir()
    (ws / "app" / "old.py").write_text("print('cũ')", encoding="utf-8")
    from app import gitops
    gitops.init_repo(ws)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-q", "-m", "init"], cwd=ws, check=True)
    jid = main.orch.create_job("sửa", workspace=str(ws))
    (ws / "app" / "compose.py").write_text("print('mới')", encoding="utf-8")        # file MỚI, chưa commit (đang làm dở giữa task)
    (ws / "app" / "old.py").write_text("print('sửa')", encoding="utf-8")            # file CŨ bị sửa, chưa commit
    (ws / "node_modules").mkdir(); (ws / "node_modules" / "x.js").write_text("x", encoding="utf-8")
    r = c.get(f"/jobs/{jid}/workspace/files").json()
    files = {f["path"]: f["changed"] for f in r["files"]}
    assert files["app/compose.py"] == "A" and files["app/old.py"] == "M"
    assert not any(p.startswith("node_modules") or ".git/" in p for p in files)       # rác không hiện
    assert c.get(f"/jobs/{jid}/workspace/files/app/compose.py").text == "print('mới')"
    assert c.get(f"/jobs/{jid}/workspace/files/.git/HEAD").status_code == 404
    assert c.get(f"/jobs/{jid}/workspace/files/..%5C..%5Cetc").status_code == 404
    plain = main.orch.create_job("thường")
    assert c.get(f"/jobs/{plain}/workspace/files").status_code == 404
