import json
import subprocess

import pytest

from app import config, gitops, settings
from app.db import DB
from app.jobs import machine as m
from app.jobs.machine import InvalidAction, Orchestrator


def wf(path, content, id="1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": id, "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": path, "content": content})}}]}


def say(t):
    return {"role": "assistant", "content": t}


class Script:
    """LLM giả: mỗi VAI có hàng đợi câu trả lời riêng, nên test không phụ thuộc thứ tự gọi giữa các vai."""
    def __init__(self, **by_role):
        self.q = {k: list(v) for k, v in by_role.items()}
        self.calls = []

    async def chat(self, role, messages, tools=None, max_tokens=4096):
        self.calls.append((role, messages[-1]["content"] if isinstance(messages[-1].get("content"), str) else ""))
        return {"model": "fake", "connection": "fake", "message": self.q[role].pop(0), "failed": []}


PLAN1 = json.dumps({"summary": "làm một việc", "tasks": [
    {"id": "T1", "role": "software", "title": "viết script", "goal": "viết script", "outputs": ["deliverables/a.py"], "acceptance": ["chạy được"]}]})
CASES = json.dumps({"cases": [{"id": "TC1", "title": "chạy", "criterion": "chạy được", "steps": ["python deliverables/a.py"], "manual_check": "xem đầu ra"}]})


def director_front(plan=PLAN1):
    return [wf("@job/brief.md", "# brief"), say("ĐÃ VIẾT BRIEF"), say("DUYỆT đủ tiêu chí"), wf("@job/plan.json", plan), say("ĐÃ LẬP KẾ HOẠCH")]


def eng_ok():
    return [wf("deliverables/a.py", "print(1)"), say("BÁO CÁO XONG")]


def qa(verdict="PASS"):
    """Kiểm thử viên chạy MỖI case một lượt và trả lời theo mẫu 'KẾT QUẢ: PASS|FAIL'."""
    return dict(qa_author=[wf("@job/qa/testcases.json", CASES), say("ĐÃ VIẾT TESTCASE")],
                qa_runner=[say(f"KẾT QUẢ: {verdict} đã chạy, bằng chứng: " + ("ok" if verdict == "PASS" else "sai"))])


@pytest.fixture
def orch(tmp_path):
    def make(llm):
        return Orchestrator(DB(tmp_path / "t.sqlite"), llm, tmp_path / "jobs", tmp_path / "lessons.md")
    return make


def test_transition_table_is_closed():
    for src, dsts in m.TRANSITIONS.items():
        assert dsts <= set(m.TRANSITIONS)
    assert m.TRANSITIONS[m.QA_DESIGN] == {m.QA_RUN, m.BLOCKED}
    assert m.AWAITING_BRIEF not in m.TRANSITIONS[m.BRIEF_REVIEW] - {m.AWAITING_BRIEF}   # chỉ vào qua công tắc cài đặt


def test_actions_rejected_in_wrong_state(orch):
    o = orch(Script())
    jid = o.create_job("việc")
    for act in (lambda: o.approve_brief(jid), lambda: o.approve_handoff(jid), lambda: o.answer(jid, "x"),
                lambda: o.reject_brief(jid, "x"), lambda: o.feedback(jid, "x"), lambda: o.retry(jid)):
        with pytest.raises(InvalidAction):
            act()
    with pytest.raises(InvalidAction):
        o.set_state(jid, m.DONE)


