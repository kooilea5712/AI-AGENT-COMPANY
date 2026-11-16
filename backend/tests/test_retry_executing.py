import json

from app.db import DB
from app.jobs import machine as m
from app.jobs.machine import Orchestrator


def _orch(tmp_path):
    return Orchestrator(DB(tmp_path / "t.sqlite"), object(), tmp_path / "jobs", tmp_path / "l.md")


def _blocked_in_fix(o):
    jid = o.create_job("x")
    o.set_state(jid, m.BRIEF_REVIEW); o.set_state(jid, m.PLANNING)
    o.set_state(jid, m.EXECUTING, round=1, fix_round=1)
    o.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, status) VALUES (?,?,?,?,?,?)", (jid, 1, "T1", "software", "a", "done"))
    o.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, status) VALUES (?,?,?,?,?,?)", (jid, 1, "FIX1", "software", "sửa", "failed"))
    o.set_state(jid, m.BLOCKED, error="hết giới hạn 25 bước", blocked_from=m.EXECUTING)
    return jid


def test_retry_from_blocked_fix_keeps_fix_round_so_the_failed_fix_task_reruns(tmp_path):
    o = _orch(tmp_path)
    jid = _blocked_in_fix(o)
    o.retry(jid, "Hợp nhất cây thư mục trước")
    j = o.get(jid)
    assert j["state"] == m.EXECUTING and j["fix_round"] == 1                  # KHÔNG reset: FIX1 phải được chạy lại
    assert "Hợp nhất cây thư mục trước" in j["note"]                          # và hướng dẫn của chủ tới được model con


def test_retry_after_qa_run_block_still_resets_fix_rounds(tmp_path):
    o = _orch(tmp_path)
    jid = o.create_job("x")
    o.set_state(jid, m.BRIEF_REVIEW); o.set_state(jid, m.PLANNING); o.set_state(jid, m.EXECUTING, round=1)
    o.set_state(jid, m.QA_DESIGN); o.set_state(jid, m.QA_RUN)
    o.set_state(jid, m.BLOCKED, error="vẫn FAIL", blocked_from=m.QA_RUN, fix_round=2)
    o.retry(jid, "làm lại")
    j = o.get(jid)
    assert j["state"] == m.EXECUTING and j["fix_round"] == 0                  # hết vòng sửa: cấp lại đủ lượt như trước


async def test_fix_tasks_are_unique_so_engineer_runs_again_after_a_reset(tmp_path):
    """Lỗi cũ: FIX1/FIX2 đã 'xong' từ lần trước; sau 'Tiếp tục' (fix_round về 0) rồi FAIL lại thì FIX1 bị coi là đã làm và Kỹ sư KHÔNG được gọi."""
    import json

    class Eng:
        def __init__(self):
            self.n = 0

        async def chat(self, role, messages, tools=None, max_tokens=4096):
            self.n += 1
            if self.n == 1:
                return {"model": "f", "connection": "f", "failed": [], "message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "1", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": "a.txt", "content": "x"})}}]}}
            return {"model": "f", "connection": "f", "failed": [], "message": {"role": "assistant", "content": "xong"}}

    eng = Eng()
    o = Orchestrator(DB(tmp_path / "t.sqlite"), eng, tmp_path / "jobs", tmp_path / "l.md")
    jid = o.create_job("x")
    o.set_state(jid, m.BRIEF_REVIEW); o.set_state(jid, m.PLANNING)
    o.set_state(jid, m.EXECUTING, round=1, fix_round=0)
    (o.job_dir(jid) / "plan.json").write_text(json.dumps({"summary": "s", "tasks": [
        {"id": "T1", "role": "software", "title": "a", "goal": "g", "outputs": ["a.txt"]}]}), encoding="utf-8")
    for tid, st in (("T1", "done"), ("FIX1", "done"), ("FIX2", "done")):      # đã có FIX1, FIX2 xong từ vòng trước
        o.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, status) VALUES (?,?,?,?,?,?)", (jid, 1, tid, "software", tid, st))
    o.db.execute("UPDATE jobs SET fix_round=1 WHERE id=?", (jid,))            # QA vừa FAIL lần nữa sau khi chủ reset: vòng sửa 1
    await o._do_executing(jid)
    ids = [r["task_id"] for r in o.db.query("SELECT task_id FROM tasks WHERE job_id=? ORDER BY id", (jid,))]
    assert ids == ["T1", "FIX1", "FIX2", "FIX3"]                             # tạo FIX3 mới thay vì tái dùng FIX1 đã xong
    assert eng.n >= 1 and (o.work_root(jid) / "a.txt").exists()               # và Kỹ sư thật sự đã chạy
    assert o.get(jid)["state"] == m.QA_DESIGN


async def test_interrupted_fix_task_is_resumed_not_duplicated(tmp_path):
    o = Orchestrator(DB(tmp_path / "t.sqlite"), object(), tmp_path / "jobs", tmp_path / "l.md")
    jid = _blocked_in_fix(o)                                                 # FIX1 đang ở trạng thái 'failed'
    o.retry(jid, "tiếp")
    rows_before = o.db.query("SELECT task_id FROM tasks WHERE job_id=? AND task_id LIKE 'FIX%'", (jid,))
    assert [r["task_id"] for r in rows_before] == ["FIX1"]                   # chưa tạo thêm: lần chạy tới sẽ dùng lại chính FIX1
