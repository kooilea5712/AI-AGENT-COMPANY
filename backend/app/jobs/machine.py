"""Máy trạng thái job: 8 bước của thiết kế, viết thẳng bằng bảng chuyển trạng thái.

Luồng bản này (chủ studio CHỈ làm việc với Giám đốc):
  1 INTAKE        Giám đốc đọc yêu cầu, hỏi lại nếu bắt buộc, viết brief
  2 BRIEF_REVIEW  Giám đốc TỰ CHỐT DUYỆT brief (chủ chỉ phải duyệt nếu bật trong Cài đặt)
  3 PLANNING      Giám đốc chia việc: plan.json = nhiều task, mỗi task một model con
  4 EXECUTING     các model con làm lần lượt theo phụ thuộc; sau MỖI task hệ thống commit Git
  6 QA_DESIGN     Kiểm định (model mạnh) viết bộ testcase;  QA_RUN  Kiểm thử viên (model rẻ) chạy HẾT, code chạy lại độc lập để chống ghi sai
  7 HANDOFF       Giám đốc viết HANDOFF.md -> AWAITING_HANDOFF: chủ xem kết quả cuối, chấp nhận hoặc phản hồi (kèm file)
  8 LESSONS       rút kinh nghiệm.
Phản hồi của chủ (từ AWAITING_HANDOFF hoặc DONE) đưa job quay về PLANNING: Giám đốc lập kế hoạch bổ sung, không làm lại từ đầu.
Mỗi trạng thái "đang chạy" có đúng một hàm _do_<trạng_thái>; trạng thái "chờ" chỉ đi tiếp nhờ hành động của chủ (API).
"""
import asyncio
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from .. import config, context, gitops, planning, prompts, settings, staff
from ..agents.loop import run_agent
from ..db import DB
from ..tools.sandbox import JobTools, ToolError, run_in_sandbox

# --- Trạng thái -------------------------------------------------------------
INTAKE, WAITING_ANSWER, BRIEF_REVIEW, AWAITING_BRIEF = "intake", "waiting_answer", "brief_review", "awaiting_brief"
PLANNING, EXECUTING, QA_DESIGN, QA_RUN = "planning", "executing", "qa_design", "qa_run"
HANDOFF, AWAITING_HANDOFF, LESSONS, DONE, BLOCKED = "handoff", "awaiting_handoff", "lessons", "done", "blocked"

RUNNING = {INTAKE, BRIEF_REVIEW, PLANNING, EXECUTING, QA_DESIGN, QA_RUN, HANDOFF, LESSONS}   # code đang làm việc
WAITING = {WAITING_ANSWER, AWAITING_BRIEF, AWAITING_HANDOFF}                                 # chờ chủ studio
# Bước (1..8) trong thiết kế, để giao diện vẽ thanh tiến trình. Bước 5 (tự kiểm) nằm trong EXECUTING.
STEP_OF = {INTAKE: 1, WAITING_ANSWER: 1, BRIEF_REVIEW: 2, AWAITING_BRIEF: 2, PLANNING: 3, EXECUTING: 4, QA_DESIGN: 6, QA_RUN: 6,
           HANDOFF: 7, AWAITING_HANDOFF: 7, LESSONS: 8, DONE: 8, BLOCKED: 0}

TRANSITIONS = {
    INTAKE: {WAITING_ANSWER, BRIEF_REVIEW, BLOCKED},
    WAITING_ANSWER: {INTAKE},
    BRIEF_REVIEW: {AWAITING_BRIEF, PLANNING, BLOCKED},
    AWAITING_BRIEF: {INTAKE, PLANNING},                    # chỉ khi bật "chủ duyệt brief"
    PLANNING: {EXECUTING, BLOCKED},
    EXECUTING: {QA_DESIGN, BLOCKED},
    QA_DESIGN: {QA_RUN, BLOCKED},
    QA_RUN: {EXECUTING, QA_DESIGN, HANDOFF, BLOCKED},      # FAIL còn lượt sửa -> EXECUTING; testcase lỗi -> QA_DESIGN; hết lượt -> BLOCKED
    HANDOFF: {AWAITING_HANDOFF, BLOCKED},
    AWAITING_HANDOFF: {LESSONS, PLANNING},                 # chấp nhận / phản hồi (Giám đốc lập kế hoạch bổ sung)
    LESSONS: {DONE},
    DONE: {PLANNING},                                      # chủ nhắn thêm sau khi xong
    BLOCKED: {INTAKE, BRIEF_REVIEW, PLANNING, EXECUTING, QA_DESIGN, QA_RUN, HANDOFF},   # "Tiếp tục" quay về bước đã dừng
}

STATE_ACTOR = {INTAKE: staff.DIRECTOR, WAITING_ANSWER: staff.OWNER, BRIEF_REVIEW: staff.DIRECTOR, AWAITING_BRIEF: staff.OWNER,
               PLANNING: staff.DIRECTOR, QA_DESIGN: staff.QA_AUTHOR, QA_RUN: staff.QA_RUNNER, HANDOFF: staff.DIRECTOR,
               AWAITING_HANDOFF: staff.OWNER, LESSONS: staff.DIRECTOR, BLOCKED: staff.OWNER, DONE: None}   # EXECUTING: xem actor_of


class InvalidAction(Exception):
    pass


def _short(t: str, n: int = 600) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


