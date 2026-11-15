import pytest

from app.db import DB
from app.jobs import machine as m
from app.jobs.machine import InvalidAction, Orchestrator, parse_verdict


def wf(path, content, id="1"):
    import json
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": id, "type": "function", "function": {"name": "write_file",
         "arguments": json.dumps({"path": path, "content": content})}}]}


def say(t):
    return {"role": "assistant", "content": t}


class Script:
    """LLM giả phát lại kịch bản theo thứ tự; hết kịch bản là test sai."""
    def __init__(self, *replies):
        self.replies = list(replies)

    async def chat(self, combo, messages, tools=None, max_tokens=4096):
        return {"model": "fake", "message": self.replies.pop(0)}


@pytest.fixture
def orch(tmp_path):
    def make(llm):
        return Orchestrator(DB(tmp_path / "t.sqlite"), llm, tmp_path / "jobs", tmp_path / "lessons.md")
    return make


def test_transition_table_is_closed():
    # Mọi trạng thái đích phải tồn tại, và trạng thái cuối không đi đâu nữa.
    for src, dsts in m.TRANSITIONS.items():
        assert dsts <= set(m.TRANSITIONS)
    assert m.TRANSITIONS[m.DONE] == set()


def test_verdict_parsing():
    assert parse_verdict("KẾT QUẢ: PASS\n...") == "PASS"
    assert parse_verdict("**KẾT QUẢ: FAIL**") == "FAIL"
    assert parse_verdict("kết quả: **pass**") == "PASS"
    assert parse_verdict("không biết") is None


def test_actions_rejected_in_wrong_state(orch):
    o = orch(Script())
    jid = o.create_job("việc")
    for act in (lambda: o.approve_brief(jid), lambda: o.approve_handoff(jid), lambda: o.answer(jid, "x"),
                lambda: o.reject_brief(jid, "x"), lambda: o.reject_handoff(jid, "x")):
        with pytest.raises(InvalidAction):
            act()
    with pytest.raises(InvalidAction):
        o.set_state(jid, m.DONE)  # nhảy cóc intake -> done


async def test_full_flow_two_human_stops(orch):
    llm = Script(
        wf("brief.md", "# brief"), say("ĐÃ VIẾT BRIEF"),                    # intake
        wf("plan.md", "T1"), say("ok"),                                     # planning
        wf("deliverables/a.py", "print(1)"), say("BÁO CÁO XONG"),           # executing
        say("KẾT QUẢ: PASS\nđạt hết"),                                      # qa
        wf("deliverables/HANDOFF.md", "# giao"), say("ok"),                 # handoff
        say("- bài học một\n- bài học hai"),                                # lessons
    )
    o = orch(llm)
    jid = o.create_job("viết script")
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_BRIEF            # dừng điểm 1
    o.approve_brief(jid)
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_HANDOFF          # dừng điểm 2
    assert (o.job_dir(jid) / "deliverables" / "HANDOFF.md").exists()
    o.approve_handoff(jid)
    await o.run(jid)
    assert o.get(jid)["state"] == m.DONE
    assert "bài học một" in (o.lessons_path).read_text(encoding="utf-8")


async def test_director_question_then_answer(orch):
    llm = Script(say("CÂU HỎI: 1. Định dạng ảnh? (mặc định JPG)"), wf("brief.md", "b"), say("ok"))
    o = orch(llm)
    jid = o.create_job("việc mơ hồ")
    await o.run(jid)
    assert o.get(jid)["state"] == m.WAITING_ANSWER
    o.answer(jid, "JPG")
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_BRIEF
    assert "JPG" in (o.job_dir(jid) / "answers.md").read_text(encoding="utf-8")


async def test_question_with_preamble_is_recognized(orch):
    o = orch(Script(say("Cần làm rõ vài điều.\n\nCÂU HỎI:\n1. Định dạng? (mặc định JPG)")))
    jid = o.create_job("x")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.WAITING_ANSWER and j["questions"].startswith("CÂU HỎI")


async def test_reject_brief_requires_new_brief(orch):
    # Nếu Giám đốc không ghi lại brief.md sau khi bị trả thì job không được lọt qua điểm duyệt.
    llm = Script(wf("brief.md", "v1"), say("ok"), say("không sửa gì"))
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    o.reject_brief(jid, "thiếu tiêu chí")
    await o.run(jid)
    assert o.get(jid)["state"] == m.BLOCKED