async def test_full_flow_director_approves_brief_owner_only_sees_final(orch):
    llm = Script(director=director_front() + [wf("@job/deliverables/HANDOFF.md", "# giao"), say("ok"), say("- bài học một")],
                 engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("viết script")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.AWAITING_HANDOFF                 # KHÔNG dừng ở brief: Giám đốc tự duyệt
    assert "awaiting_brief" not in [e["message"].split(" -> ")[-1] for e in o.db.query("SELECT message FROM events WHERE kind='state'")]
    roles_called = [c[0] for c in llm.calls]
    assert roles_called.count("director") >= 5 and "qa_author" in roles_called and "qa_runner" in roles_called
    # Mỗi lần chạy đều có commit (brief, plan, task, testcase, kiểm thử, handoff)
    assert len(o.db.query("SELECT 1 FROM commits WHERE job_id=?", (jid,))) >= 6
    assert len(gitops.history(o.job_dir(jid))) >= 7
    o.approve_handoff(jid)
    await o.run(jid)
    assert o.get(jid)["state"] == m.DONE
    assert "bài học một" in o.lessons_path.read_text(encoding="utf-8")
    senders = [x["sender"] for x in o.conversation(jid)]
    assert senders[0] == "owner" and "director" in senders


async def test_owner_gate_is_optional_setting(orch):
    settings.update({"owner_approves_brief": True})
    llm = Script(director=director_front()[:3] + [wf("@job/plan.json", PLAN1), say("ĐÃ LẬP")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_BRIEF
    o.approve_brief(jid)
    await o.run(jid)                       # đi tiếp tới khi hết kịch bản Giám đốc (handoff chưa có -> dừng bất thường là chấp nhận được)
    assert o.get(jid)["round"] == 1


async def test_director_self_review_can_rewrite_once(orch):
    llm = Script(director=[wf("@job/brief.md", "v1"), say("ĐÃ VIẾT BRIEF"),
                           wf("@job/brief.md", "v2 đã sửa"), say("SỬA thiếu tiêu chí"),   # lượt duyệt 1: sửa
                           say("DUYỆT giờ ổn"),                                           # lượt duyệt 2
                           wf("@job/plan.json", PLAN1), say("ok")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert (o.job_dir(jid) / "brief.md").read_text(encoding="utf-8") == "v2 đã sửa"
    assert o.get(jid)["round"] == 1


BRIEF_TEXT = "# BRIEF: Tool\n\n## Mục tiêu\nLàm tool video dọc.\n\n## Tiêu chí nghiệm thu\n- Xuất được MP4 1080x1920 có thẻ."


async def test_brief_pasted_in_reply_is_saved_instead_of_blocking(orch):
    """Model yếu dán brief vào câu trả lời thay vì gọi write_file: hệ thống lưu hộ, job đi tiếp."""
    llm = Script(director=[say(f"ĐÃ VIẾT BRIEF\n\n@job/brief.md\n```markdown\n{BRIEF_TEXT}\n```"), say("DUYỆT"),
                           wf("@job/plan.json", PLAN1), say("ok")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert (o.job_dir(jid) / "brief.md").read_text(encoding="utf-8").startswith("# BRIEF: Tool")
    assert o.get(jid)["round"] == 1


async def test_director_reminded_once_to_write_brief_then_blocks(orch):
    llm = Script(director=[say("ĐÃ VIẾT BRIEF, @job/brief.md đã được tạo."), wf("@job/brief.md", BRIEF_TEXT), say("ĐÃ VIẾT BRIEF"),
                           say("DUYỆT"), wf("@job/plan.json", PLAN1), say("ok")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert "KHÔNG tạo file @job/brief.md" in [c for c in llm.calls if c[0] == "director"][1][1]
    assert o.get(jid)["round"] == 1

    llm2 = Script(director=[say("xong"), say("xong rồi")])
    o2 = orch(llm2)
    jid2 = o2.create_job("y")
    await o2.run(jid2)
    assert o2.get(jid2)["state"] == m.BLOCKED and "nhắc lại" in o2.get(jid2)["error"]


async def test_director_question_then_answer_with_attachment(orch):
    llm = Script(director=[say("Cần làm rõ.\n\nCÂU HỎI:\n1. Định dạng? (mặc định JPG)"), wf("@job/brief.md", "b"), say("ok"), say("DUYỆT"),
                           wf("@job/plan.json", PLAN1), say("ok")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("việc mơ hồ")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.WAITING_ANSWER and j["questions"].startswith("CÂU HỎI")
    o.answer(jid, "JPG", [("mau.png", b"PNG")])
    assert any(p.name == "mau.png" for p in (o.job_dir(jid) / "inputs").rglob("*"))
    assert "@job/inputs/" in (o.job_dir(jid) / "answers.md").read_text(encoding="utf-8")
    await o.run(jid)
    assert o.get(jid)["round"] == 1                         # đã qua brief và lập kế hoạch


async def test_invalid_plan_is_sent_back_to_director(orch):
    bad = json.dumps({"summary": "x", "tasks": [{"id": "T1", "role": "software", "title": "a", "goal": "g", "depends_on": ["T9"]}]})
    llm = Script(director=[wf("@job/brief.md", "b"), say("ok"), say("DUYỆT"), wf("@job/plan.json", bad), say("xong"),
                           wf("@job/plan.json", PLAN1), say("đã sửa")], engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["round"] == 1
    assert any("depends_on trỏ tới task không tồn tại" in c[1] for c in llm.calls if c[0] == "director")   # lỗi được trả nguyên văn cho Giám đốc


async def test_plan_never_valid_blocks(orch):
    bad = json.dumps({"summary": "x", "tasks": []})
    llm = Script(director=[wf("@job/brief.md", "b"), say("ok"), say("DUYỆT")] + [wf("@job/plan.json", bad), say("x")] * 3)
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["state"] == m.BLOCKED


async def test_multi_task_dependency_order_and_roles(orch):
    plan = json.dumps({"summary": "hai việc", "tasks": [
        {"id": "T2", "role": "media", "title": "vẽ logo", "goal": "logo", "outputs": ["deliverables/logo.svg"], "depends_on": ["T1"]},
        {"id": "T1", "role": "software", "title": "viết script", "goal": "script", "outputs": ["deliverables/a.py"]}]})
    llm = Script(director=director_front(plan) + [wf("@job/deliverables/HANDOFF.md", "h"), say("ok")],
                 engineer=eng_ok(), media=[wf("deliverables/logo.svg", "<svg/>"), say("xong")], **qa())
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    rows = o.db.query("SELECT task_id, role, status FROM tasks WHERE job_id=? ORDER BY id", (jid,))
    assert [(r["task_id"], r["role"]) for r in rows] == [("T1", "software"), ("T2", "media")]   # T1 trước dù khai báo sau
    assert all(r["status"] == "done" for r in rows)
    called = [c[0] for c in llm.calls]
    assert called.index("engineer") < called.index("media")


async def test_missing_declared_output_gets_one_retry_then_blocks(orch):
    llm = Script(director=director_front(), engineer=[say("xong rồi"), say("vẫn xong")])   # không bao giờ tạo file
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.BLOCKED and "thiếu file" in j["error"]
    assert len([c for c in llm.calls if c[0] == "engineer"]) == 2


async def test_qa_fail_twice_then_blocked_and_retry(orch):
    eng = eng_ok()
    llm = Script(director=director_front(), engineer=eng * 3, qa_author=qa()["qa_author"],
                 qa_runner=[say("KẾT QUẢ: FAIL sai")] * 3)
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.BLOCKED and j["fix_round"] == 2 and j["blocked_from"] == m.QA_RUN
    assert [r["task_id"] for r in o.db.query("SELECT task_id FROM tasks WHERE job_id=? ORDER BY id", (jid,))] == ["T1", "FIX1", "FIX2"]
    # Lỗi Kiểm thử đi NGUYÊN VĂN tới model con ở vòng sửa
    assert any("KIỂM THỬ TRẢ FAIL" in c[1] and "sai" in c[1] for c in llm.calls if c[0] == "engineer")
    o.retry(jid, "đừng dùng EXIF", [("ghi-chu.txt", b"x")])
    j = o.get(jid)
    assert j["state"] == m.EXECUTING and j["fix_round"] == 0 and "đừng dùng EXIF" in j["note"] and "@job/inputs/" in j["note"]


async def test_runner_without_verdict_is_asked_again_then_fails_the_case(orch):
    llm = Script(director=director_front(), engineer=eng_ok() * 3, qa_author=qa()["qa_author"],
                 qa_runner=[say("xong rồi")] * 6)                        # không bao giờ kết luận đúng mẫu
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert len([c for c in llm.calls if c[0] == "qa_runner"]) == 6          # 2 lượt mỗi vòng x 3 vòng (gốc + 2 sửa)
    assert any("chưa kết luận đúng mẫu" in c[1] for c in llm.calls if c[0] == "qa_runner")
    assert o.get(jid)["state"] == m.BLOCKED


async def test_each_testcase_gets_its_own_runner_call(orch):
    two = json.dumps({"cases": [
        {"id": "TC1", "title": "a", "criterion": "c", "steps": ["x"], "manual_check": "xem"},
        {"id": "TC2", "title": "b", "criterion": "c", "steps": ["y"], "manual_check": "xem"}]})
    llm = Script(director=director_front() + [wf("@job/deliverables/HANDOFF.md", "h"), say("ok")], engineer=eng_ok(),
                 qa_author=[wf("@job/qa/testcases.json", two), say("ok")], qa_runner=[say("KẾT QUẢ: PASS 1"), say("KẾT QUẢ: PASS 2")])
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    calls = [c[1] for c in llm.calls if c[0] == "qa_runner"]
    assert len(calls) == 2 and '"TC1"' in calls[0] and '"TC2"' in calls[1] and '"TC2"' not in calls[0]   # mỗi lượt chỉ MỘT case
    assert o.get(jid)["state"] == m.AWAITING_HANDOFF


async def test_broken_testcase_setup_goes_back_to_qa_author_not_to_engineer(orch, monkeypatch):
    bad = json.dumps({"cases": [{"id": "TC1", "title": "t", "criterion": "c", "setup": ["python -c 'import khong_co'"], "steps": ["echo hi"],
                                 "expect": {"exit_code": 0}}]})
    good = json.dumps({"cases": [{"id": "TC1", "title": "t", "criterion": "c", "setup": [], "steps": ["echo hi"], "expect": {"exit_code": 0}}]})
    monkeypatch.setattr(config, "SANDBOX_MODE", "docker")
    calls = []

    def fake(root, script, meta, timeout, isolated):
        calls.append(script)
        return (1, "", "ModuleNotFoundError") if "khong_co" in script else (0, "@@SETUP_OK@@ hi ", "")   # setup hỏng thì KHÔNG in dấu mốc

    monkeypatch.setattr(m, "run_in_sandbox", fake)
    llm = Script(director=director_front() + [wf("@job/deliverables/HANDOFF.md", "h"), say("ok")], engineer=eng_ok(),
                 qa_author=[wf("@job/qa/testcases.json", bad), say("ok"), wf("@job/qa/testcases.json", good), say("đã sửa")],
                 qa_runner=[say("KẾT QUẢ: FAIL setup lỗi"), say("KẾT QUẢ: PASS ok")])
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.AWAITING_HANDOFF and j["qa_repairs"] == 1 and j["fix_round"] == 0      # sản phẩm KHÔNG bị bắt sửa
    assert [c[0] for c in llm.calls].count("engineer") == 2      # đúng MỘT lần chạy của Kỹ sư (2 lượt gọi: công cụ + báo cáo)
    assert any("SỬA TESTCASE" in c[1] and "KHÔNG phải của sản phẩm" in c[1] for c in llm.calls if c[0] == "qa_author")


async def test_audit_overrides_a_lying_runner(orch, monkeypatch):
    cases = json.dumps({"cases": [{"id": "TC1", "title": "chạy", "criterion": "c", "steps": ["./run"], "expect": {"exit_code": 0, "stdout_contains": ["XONG"]}}]})
    monkeypatch.setattr(config, "SANDBOX_MODE", "docker")
    monkeypatch.setattr(m, "run_in_sandbox", lambda *a, **k: (1, "@@SETUP_OK@@ lỗi gì đó", ""))   # setup ổn, chạy lại độc lập thất bại thật
    llm = Script(director=director_front(), engineer=eng_ok() * 3,
                 qa_author=[wf("@job/qa/testcases.json", cases), say("ok")],
                 qa_runner=[say("KẾT QUẢ: PASS ok")] * 3)                              # runner nói PASS mãi
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["state"] == m.BLOCKED                                        # PASS của runner KHÔNG được tin
    rep = next(o.job_dir(jid).glob("qa-bao-cao-vong*.md")).read_text(encoding="utf-8")
    assert "báo PASS nhưng chạy lại độc lập thì FAIL" in rep


async def test_owner_feedback_reopens_with_new_round_and_files(orch):
    llm = Script(director=director_front() + [wf("@job/deliverables/HANDOFF.md", "h"), say("ok"),
                                              wf("@job/plan.json", PLAN1), say("kế hoạch bổ sung")],
                 engineer=eng_ok() * 2, qa_author=qa()["qa_author"] * 2, qa_runner=qa()["qa_runner"] * 2)
    o = orch(llm)
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_HANDOFF
    o.feedback(jid, "lỗi ở dòng 3", [("anh-loi.png", b"PNG")])
    j = o.get(jid)
    assert j["state"] == m.PLANNING and "lỗi ở dòng 3" in j["note"] and "@job/inputs/" in j["note"]
    (o.job_dir(jid) / "plan.json").write_text(PLAN1, encoding="utf-8")   # (kịch bản đã ghi plan; thời gian sửa file cần mới hơn)
    import os, time
    os.utime(o.job_dir(jid) / "plan.json", (time.time() - 100, time.time() - 100))
    await o.run(jid)
    assert o.get(jid)["round"] == 2                           # đợt mới, không làm lại từ đầu
    assert not (o.job_dir(jid) / "qa" / "testcases.json").exists() or o.get(jid)["state"] != m.EXECUTING


async def test_message_is_routed_by_state(orch):
    o = orch(Script())
    jid = o.create_job("x")
    o.message(jid, "ghi chú giữa chừng", [("a.txt", b"1")])          # đang chạy -> xếp hàng cho Giám đốc
    assert o.get(jid)["state"] == m.INTAKE
    inbox = o._inbox(jid)
    assert "ghi chú giữa chừng" in inbox and "@job/inputs/" in inbox
    assert o._inbox(jid) == ""                                         # đã đọc thì không đưa lại
    o.set_state(jid, m.BLOCKED, error="x", blocked_from=m.INTAKE)
    o.message(jid, "tiếp đi")                                          # đang dừng -> hướng dẫn tiếp tục
    assert o.get(jid)["state"] == m.INTAKE


async def test_git_commit_is_mandatory(orch, monkeypatch):
    llm = Script(director=[wf("@job/brief.md", "b"), say("ok")])
    o = orch(llm)

    def boom(*a, **k):
        raise gitops.GitError("hook từ chối")

    monkeypatch.setattr(gitops, "commit_all", boom)
    jid = o.create_job("x")
    await o.run(jid)
    j = o.get(jid)
    assert j["state"] == m.BLOCKED and "hook từ chối" in j["error"]    # không commit được thì KHÔNG đi tiếp


def _git(p, *a):
    return subprocess.run(["git", *a], cwd=p, capture_output=True, text=True, encoding="utf-8").stdout.strip()


async def test_workspace_job_edits_real_folder_on_own_branch(orch, tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    gitops.init_repo(ws)
    (ws / "app.py").write_text("print('cũ')", encoding="utf-8")
    _git(ws, "add", "-A"); _git(ws, "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-m", "init")
    main_branch = gitops.current_branch(ws)
    plan = json.dumps({"summary": "sửa", "tasks": [{"id": "T1", "role": "software", "title": "sửa app", "goal": "sửa", "outputs": ["app.py"]}]})
    llm = Script(director=director_front(plan) + [wf("@job/deliverables/HANDOFF.md", "h"), say("ok")],
                 engineer=[wf("app.py", "print('mới')"), say("xong")], **qa())
    o = orch(llm)
    jid = o.create_job("sửa project", workspace=str(ws))
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_HANDOFF
    assert gitops.current_branch(ws) == f"studio/{jid}"
    assert (ws / "app.py").read_text(encoding="utf-8") == "print('mới')"       # sửa thẳng file thật
    assert _git(ws, "show", f"{main_branch}:app.py") == "print('cũ')"          # nhánh gốc nguyên vẹn
    assert any(c["repo"] == "workspace" for c in o.db.query("SELECT repo FROM commits WHERE job_id=?", (jid,)))


async def test_workspace_refused_when_dirty_or_dangerous(orch, tmp_path):
    o = orch(Script())
    ws = tmp_path / "p"; ws.mkdir()
    gitops.init_repo(ws)
    (ws / "wip.txt").write_text("dở", encoding="utf-8")
    with pytest.raises(gitops.GitError):
        o.create_job("x", workspace=str(ws))
    with pytest.raises(gitops.GitError):
        o.create_job("x", workspace="C:/Windows")


async def test_resume_reruns_running_state(orch):
    o = orch(Script(director=[wf("@job/brief.md", "b"), say("ok"), say("DUYỆT"), wf("@job/plan.json", PLAN1), say("ok")], engineer=eng_ok(), **qa()))
    jid = o.create_job("x")                      # intake = "đang chạy", như thể backend chết giữa chừng
    o.resume_interrupted()
    await o._tasks[jid]
    assert o.get(jid)["round"] == 1
    assert "resume" in [e["kind"] for e in o.db.query("SELECT kind FROM events WHERE job_id=?", (jid,))]


async def test_upload_name_cannot_escape(orch):
    o = orch(Script())
    jid = o.create_job("x", [("..\\..\\evil.txt", b"hi")])
    assert (o.job_dir(jid) / "inputs" / "evil.txt").exists()
    assert not (o.job_dir(jid).parent / "evil.txt").exists()
    saved = o.save_files(jid, [("../../x.txt", b"1")], "t")
    assert saved == ["inputs/t/x.txt"]


async def test_broken_testcases_file_is_redesigned_not_crashing(orch):
    llm = Script(director=[wf("@job/deliverables/HANDOFF.md", "h"), say("ok")],  # chỉ bước bàn giao: test bắt đầu từ EXECUTING
                  engineer=eng_ok(),
                 qa_author=[wf("@job/qa/testcases.json", CASES), say("viết lại")], qa_runner=[say("KẾT QUẢ: PASS ok")])
    o = orch(llm)
    jid = o.create_job("x")
    (o.job_dir(jid) / "qa" / "testcases.json").write_text('{"cases": [ {"id": "TC1" ', encoding="utf-8")   # file dở dang từ lần chạy trước
    o.set_state(jid, m.BRIEF_REVIEW); o.set_state(jid, m.PLANNING); o.set_state(jid, m.EXECUTING, round=1)
    (o.job_dir(jid) / "plan.json").write_text(PLAN1, encoding="utf-8")
    o.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, status) VALUES (?,?,?,?,?,?)", (jid, 1, "T1", "software", "viết", "pending"))
    await o.run(jid)
    assert o.get(jid)["state"] == m.AWAITING_HANDOFF


async def test_owner_can_cancel_a_running_job_and_resume_it(orch):
    import asyncio

    class Slow:
        async def chat(self, role, messages, tools=None, max_tokens=4096):
            await asyncio.sleep(30)      # model "treo": job đang chạy lâu

    o = orch(Slow())
    jid = o.create_job("x")
    o.schedule(jid)
    await asyncio.sleep(0.2)
    o.cancel(jid)
    await asyncio.sleep(0.2)
    j = o.get(jid)
    assert j["state"] == m.BLOCKED and j["blocked_from"] == m.INTAKE and "dừng job" in j["error"]
    assert o._tasks[jid].cancelled() or o._tasks[jid].done()          # agent đã bị dừng thật, không chạy ngầm
    with pytest.raises(InvalidAction):
        o.cancel(jid)                                                   # đã dừng rồi
    o.retry(jid, "tiếp đi")                                             # và tiếp tục được
    assert o.get(jid)["state"] == m.INTAKE


async def test_autopilot_never_asks_and_accepts_handoff(orch):
    settings.update({"autopilot": True})
    llm = Script(director=[say("CÂU HỎI:\n1. Định dạng?"), wf("@job/brief.md", BRIEF_TEXT), say("ĐÃ VIẾT BRIEF"), say("DUYỆT"),
                           wf("@job/plan.json", PLAN1), say("ok"), wf("@job/deliverables/HANDOFF.md", "# giao"), say("ok"), say("- bài học")],
                 engineer=eng_ok(), **qa())
    o = orch(llm)
    jid = o.create_job("việc mơ hồ")
    await o.run(jid)
    assert "KHÔNG hỏi lại chủ studio" in [c for c in llm.calls if c[0] == "director"][0][1]
    assert o.get(jid)["state"] == m.DONE                      # không dừng ở câu hỏi, không chờ duyệt bàn giao
    o.feedback(jid, "sửa thêm chút")                         # chủ vẫn phản hồi được sau khi tự chấp nhận
    assert o.get(jid)["state"] == m.PLANNING


async def test_autopilot_retries_blocked_job_then_gives_up(orch):
    settings.update({"autopilot": True, "autopilot_retries": 2})
    # Thử lại ra ĐÚNG lỗi cũ (mỗi lượt = 2 lần gọi vì có nhắc lại) -> dừng sau 1 lần, không đốt hết lượt.
    o = orch(Script(director=[say("xong")] * 4))
    jid = o.create_job("x")
    await o.run(jid)
    assert o.get(jid)["state"] == m.BLOCKED
    ev = o.db.query("SELECT kind, message FROM events WHERE job_id=?", (jid,))
    assert [e["kind"] for e in ev].count("auto_retry") == 1
    assert any(e["kind"] == "auto_retry_stop" and "đúng lỗi cũ" in e["message"] for e in ev)

    # Lỗi KHÁC nhau mỗi lần thì dùng hết số lượt rồi mới dừng.
    o3 = orch(Script(director=[say("xong")] * 6))
    jid3 = o3.create_job("z")
    errs = iter(["lỗi A", "lỗi B", "lỗi C"])
    o3._do_intake = lambda job_id: _fake_block(o3, job_id, next(errs))
    await o3.run(jid3)
    kinds = [e["kind"] for e in o3.db.query("SELECT kind FROM events WHERE job_id=?", (jid3,))]
    assert kinds.count("auto_retry") == 2 and "auto_retry_stop" in kinds

    # Tự thử lại thành công: job đi tiếp tới cuối, không cần chủ.
    llm = Script(director=[say("xong"), say("xong"), wf("@job/brief.md", BRIEF_TEXT), say("ĐÃ VIẾT BRIEF"), say("DUYỆT"),
                           wf("@job/plan.json", PLAN1), say("ok"), wf("@job/deliverables/HANDOFF.md", "# giao"), say("ok"), say("- b")],
                 engineer=eng_ok(), **qa())
    o2 = orch(llm)
    jid2 = o2.create_job("y")
    await o2.run(jid2)
    assert o2.get(jid2)["state"] == m.DONE


async def _fake_block(o, job_id, reason):
    o._block(job_id, reason)


async def test_autopilot_does_not_retry_owner_cancel(orch):
    settings.update({"autopilot": True})
    o = orch(Script())
    jid = o.create_job("x")
    o.set_state(jid, m.BLOCKED, error="Chủ studio đã dừng job", blocked_from=m.INTAKE)
    assert await o._auto_retry(jid) is False