class Orchestrator:
    def __init__(self, db: DB, llm, jobs_dir: Path | None = None, lessons_path: Path | None = None):
        self.db, self.llm = db, llm
        self.jobs_dir = Path(jobs_dir or config.JOBS_DIR)
        self.lessons_path = Path(lessons_path or config.ROOT / "lessons.md")
        self._tasks: dict[str, asyncio.Task] = {}

    # --- tiện ích -----------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def get(self, job_id: str) -> dict:
        j = self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not j:
            raise KeyError(job_id)
        return j

    def work_root(self, job_id: str) -> Path:
        ws = self.get(job_id)["workspace"]
        return Path(ws) if ws else self.job_dir(job_id)

    def event(self, job_id: str, kind: str, msg: str, actor: str | None = None):
        """Một nguồn sự thật cho nhật ký: DB (cho SSE/giao diện) và log.md (cho người mở thư mục job).
        actor = ai gây ra sự kiện, để giao diện vẽ luồng bàn giao và lọc nhật ký theo nhân viên."""
        self.db.execute("INSERT INTO events(job_id, ts, kind, message, actor) VALUES (?,?,?,?,?)",
                        (job_id, time.time(), kind, msg, actor or staff.SYSTEM))
        with open(self.job_dir(job_id) / "log.md", "a", encoding="utf-8") as f:
            f.write(f"- `{time.strftime('%H:%M:%S')}` **{kind}** {msg}\n")

    def set_state(self, job_id: str, new: str, **fields):
        cur = self.get(job_id)["state"]
        if new not in TRANSITIONS[cur]:
            raise InvalidAction(f"Không thể chuyển {cur} -> {new}")
        cols = {"state": new, "updated_at": time.time(), **fields}
        self.db.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), job_id))
        self.event(job_id, "state", f"{cur} -> {new}")

    def _block(self, job_id: str, reason: str):
        self.event(job_id, "error", reason)
        self.say(job_id, "director", f"Job dừng, cần anh/chị quyết định: {reason}")
        self.set_state(job_id, BLOCKED, error=reason, blocked_from=self.get(job_id)["state"])

    # --- hội thoại chủ <-> Giám đốc ------------------------------------------------
    def say(self, job_id: str, sender: str, text: str, files: list[str] | None = None, delivered: bool = True):
        self.db.execute("INSERT INTO messages(job_id, ts, sender, text, files, delivered) VALUES (?,?,?,?,?,?)",
                        (job_id, time.time(), sender, text, json.dumps(files or []), 1 if delivered else 0))

    def conversation(self, job_id: str) -> list[dict]:
        rows = self.db.query("SELECT id, ts, sender, text, files FROM messages WHERE job_id=? ORDER BY id", (job_id,))
        return [{**r, "files": json.loads(r["files"])} for r in rows]

    def _inbox(self, job_id: str) -> str:
        """Tin chủ gửi LÚC job đang chạy: đưa cho Giám đốc/model con ở bước kế tiếp rồi đánh dấu đã đọc."""
        rows = self.db.query("SELECT id, text, files FROM messages WHERE job_id=? AND sender='owner' AND delivered=0 ORDER BY id", (job_id,))
        if not rows:
            return ""
        self.db.execute("UPDATE messages SET delivered=1 WHERE job_id=? AND sender='owner' AND delivered=0", (job_id,))
        return "\n".join(f"- {r['text']}" + (f" (đính kèm: {', '.join('@job/' + f for f in json.loads(r['files']))})" if json.loads(r["files"]) else "") for r in rows)

    def save_files(self, job_id: str, files: list[tuple[str, bytes]], tag: str) -> list[str]:
        """Lưu file đính kèm vào inputs/<tag>/. Path(name).name bỏ mọi thành phần thư mục trong tên upload (chống ghi ra ngoài)."""
        out = []
        for name, data in files or []:
            safe = Path(name).name or "file"
            d = self.job_dir(job_id) / "inputs" / tag
            d.mkdir(parents=True, exist_ok=True)
            (d / safe).write_bytes(data)
            out.append(f"inputs/{tag}/{safe}")
        return out

    def _note(self, text: str, saved: list[str]) -> str:
        n = text.strip()
        if saved:
            n += "\nFile chủ đính kèm: " + ", ".join(f"@job/{f}" for f in saved)
        return n

    # --- tạo job ------------------------------------------------------------
    def create_job(self, description: str, files: list[tuple[str, bytes]] | None = None, workspace: str | None = None,
                   tier: str | None = None, budget: float | None = None) -> str:
        tier = tier or settings.load()["default_tier"]
        if tier not in settings.TIERS:
            raise ValueError("tier phải là full hoặc economy")
        if budget is not None and budget < 0:
            raise ValueError("hạn mức phải >= 0")
        job_id = f"job-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:3]}"
        d = self.job_dir(job_id)
        ws_note = None
        base = None
        if workspace and workspace.strip():
            ws = Path(workspace.strip()).expanduser()
            ws_note = gitops.prepare_workspace(ws, job_id)       # GitError nếu thư mục không hợp lệ: báo ngay lúc tạo job
            workspace, base = str(ws.resolve()), None
        else:
            workspace = None
        for sub in ("inputs", "work", "deliverables", "reports", "qa"):
            (d / sub).mkdir(parents=True)
        gitops.init_repo(d)
        for name, data in files or []:
            (d / "inputs" / Path(name).name).write_bytes(data)
        title = description.strip().splitlines()[0][:80] or job_id
        now = time.time()
        self.db.execute("INSERT INTO jobs(id,title,description,state,created_at,updated_at,workspace,base_branch,tier,budget) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (job_id, title, description, INTAKE, now, now, workspace, base, tier, budget))
        self.say(job_id, "owner", description, [f"inputs/{Path(n).name}" for n, _ in files or []])
        self.event(job_id, "state", f"tạo job, trạng thái {INTAKE}", staff.OWNER)
        if ws_note:
            self.event(job_id, "git", f"thư mục làm việc {workspace}: {ws_note}")
        return job_id

    # --- hành động của chủ studio (API gọi) ----------------------------------
    def _require(self, job_id: str, *states: str) -> dict:
        j = self.get(job_id)
        if j["state"] not in states:
            raise InvalidAction(f"Job đang ở '{j['state']}', hành động này cần {' hoặc '.join(states)}")
        return j

    def _owner_says(self, job_id: str, text: str, saved: list[str]):
        self.say(job_id, "owner", text, saved)
        self.event(job_id, "message", _short(text, 300) + (f" (+{len(saved)} file)" if saved else ""), staff.OWNER)

    def answer(self, job_id: str, text: str, files: list[tuple[str, bytes]] | None = None):
        j = self._require(job_id, WAITING_ANSWER)
        saved = self.save_files(job_id, files or [], f"tl{int(time.time())}")
        with open(self.job_dir(job_id) / "answers.md", "a", encoding="utf-8") as f:
            f.write(f"## Câu hỏi của Giám đốc\n{j['questions']}\n\n## Trả lời của chủ studio\n{self._note(text, saved)}\n\n")
        self._owner_says(job_id, text, saved)
        self.set_state(job_id, INTAKE, questions=None)

    def approve_brief(self, job_id: str):
        self._require(job_id, AWAITING_BRIEF)
        self.set_state(job_id, PLANNING, note=None)

    def reject_brief(self, job_id: str, note: str, files=None):
        self._require(job_id, AWAITING_BRIEF)
        saved = self.save_files(job_id, files or [], f"pn{int(time.time())}")
        self._owner_says(job_id, note, saved)
        self.set_state(job_id, INTAKE, note=self._note(note, saved))

    def approve_handoff(self, job_id: str):
        """Chủ chấp nhận kết quả cuối."""
        self._require(job_id, AWAITING_HANDOFF)
        self.say(job_id, "owner", "Đã chấp nhận kết quả.")
        self.set_state(job_id, LESSONS)

    def feedback(self, job_id: str, text: str, files=None):
        """Chủ chỉ ra lỗi / yêu cầu thêm sau khi xem kết quả: Giám đốc lập kế hoạch bổ sung (đợt mới), không làm lại từ đầu."""
        self._require(job_id, AWAITING_HANDOFF, DONE)
        saved = self.save_files(job_id, files or [], f"ph{int(time.time())}")
        self._owner_says(job_id, text, saved)
        self.set_state(job_id, PLANNING, note="PHẢN HỒI CỦA CHỦ STUDIO SAU KHI XEM KẾT QUẢ: " + self._note(text, saved), fix_round=0, error=None)

    reject_handoff = feedback   # tên cũ của API

    def retry(self, job_id: str, note: str = "", files=None):
        """Tiếp tục job bị chặn từ đúng bước đã dừng, kèm hướng dẫn của chủ studio (nếu có)."""
        j = self._require(job_id, BLOCKED)
        src = j["blocked_from"] or INTAKE
        # QA_RUN bị chặn nghĩa là đã hết vòng sửa: cho model con làm lại với phản hồi mới và cấp lại đủ lượt.
        target = EXECUTING if src == QA_RUN else src
        fields = {"error": None, "fix_round": 0 if src in (QA_RUN, EXECUTING) else j["fix_round"]}
        saved = self.save_files(job_id, files or [], f"tt{int(time.time())}")
        if src == QA_DESIGN:      # bị chặn khi thiết kế testcase: thiết kế lại từ đầu thay vì dùng bộ cũ hỏng
            (self.job_dir(job_id) / "qa" / "testcases.json").unlink(missing_ok=True)
        if note or saved:
            self._owner_says(job_id, note or "(đính kèm file)", saved)
            fields["note"] = "CHỦ STUDIO HƯỚNG DẪN KHI TIẾP TỤC: " + self._note(note, saved)
        self.set_state(job_id, target, **fields)

    def cancel(self, job_id: str):
        """Chủ dừng job đang chạy. Job chuyển sang 'blocked' (giữ mọi thứ đã làm); bấm "Tiếp tục" để chạy tiếp từ bước đó."""
        j = self._require(job_id, *(RUNNING - {LESSONS}))
        t = self._tasks.get(job_id)
        if t and not t.done():
            t.cancel()        # dừng agent đang chạy; lệnh sandbox đang dở tự hết giờ theo timeout
        self.event(job_id, "message", "Chủ studio đã dừng job", staff.OWNER)
        self.say(job_id, "owner", "Dừng job.")
        self.set_state(job_id, BLOCKED, error="Chủ studio đã dừng job", blocked_from=j["state"])

    def message(self, job_id: str, text: str, files=None):
        """Chủ nhắn Giám đốc BẤT CỨ LÚC NÀO (chủ chỉ nói chuyện với Giám đốc). Tuỳ trạng thái mà tin này là câu trả lời,
        phản hồi, hướng dẫn tiếp tục, hoặc được xếp hàng để Giám đốc đọc ở bước kế tiếp."""
        st = self.get(job_id)["state"]
        if st == WAITING_ANSWER:
            return self.answer(job_id, text, files)
        if st == AWAITING_BRIEF:
            return self.reject_brief(job_id, text, files)
        if st in (AWAITING_HANDOFF, DONE):
            return self.feedback(job_id, text, files)
        if st == BLOCKED:
            return self.retry(job_id, text, files)
        saved = self.save_files(job_id, files or [], f"ms{int(time.time())}")
        self.say(job_id, "owner", text, saved, delivered=False)     # đang chạy: xếp hàng
        self.event(job_id, "message", f"(xếp hàng cho Giám đốc) {_short(text, 300)}", staff.OWNER)

    # --- chạy -----------------------------------------------------------------
    def schedule(self, job_id: str):
        """Chạy job nền tới khi gặp trạng thái chờ/kết thúc. Không chạy hai lần cho cùng một job."""
        t = self._tasks.get(job_id)
        if t and not t.done():
            return
        self._tasks[job_id] = asyncio.create_task(self.run(job_id))

    def resume_interrupted(self):
        """Gọi lúc backend khởi động: job đang ở trạng thái 'đang chạy' mà tiến trình đã chết thì chạy lại đúng bước đó
        (mỗi bước được viết để chạy lại được: ghi đè file, đọc lại từ đĩa, task đã xong thì bỏ qua)."""
        for j in self.db.query("SELECT id, state FROM jobs"):
            if j["state"] in RUNNING:
                self.event(j["id"], "resume", f"backend khởi động lại giữa chừng, chạy lại bước '{j['state']}'")
                self.schedule(j["id"])

    # --- chi phí và hạn mức ------------------------------------------------------------
    def job_cost(self, job_id: str) -> dict:
        r = self.db.one("SELECT COALESCE(SUM(tokens_in),0) tin, COALESCE(SUM(tokens_out),0) tout, COALESCE(SUM(cost),0) cost, "
                        "COALESCE(SUM(1-priced),0) unpriced, COUNT(*) calls FROM usage WHERE job_id=?", (job_id,))
        j = self.get(job_id)
        budget = j["budget"] if j["budget"] is not None else settings.load()["job_budget_usd"]
        return {"tokens_in": r["tin"], "tokens_out": r["tout"], "cost": round(r["cost"], 6), "calls": r["calls"],
                "unpriced_calls": r["unpriced"], "budget": budget or 0, "tier": j["tier"],
                "by_model": self.db.query("SELECT model, connection, SUM(tokens_in) tokens_in, SUM(tokens_out) tokens_out, SUM(cost) cost, "
                                          "MIN(priced) priced, COUNT(*) calls FROM usage WHERE job_id=? GROUP BY model, connection ORDER BY cost DESC", (job_id,))}

    def on_usage(self, role: str, connection: str, model: str, usage: dict):
        """Móc của LLMClient: ghi token + chi phí ước tính cho job hiện tại (lấy từ context)."""
        job_id = context.job_id_var.get()
        if not job_id:
            return
        s = settings.load()
        c = s["connections"].get(connection, {})
        tin, tout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        local = settings._local(c.get("base_url", ""))        # Ollama và OmniRoute chạy trên máy: không tính tiền ở đây
        price = None if local else s["prices"].get(model)
        cost = (tin * price["in"] + tout * price["out"]) / 1_000_000 if price else 0.0
        self.db.execute("INSERT INTO usage(job_id, ts, role, connection, model, tokens_in, tokens_out, cost, priced) VALUES (?,?,?,?,?,?,?,?,?)",
                        (job_id, time.time(), role, connection, model, tin, tout, cost, 1 if (local or price) else 0))
        info = self.job_cost(job_id)
        if info["budget"] and info["cost"] >= 0.8 * info["budget"] and not self.db.one(
                "SELECT 1 FROM events WHERE job_id=? AND kind='cost'", (job_id,)):
            self.event(job_id, "cost", f"Đã dùng 80% hạn mức chi phí: ${info['cost']:.2f} / ${info['budget']:.2f}", staff.SYSTEM)

    def check_budget(self, job_id: str | None):
        """Móc của LLMClient: chạm hạn mức thì dừng TRƯỚC lượt gọi tiếp theo."""
        if not job_id:
            return
        info = self.job_cost(job_id)
        if info["budget"] and info["cost"] >= info["budget"]:
            from ..llm.client import BudgetExceeded
            raise BudgetExceeded(f"Đã chạm hạn mức chi phí của job: ${info['cost']:.2f} / ${info['budget']:.2f}. "
                                 "Nâng hạn mức (nút 💰 trên đầu job) rồi bấm Tiếp tục.")

    def set_budget(self, job_id: str, usd: float | None):
        if usd is not None and usd < 0:
            raise InvalidAction("Hạn mức phải >= 0 (0 = không giới hạn)")
        self.get(job_id)
        self.db.execute("UPDATE jobs SET budget=?, updated_at=? WHERE id=?", (usd, time.time(), job_id))
        self.event(job_id, "cost", "Hạn mức chi phí đặt thành " + ("mặc định" if usd is None else f"${usd:.2f}" if usd else "không giới hạn"), staff.OWNER)

    async def run(self, job_id: str):
        context.job_id_var.set(job_id)       # mọi lượt gọi model trong run() được tính cho job này, đúng mức đầu tư của job
        context.tier_var.set(self.get(job_id)["tier"])
        try:
            while (state := self.get(job_id)["state"]) in RUNNING:
                await getattr(self, f"_do_{state}")(job_id)
        except Exception as e:  # noqa: BLE001 - bất kỳ lỗi bất ngờ nào cũng phải dừng job và hiện lên giao diện
            if self.get(job_id)["state"] in RUNNING:
                self._block(job_id, f"lỗi bất ngờ: {type(e).__name__}: {e}")

    # --- agent --------------------------------------------------------------------
    def _vision_fn(self):
        """Cầu nối cho tool describe_image: tool chạy ở thread riêng, còn LLMClient là async trên event loop chính."""
        loop = asyncio.get_running_loop()

        def fn(b64: str, mime: str, question: str) -> str:
            msgs = [{"role": "user", "content": [{"type": "text", "text": question},
                                                  {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]
            fut = asyncio.run_coroutine_threadsafe(self.llm.chat("vision", msgs, max_tokens=2000), loop)
            return fut.result(timeout=600)["message"].get("content") or "(model vision trả nội dung trống)"
        return fn

    def tools_for(self, job_id: str, llm_role: str) -> JobTools:
        """Công cụ của một vai: Giám đốc chỉ ghi được trong thư mục job; Kiểm định chỉ ghi trong qa/ và chạy lệnh trên bản sao."""
        scope = {"director": "meta", "qa_author": "qa", "qa_runner": "qa"}.get(llm_role, "all")
        return JobTools(self.work_root(job_id), self._vision_fn(), meta_root=self.job_dir(job_id),
                        isolated=llm_role in ("qa_author", "qa_runner"), write_scope=scope)

    async def _agent(self, job_id: str, who: str, llm_role: str, system: str, user: str, max_tokens: int = 4096):
        return await run_agent(self.llm, llm_role, system, user, self.tools_for(job_id, llm_role),
                               lambda k, m: self.event(job_id, k, m, who), config.MAX_STEPS_PER_TASK, who, max_tokens=max_tokens)

    def _lessons(self) -> str:
        return self.lessons_path.read_text(encoding="utf-8") if self.lessons_path.exists() else "(chưa có)"

    def _director_sys(self) -> str:
        team = ("- Kỹ sư phần mềm (VAI: software): viết, chạy, test code, script\n"
                "- Chuyên viên media (VAI: media): logo SVG, vector, xử lý ảnh, PDF bằng ArtCraft/Inkscape/ImageMagick\n"
                "- Kiểm định + Kiểm thử viên: hệ thống tự điều phối sau khi các task xong (bạn không giao việc cho họ)\n"
                "- (Video, âm thanh, game: CHƯA có ở bản này; job cần những thứ đó thì nói rõ trong brief)")
        return prompts.director_system(self._lessons(), team)

    def _ctx(self, job_id: str) -> str:
        """Bối cảnh chung đưa cho Giám đốc ở mỗi bước: yêu cầu, thư mục làm việc, file đính kèm, hội thoại gần nhất, tin xếp hàng."""
        j, d = self.get(job_id), self.job_dir(job_id)
        parts = [f"Mã job: {job_id}", f"YÊU CẦU GỐC CỦA CHỦ STUDIO:\n{j['description']}"]
        if j["workspace"]:
            parts.append(f"Job gắn với project trên máy: {j['workspace']} (nhánh Git riêng studio/{job_id}). Bạn có thể xem file trong đó "
                         "bằng list_dir/read_file (đường dẫn tương đối); tài liệu của job vẫn ở @job/.")
        files = sorted(str(p.relative_to(d)).replace("\\", "/") for p in (d / "inputs").rglob("*") if p.is_file())
        if files:
            parts.append("File chủ đã đính kèm: " + ", ".join("@job/" + f for f in files))
        if (d / "answers.md").exists():
            parts.append("ĐÃ HỎI VÀ ĐƯỢC TRẢ LỜI:\n" + (d / "answers.md").read_text(encoding="utf-8"))
        inbox = self._inbox(job_id)
        if inbox:
            parts.append("CHỦ VỪA NHẮN THÊM (đọc kỹ, ưu tiên):\n" + inbox)
        return "\n\n".join(parts)

    # --- commit bắt buộc sau mỗi lần chạy ------------------------------------------
    def _commit(self, job_id: str, what: str):
        """Quy tắc cứng: mọi lần agent chạy xong đều phải commit. Lỗi Git ném ra -> run() dừng job (không bỏ qua)."""
        j = self.get(job_id)
        targets = [("job", self.job_dir(job_id))] + ([("workspace", Path(j["workspace"]))] if j["workspace"] else [])
        for repo, path in targets:
            msg = f"[studio] {job_id} {what}"
            r = gitops.commit_all(path, msg)
            self.db.execute("INSERT INTO commits(job_id, ts, repo, hash, message, files) VALUES (?,?,?,?,?,?)",
                            (job_id, time.time(), repo, r["hash"], msg, r["files"]))
            self.event(job_id, "git", f"commit {repo} {r['hash']}: {what} ({r['files']} file)")

    # --- Bước 1: tiếp nhận ----------------------------------------------------------
    async def _do_intake(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        brief = d / "brief.md"
        before = brief.stat().st_mtime if brief.exists() else None
        parts = [self._ctx(job_id)]
        if j["note"] and brief.exists():
            parts.append(f"Chủ studio TRẢ LẠI brief hiện có (@job/brief.md) với phản hồi: {j['note']}\nHãy sửa brief.md.")
        if j["asked"] >= 1:
            parts.append("Bạn đã hỏi một lượt rồi: KHÔNG hỏi thêm, tự chọn phương án mặc định và ghi giả định vào brief.")
        parts.append("Việc của bạn bây giờ: bước 1 (tiếp nhận). Hỏi lại nếu bắt buộc, hoặc viết @job/brief.md.")
        r = await self._agent(job_id, staff.DIRECTOR, "director", self._director_sys(), "\n\n".join(parts))
        # Model hay chèn một câu dẫn trước "CÂU HỎI:" nên tìm ở đầu dòng bất kỳ, không chỉ đầu văn bản.
        q = re.search(r"^[\s*#]*CÂU HỎI.*", r.text, re.M | re.S)
        if q and j["asked"] < 1:
            self.say(job_id, "director", q.group(0).strip())
            self.set_state(job_id, WAITING_ANSWER, questions=q.group(0).strip(), asked=j["asked"] + 1)
        elif brief.exists() and (before is None or brief.stat().st_mtime > before):
            self._commit(job_id, "brief")
            self.set_state(job_id, BRIEF_REVIEW, note=None)
        else:
            self._block(job_id, r.reason or "Giám đốc không viết brief.md cũng không hỏi gì")

    # --- Bước 2: Giám đốc tự chốt duyệt brief ----------------------------------------
    async def _do_brief_review(self, job_id: str):
        d = self.job_dir(job_id)
        brief = d / "brief.md"
        verdict, reason = "DUYỆT", ""
        for attempt in (1, 2):                      # tối đa một lần sửa rồi chốt, để không lặp vô hạn
            before = brief.stat().st_mtime
            r = await self._agent(job_id, staff.DIRECTOR, "director", self._director_sys(),
                                  self._ctx(job_id) + "\n\n" + prompts.task_prompt("giam-doc-duyet-brief"))
            if not r.ok:
                return self._block(job_id, r.reason or "Giám đốc không duyệt được brief")
            m = re.match(r"\W*(DUYỆT|SỬA)", r.text.strip(), re.I)
            verdict = m.group(1).upper() if m else "DUYỆT"
            reason = _short(r.text, 400)
            if verdict == "DUYỆT" or brief.stat().st_mtime <= before:
                break
            self._commit(job_id, f"brief (đã sửa lần {attempt})")
        self.say(job_id, "director", f"Tôi đã duyệt brief. {reason}")
        if settings.load()["owner_approves_brief"]:
            self.set_state(job_id, AWAITING_BRIEF)
        else:
            self.set_state(job_id, PLANNING)

    # --- Bước 3: lập kế hoạch, chia việc ------------------------------------------
    async def _do_planning(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        plan_f = d / "plan.json"
        rnd = j["round"] + 1
        if plan_f.exists():                          # giữ bản kế hoạch cũ để xem lại lịch sử các đợt
            (d / "plans").mkdir(exist_ok=True)
            shutil.copy(plan_f, d / "plans" / f"plan-dot{j['round']}.json")
        before = plan_f.stat().st_mtime if plan_f.exists() else None
        extra = [j["note"]] if j["note"] else []
        plan, errors = None, []
        for attempt in range(1, 4):
            user = self._ctx(job_id) + "\n\n" + "\n".join(extra) + "\n\n" + prompts.task_prompt("giam-doc-ke-hoach")
            if errors:
                user += "\n\nLẦN TRƯỚC plan.json KHÔNG HỢP LỆ, hãy sửa và ghi lại:\n- " + "\n- ".join(errors)
            r = await self._agent(job_id, staff.DIRECTOR, "director", self._director_sys(), user, max_tokens=6000)
            if not r.ok:
                return self._block(job_id, r.reason or "Giám đốc không lập được kế hoạch")
            if not plan_f.exists() or (before is not None and plan_f.stat().st_mtime <= before):
                errors = ["Bạn chưa ghi @job/plan.json bằng write_file"]
                continue
            try:
                plan = planning.load_json(plan_f.read_text(encoding="utf-8"))
            except ValueError as e:
                errors = [f"plan.json không phải JSON hợp lệ: {e}"]
                continue
            errors = planning.validate_plan(plan)
            if not errors:
                break
            self.event(job_id, "warn", "plan.json chưa hợp lệ, yêu cầu Giám đốc sửa: " + "; ".join(errors), staff.DIRECTOR)
        if errors:
            return self._block(job_id, "Giám đốc không tạo được plan.json hợp lệ: " + "; ".join(errors))
        order = planning.ordered_tasks(plan)
        self.db.execute("DELETE FROM tasks WHERE job_id=? AND round=?", (job_id, rnd))
        for t in order:
            self.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, depends) VALUES (?,?,?,?,?,?)",
                            (job_id, rnd, str(t["id"]), planning.normalize_role(t["role"]), t["title"], json.dumps([str(x) for x in t.get("depends_on", [])])))
        (d / "plan.md").write_text(self._render_plan(plan, order, rnd), encoding="utf-8")
        # Đợt mới: bộ testcase cũ không còn đúng, để Kiểm định viết lại.
        for f in ("testcases.json", "results.json"):
            (d / "qa" / f).unlink(missing_ok=True)
        self.say(job_id, "director", f"Kế hoạch đợt {rnd}: {plan.get('summary', '')}\n" + "\n".join(
            f"- {t['id']} [{prompts.ROLES[planning.normalize_role(t['role'])][1]}] {t['title']}" for t in order))
        self._commit(job_id, f"plan đợt {rnd}")
        self.set_state(job_id, EXECUTING, round=rnd, note=None, fix_round=0, qa_repairs=0)

    @staticmethod
    def _render_plan(plan: dict, order: list[dict], rnd: int) -> str:
        out = [f"# Kế hoạch (đợt {rnd})", "", plan.get("summary", ""), ""]
        for t in order:
            out += [f"## {t['id']} · {t['title']}  ({prompts.ROLES[planning.normalize_role(t['role'])][1]})",
                    f"- Mục tiêu: {t['goal']}", f"- Phụ thuộc: {', '.join(map(str, t.get('depends_on', []))) or 'không'}",
                    f"- Sản phẩm: {', '.join(t.get('outputs', [])) or '—'}", f"- Tiêu chí: {'; '.join(t.get('acceptance', [])) or '—'}", ""]
        return "\n".join(out)

    def actor_of(self, job_id: str, state: str) -> str | None:
        """Nhân viên đang chịu trách nhiệm ở trạng thái này (EXECUTING: vai của task đang chạy hoặc task kế tiếp)."""
        if state == EXECUTING:
            j = self.get(job_id)
            row = self.db.one("SELECT role FROM tasks WHERE job_id=? AND round=? AND status IN ('running','pending') "
                              "ORDER BY (status='running') DESC, id LIMIT 1", (job_id, j["round"]))
            return prompts.ROLES[row["role"]][1] if row else prompts.ROLES["software"][1]
        return STATE_ACTOR.get(state)

    # --- Bước 4-5: thực thi + tự kiểm -------------------------------------------------
    def _plan(self, job_id: str) -> dict:
        return planning.load_json((self.job_dir(job_id) / "plan.json").read_text(encoding="utf-8"))

    def _prior_reports(self, job_id: str, rnd: int) -> str:
        rows = self.db.query("SELECT task_id, title, report FROM tasks WHERE job_id=? AND round=? AND status='done' ORDER BY id", (job_id, rnd))
        return "\n".join(f"- {r['task_id']} {r['title']}: báo cáo ở @job/{r['report']}" for r in rows if r["report"])

    async def _do_executing(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        rnd = j["round"]
        plan = self._plan(job_id)
        if j["fix_round"] > 0:
            fid = f"FIX{j['fix_round']}"
            if not self.db.one("SELECT 1 FROM tasks WHERE job_id=? AND round=? AND task_id=?", (job_id, rnd, fid)):
                last = self.db.one("SELECT role FROM tasks WHERE job_id=? AND round=? AND task_id NOT LIKE 'FIX%' ORDER BY id DESC LIMIT 1", (job_id, rnd))
                role = last["role"] if last else "software"
                self.db.execute("INSERT INTO tasks(job_id, round, task_id, role, title, depends) VALUES (?,?,?,?,?,?)",
                                (job_id, rnd, fid, role, f"Sửa lỗi Kiểm thử (vòng {j['fix_round']})", "[]"))
            todo = self.db.query("SELECT * FROM tasks WHERE job_id=? AND round=? AND task_id=? AND status!='done'", (job_id, rnd, fid))
        else:
            todo = self.db.query("SELECT * FROM tasks WHERE job_id=? AND round=? AND task_id NOT LIKE 'FIX%' AND status!='done' ORDER BY id", (job_id, rnd))
        by_id = {str(t["id"]): t for t in plan["tasks"]}
        for row in todo:
            self.db.execute("UPDATE tasks SET status='running', started=?, ended=NULL WHERE id=?", (time.time(), row["id"]))
            spec = by_id.get(row["task_id"], {})
            role_file, role_name, llm_role = prompts.ROLES[row["role"]]
            fix = row["task_id"].startswith("FIX")
            known = ["Python có thư viện chuẩn và Pillow; pip install bị chặn."]
            if j["note"]:
                known.append("PHẢN HỒI CẦN XỬ LÝ (nguyên văn):\n" + j["note"])
            inbox = self._inbox(job_id)
            if inbox:
                known.append("CHỦ VỪA NHẮN THÊM:\n" + inbox)
            prior = self._prior_reports(job_id, rnd)
            if prior:
                known.append("Task trước đã xong, đọc báo cáo nếu cần:\n" + prior)
            if self._lessons().strip() != "(chưa có)":
                known.append("Bài học từ job trước:\n" + self._lessons())
            out_hint = ("project trên máy (đang ở nhánh Git riêng của job); sửa trực tiếp file trong đó" if j["workspace"]
                        else "deliverables/ (file cuối) kèm README cách chạy; làm nháp trong work/")
            order = prompts.work_order(job_id, row["task_id"], role_name, {
                "Bối cảnh": f"Job {job_id}: {j['title']}. Toàn bộ yêu cầu ở @job/brief.md, kế hoạch ở @job/plan.json. Task này: {row['title']}.",
                "Việc cần làm": spec.get("goal") or "Sửa các lỗi trong phần Điều đã biết cho đến khi mọi tiêu chí của brief đạt.",
                "Đầu vào": ", ".join(["@job/brief.md", "@job/plan.json", *spec.get("inputs", [])]) + ", @job/inputs/ (nếu có)",
                "Đầu ra": (", ".join(spec.get("outputs", [])) or "—") + f". Nơi đặt sản phẩm: {out_hint}.",
                "Tiêu chí xong": "; ".join(spec.get("acceptance", [])) or "Các tiêu chí nghiệm thu trong brief, đã tự chạy thử và thấy kết quả thật.",
                "Ràng buộc": "Chỉ làm trong thư mục làm việc. Hệ thống tự ghi nhật ký và tự commit Git, bạn không chạy git.",
                "Điều đã biết": "\n".join(known)})
            (d / "work").mkdir(exist_ok=True)
            (d / "work" / f"phieu-{row['task_id']}-dot{rnd}.md").write_text(order, encoding="utf-8")
            r = await self._agent(job_id, role_name, llm_role, prompts.specialist_system(role_file), order)
            missing = self._missing_outputs(job_id, spec)
            if r.ok and missing:      # Giám đốc không tin báo cáo: file khai báo phải có thật; cho làm bù MỘT lần
                self.event(job_id, "warn", f"{row['task_id']} thiếu sản phẩm {missing}, yêu cầu làm bù", staff.DIRECTOR)
                r = await self._agent(job_id, role_name, llm_role, prompts.specialist_system(role_file),
                                      order + "\n\nBÁO CÁO TRƯỚC CỦA BẠN CHƯA ĐỦ: các file sau chưa tồn tại: " + ", ".join(missing) + ". Hãy tạo chúng rồi báo lại.")
                missing = self._missing_outputs(job_id, spec)
            rep = f"reports/{row['task_id']}-dot{rnd}.md"
            (d / "reports").mkdir(exist_ok=True)
            (d / rep).write_text(r.text or f"(không có báo cáo: {r.reason})", encoding="utf-8")
            if not r.ok or missing:
                self.db.execute("UPDATE tasks SET status='failed', ended=?, report=? WHERE id=?", (time.time(), rep, row["id"]))
                self._commit(job_id, f"{row['task_id']} không hoàn thành")
                return self._block(job_id, f"{role_name} không hoàn thành {row['task_id']}: " + (r.reason or f"thiếu file {missing}"))
            self.db.execute("UPDATE tasks SET status='done', ended=?, report=? WHERE id=?", (time.time(), rep, row["id"]))
            self.event(job_id, "task", f"{row['task_id']} xong ({role_name}): {row['title']}", role_name)
            self._commit(job_id, f"{row['task_id']} {row['title']}")
        self.set_state(job_id, QA_DESIGN, note=None)

    def _missing_outputs(self, job_id: str, spec: dict) -> list[str]:
        root = self.work_root(job_id)
        return [o for o in spec.get("outputs", []) if not re.search(r"[*?]", o) and not (root / o).exists()]

    def _snapshot(self, job_id: str) -> str:
        """Bản chụp sản phẩm đưa thẳng cho Kiểm định: cây file + nội dung các file sản phẩm khai báo trong plan.json.
        Model nhỏ hay lang thang 'ls' mãi nếu phải tự khám phá; có sẵn thông tin thì vào việc ngay."""
        root = self.work_root(job_id)
        skip = {".git", "node_modules", "__pycache__", ".venv", "qa", "inputs", "reports", "plans"}
        tree = []
        for pth in sorted(root.rglob("*")):
            rel = pth.relative_to(root)
            if pth.is_file() and not (set(rel.parts) & skip) and len(tree) < 60:
                tree.append(rel.as_posix())
        parts = ["Cây file trong thư mục làm việc:\n" + "\n".join(f"- {t}" for t in tree)]
        try:
            outs = [o for t in self._plan(job_id)["tasks"] for o in t.get("outputs", [])]
        except (OSError, ValueError, KeyError):
            outs = []
        shown = 0
        for o in dict.fromkeys(outs):
            f = root / o
            if f.is_file() and shown < 6 and f.stat().st_size < 60000:
                try:
                    parts.append(f"=== {o} ===\n" + f.read_text(encoding="utf-8")[:8000])
                    shown += 1
                except UnicodeDecodeError:
                    pass
        return "\n\n".join(parts)

    @staticmethod
    def _cases_ok(tc: Path) -> bool:
        try:
            return not planning.validate_cases(planning.load_json(tc.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return False

    # --- Bước 6a: Kiểm định thiết kế testcase -------------------------------------------
    async def _do_qa_design(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        tc = d / "qa" / "testcases.json"
        repair = (j["note"] or "").startswith("SỬA TESTCASE")
        if tc.exists() and not repair and self._cases_ok(tc):    # vòng sửa sản phẩm: bộ testcase vẫn đúng, không viết lại
            return self.set_state(job_id, QA_RUN)
        if tc.exists() and not repair:        # file có nhưng hỏng (model ghi dở, hoặc backend chết giữa chừng): viết lại từ đầu
            tc.unlink()
        before = tc.stat().st_mtime if tc.exists() else None
        errors = []
        for attempt in range(1, 4):
            user = (self._ctx(job_id) + "\n\nThiết kế testcase cho sản phẩm hiện tại. Thư mục làm việc chứa sản phẩm.\n\n"
                    "BẢN CHỤP SẢN PHẨM (đã đủ thông tin, KHÔNG cần khám phá thêm bằng ls/cat; chỉ chạy thử nếu thật sự cần hiểu cách dùng):\n" + self._snapshot(job_id))
            if repair:
                user += "\n\n" + j["note"] + "\nHãy ghi lại @job/qa/testcases.json đã sửa (giữ nguyên id các case)."
            if errors:
                user += "\n\nLẦN TRƯỚC testcases.json KHÔNG HỢP LỆ, sửa và ghi lại:\n- " + "\n- ".join(errors)
            r = await self._agent(job_id, staff.QA_AUTHOR, "qa_author", prompts.qa_author_system(), user, max_tokens=8000)
            if not r.ok:
                return self._block(job_id, r.reason or "Kiểm định không thiết kế được testcase")
            if not tc.exists() or (before is not None and tc.stat().st_mtime <= before):
                errors = ["Bạn chưa ghi @job/qa/testcases.json bằng write_file"]
                continue
            try:
                cases = planning.load_json(tc.read_text(encoding="utf-8"))
            except ValueError as e:
                errors = [f"testcases.json không phải JSON hợp lệ: {e}"]
                continue
            errors = planning.validate_cases(cases)
            if not errors:
                break
            self.event(job_id, "warn", "testcases.json chưa hợp lệ: " + "; ".join(errors), staff.QA_AUTHOR)
        if errors:
            return self._block(job_id, "Kiểm định không tạo được testcases.json hợp lệ: " + "; ".join(errors))
        self.event(job_id, "qa", f"đã {'sửa' if repair else 'thiết kế'} {len(cases['cases'])} testcase", staff.QA_AUTHOR)
        self._commit(job_id, f"testcase ({len(cases['cases'])} case)")
        self.set_state(job_id, QA_RUN, note=None)

    # --- Bước 6b: Kiểm thử viên chạy HẾT testcase + code kiểm lại độc lập ---------------------
    async def _do_qa_run(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        cases = planning.load_json((d / "qa" / "testcases.json").read_text(encoding="utf-8"))["cases"]
        results: dict[str, dict] = {}
        # MỖI testcase một lượt gọi riêng, ngắn và tập trung: model nhỏ/free hay bỏ dở giữa danh sách dài nếu gặp lỗi ở case đầu.
        for c in cases:
            verdict, evidence = None, ""
            for attempt in (1, 2):
                user = "Chạy testcase sau (chỉ MỘT case này) rồi kết luận theo mẫu.\n" + json.dumps(c, ensure_ascii=False, indent=1)
                if attempt > 1:
                    user += "\n\nLẦN TRƯỚC bạn chưa kết luận đúng mẫu. Chạy lại và dòng đầu của câu trả lời cuối phải là KẾT QUẢ: PASS hoặc KẾT QUẢ: FAIL."
                r = await self._agent(job_id, staff.QA_RUNNER, "qa_runner", prompts.qa_runner_system(), user, max_tokens=3000)
                if not r.ok:
                    return self._block(job_id, r.reason or f"Kiểm thử viên không chạy được {c['id']}")
                m = re.search(r"KẾT\s*QUẢ\s*[:：]\s*\**\s*(PASS|FAIL)", r.text, re.I)
                if m:
                    verdict, evidence = m.group(1).upper(), r.text.strip()
                    break
            results[c["id"]] = {"id": c["id"], "status": verdict or "FAIL", "evidence": evidence or "Kiểm thử viên không kết luận được"}
        (d / "qa" / "results.json").write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=1), encoding="utf-8")
        rows = await self._audit(job_id, cases, results)
        # Lỗi ở bước setup của testcase là lỗi CỦA TESTCASE, không đổ cho người làm sản phẩm: gửi về cho Kiểm định sửa (tối đa 2 lần).
        bad = [x for x in rows if x["final"] == "TEST_ERROR"]
        if bad and j["qa_repairs"] < 2:
            self._commit(job_id, f"kiểm thử: {len(bad)} testcase lỗi, trả Kiểm định sửa")
            lst = "\n".join(f"- {x['id']}: {x['why']}" for x in bad)
            self.event(job_id, "qa", f"{len(bad)} testcase lỗi ở bước setup, trả Kiểm định sửa", staff.QA_RUNNER)
            return self.set_state(job_id, QA_DESIGN, qa_repairs=j["qa_repairs"] + 1,
                                  note=f"SỬA TESTCASE: các case sau lỗi ở bước setup (lỗi của testcase, KHÔNG phải của sản phẩm):\n{lst}")
        real = [x for x in rows if x["final"] != "TEST_ERROR"]
        if not real:
            return self._block(job_id, "Mọi testcase đều lỗi ở bước setup dù đã sửa; cần chủ studio xem lại")
        passed = sum(1 for x in real if x["final"] == "PASS")
        report = self._render_qa(rows, passed, len(real), j)
        rname = f"qa-bao-cao-vong{j['round']}-{j['fix_round']}.md"
        (d / rname).write_text(report, encoding="utf-8")
        self.event(job_id, "qa", f"{passed}/{len(real)} testcase PASS" + (f" ({len(bad)} case lỗi testcase bị loại)" if bad else ""), staff.QA_RUNNER)
        self._commit(job_id, f"kiểm thử {passed}/{len(real)} PASS")
        if passed == len(real):
            self.say(job_id, "director", f"Kiểm định: {passed}/{len(real)} testcase PASS (đã kiểm lại độc lập)." + (f" Lưu ý: {len(bad)} testcase lỗi thiết kế đã bị loại." if bad else ""))
            return self.set_state(job_id, HANDOFF)
        fails = "\n".join(f"- {x['id']} {x['title']}: {x['why']}" for x in real if x["final"] != "PASS")
        if j["fix_round"] < config.MAX_FIX_ROUNDS:
            self.set_state(job_id, EXECUTING, fix_round=j["fix_round"] + 1,
                           note=f"KIỂM THỬ TRẢ FAIL {len(real) - passed}/{len(real)} (nguyên văn, xem thêm @job/{rname}):\n{fails}")
        else:
            self._block(job_id, f"Vẫn FAIL sau {config.MAX_FIX_ROUNDS} vòng sửa; cần chủ studio quyết định. Xem {rname}")

    async def _audit(self, job_id: str, cases: list[dict], results: dict[str, dict]) -> list[dict]:
        """Kết luận cuối từng case. Case đo được bằng máy (expect) thì CODE tự chạy lại trong sandbox (bản sao dùng một lần) và so với
        expect: model rẻ có thể ghi bừa PASS, nên kết quả của code thắng. Case còn lại tin kết quả của Kiểm thử viên."""
        j = self.get(job_id)
        root, meta = self.work_root(job_id), self.job_dir(job_id)
        out = []
        for c in cases:
            rr = results.get(c["id"])
            runner = (rr or {}).get("status", "").upper() if rr else None
            row = {"id": c["id"], "title": c["title"], "criterion": c.get("criterion", ""), "runner": runner or "KHÔNG CHẠY",
                   "evidence": (rr or {}).get("evidence", ""), "audited": False, "final": "PASS" if runner == "PASS" else "FAIL",
                   "why": "" if runner == "PASS" else ((rr or {}).get("evidence") or "Kiểm thử viên không chạy case này")}
            if planning.machine_checkable(c) and config.SANDBOX_MODE == "docker":
                # `set -e` cho phần setup + dấu mốc: setup hỏng thì dừng TRƯỚC dấu mốc => lỗi của testcase, không phải của sản phẩm.
                script = "set -e\n" + "\n".join(c.get("setup", [])) + "\necho @@SETUP_OK@@\nset +e\n" + "\n".join(c["steps"])
                try:
                    code, so, se = await asyncio.to_thread(run_in_sandbox, root, script, meta, config.COMMAND_TIMEOUT * 2, True)
                    if "@@SETUP_OK@@" not in so:
                        row.update(audited=True, final="TEST_ERROR", why="setup của testcase thất bại: " + _short(so + se, 400))
                        out.append(row)
                        continue
                    so = so.split("@@SETUP_OK@@", 1)[1]
                    ok, why = planning.evaluate(c, code, so, se)
                    row.update(audited=True, final="PASS" if ok else "FAIL", why=("" if ok else why + f". Đầu ra: {_short(so + se, 300)}"))
                    if runner == "PASS" and not ok:
                        row["why"] = "Kiểm thử viên báo PASS nhưng chạy lại độc lập thì FAIL: " + row["why"]
                        self.event(job_id, "warn", f"{c['id']}: runner báo PASS nhưng kiểm lại FAIL ({why})", staff.QA_RUNNER)
                except ToolError as e:
                    row.update(audited=True, final="FAIL", why=f"không chạy lại được: {e}")
            out.append(row)
        return out

    @staticmethod
    def _render_qa(rows: list[dict], passed: int, total: int, j: dict) -> str:
        head = f"KẾT QUẢ: {'PASS' if passed == total else 'FAIL'}\n\n{passed}/{total} testcase đạt (đợt {j['round']}, vòng sửa {j['fix_round']}).\n"
        body = ["", "| Case | Tiêu chí | Kiểm thử viên | Kiểm lại độc lập | Kết luận |", "|---|---|---|---|---|"]
        for x in rows:
            body.append(f"| {x['id']} {x['title']} | {x['criterion']} | {x['runner']} | {'có' if x['audited'] else 'không (cần mắt)'} | **{x['final']}** |")
        det = ["", "## Chi tiết"]
        for x in rows:
            det.append(f"### {x['id']} {x['title']}: {x['final']}\n{x['why'] or x['evidence']}")
        return head + "\n".join(body + det)

    # --- Bước 7: bàn giao -----------------------------------------------------------------
    async def _do_handoff(self, job_id: str):
        d = self.job_dir(job_id)
        target = d / "deliverables" / "HANDOFF.md"
        before = target.stat().st_mtime if target.exists() else None
        commits = self.db.query("SELECT repo, hash, message FROM commits WHERE job_id=? ORDER BY id", (job_id,))
        ws = self.get(job_id)["workspace"]
        git_note = ("\nCÁC COMMIT (ghi vào HANDOFF để chủ xem lại):\n" + "\n".join(f"- {c['repo']} {c['hash']} {c['message']}" for c in commits[-15:])
                    + (f"\nThay đổi nằm trên nhánh studio/{job_id} của project {ws}; chủ tự quyết định merge, hệ thống không push." if ws else ""))
        r = await self._agent(job_id, staff.DIRECTOR, "director", self._director_sys(),
                              self._ctx(job_id) + "\n\nKiểm định đã PASS toàn bộ (báo cáo mới nhất là @job/qa-bao-cao-*.md). Bước 7: đọc brief, báo cáo kiểm thử và sản phẩm, "
                              "rồi viết @job/deliverables/HANDOFF.md (đã làm gì, cách mở hoặc chạy, giới hạn đã biết, giả định đã dùng)." + git_note)
        if target.exists() and (before is None or target.stat().st_mtime > before):
            self.say(job_id, "director", "Đã xong. " + _short(target.read_text(encoding="utf-8"), 700))
            self._commit(job_id, "handoff")
            self.set_state(job_id, AWAITING_HANDOFF)
        else:
            self._block(job_id, r.reason or "Giám đốc không viết HANDOFF.md")

    # --- Bước 8: rút kinh nghiệm (lỗi ở đây không chặn job) ------------------------------------
    async def _do_lessons(self, job_id: str):
        r = await self._agent(job_id, staff.DIRECTOR, "director", self._director_sys(),
                              self._ctx(job_id) + "\n\nChủ studio đã chấp nhận kết quả. Bước 8: rút kinh nghiệm cho các job sau.")
        lines = [ln for ln in r.text.splitlines() if ln.strip().startswith("- ")][:3]
        if lines:
            with open(self.lessons_path, "a", encoding="utf-8") as f:
                f.write(f"\n<!-- {job_id} -->\n" + "\n".join(lines) + "\n")
            self.event(job_id, "lessons", " | ".join(lines), staff.DIRECTOR)
        else:
            self.event(job_id, "warn", "Giám đốc không ghi được bài học nào")
        self._commit(job_id, "kết thúc job")
        self.set_state(job_id, DONE)
