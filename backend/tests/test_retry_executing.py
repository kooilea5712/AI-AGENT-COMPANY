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