async def _to_executing(o, jid):
    o.set_state(jid, m.AWAITING_BRIEF)
    o.approve_brief(jid)
    (o.job_dir(jid) / "brief.md").write_text("b", encoding="utf-8")
    o.set_state(jid, m.EXECUTING)


async def test_qa_fail_twice_then_blocked(orch):
    fail = say("KẾT QUẢ: FAIL\nlỗi X")
    eng = [wf("deliverables/a.py", "x"), say("báo cáo")]
    llm = Script(*eng, fail, *eng, fail, *eng, fail)   # 1 lần làm + 2 vòng sửa, QA FAIL cả ba
    o = orch(llm)
    jid = o.create_job("x")
    o.set_state(jid, m.AWAITING_BRIEF)
    o.approve_brief(jid)
    o.set_state(jid, m.EXECUTING)
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.BLOCKED and j["fix_round"] == 2 and not llm.replies


async def test_qa_fail_feedback_reaches_engineer_then_pass(orch):
    seen = []

    class Spy(Script):
        async def chat(self, combo, messages, tools=None, max_tokens=4096):
            seen.append(messages[1]["content"])
            return await super().chat(combo, messages, tools, max_tokens)

    llm = Spy(wf("deliverables/a.py", "x"), say("b"), say("KẾT QUẢ: FAIL\nthiếu dry-run"),
              wf("deliverables/a.py", "y"), say("b"), say("KẾT QUẢ: PASS"))
    o = orch(llm)
    jid = o.create_job("x")
    o.set_state(jid, m.AWAITING_BRIEF)
    o.approve_brief(jid)
    o.set_state(jid, m.EXECUTING)
    await o.run(jid)
    assert o.get(jid)["state"] == m.HANDOFF or o.get(jid)["state"] == m.BLOCKED
    assert any("thiếu dry-run" in s for s in seen)     # lỗi QA được chuyển NGUYÊN VĂN cho Kỹ sư
    assert o.get(jid)["fix_round"] == 1


async def test_resume_reruns_running_state(orch, tmp_path):
    o = orch(Script(wf("brief.md", "b"), say("ok")))
    jid = o.create_job("x")                      # trạng thái intake = "đang chạy", như thể backend chết giữa chừng
    o.resume_interrupted()
    await o._tasks[jid]
    assert o.get(jid)["state"] == m.AWAITING_BRIEF
    kinds = [e["kind"] for e in o.db.query("SELECT kind FROM events WHERE job_id=?", (jid,))]
    assert "resume" in kinds


async def test_upload_name_cannot_escape(orch):
    o = orch(Script())
    jid = o.create_job("x", [("..\\..\\evil.txt", b"hi")])
    assert (o.job_dir(jid) / "inputs" / "evil.txt").exists()
    assert not (o.job_dir(jid).parent / "evil.txt").exists()


async def test_retry_blocked_qa_goes_back_to_executing_with_note(orch):
    fail = say("KẾT QUẢ: FAIL lỗi X")
    eng = [wf("deliverables/a.py", "x"), say("b")]
    llm = Script(*eng, fail, *eng, fail, *eng, fail,          # hết 2 vòng sửa -> blocked
                 wf("deliverables/a.py", "fixed"), say("b"), say("KẾT QUẢ: PASS"))
    o = orch(llm)
    jid = o.create_job("x")
    o.set_state(jid, m.AWAITING_BRIEF)
    o.approve_brief(jid)
    o.set_state(jid, m.EXECUTING)
    await o.run(jid)
    assert o.get(jid)["state"] == m.BLOCKED and o.get(jid)["blocked_from"] == m.QA
    o.retry(jid, "đừng dùng EXIF")
    j = o.get(jid)
    assert j["state"] == m.EXECUTING and j["fix_round"] == 0 and "đừng dùng EXIF" in j["note"] and j["error"] is None
    await o.run(jid)
    assert o.get(jid)["state"] == m.HANDOFF or o.get(jid)["state"] == m.BLOCKED


def test_retry_only_when_blocked(orch):
    o = orch(Script())
    jid = o.create_job("x")
    with pytest.raises(InvalidAction):
        o.retry(jid)
