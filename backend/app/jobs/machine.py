"""Máy trạng thái job: 8 bước của thiết kế, viết thẳng bằng bảng chuyển trạng thái.

Vì sao không dùng framework: luồng chỉ có hai điểm dừng chờ người, trạng thái nằm trong SQLite,
và bạn cần đọc/gỡ lỗi được. Mỗi trạng thái "đang chạy" có đúng một hàm _do_<trạng_thái>; hàm đó
làm việc rồi gọi set_state sang trạng thái kế. Trạng thái "chờ" không có hàm: chỉ API (hành động của
chủ studio) mới đưa job đi tiếp.
"""
import asyncio
import re
import time
import uuid
from pathlib import Path

from .. import config, prompts, staff
from ..agents.loop import run_agent
from ..db import DB
from ..tools.sandbox import JobTools

# --- Trạng thái -------------------------------------------------------------
INTAKE, WAITING_ANSWER, AWAITING_BRIEF = "intake", "waiting_answer", "awaiting_brief"
PLANNING, EXECUTING, QA = "planning", "executing", "qa"
HANDOFF, AWAITING_HANDOFF, LESSONS, DONE, BLOCKED = "handoff", "awaiting_handoff", "lessons", "done", "blocked"

RUNNING = {INTAKE, PLANNING, EXECUTING, QA, HANDOFF, LESSONS}   # code đang làm việc
WAITING = {WAITING_ANSWER, AWAITING_BRIEF, AWAITING_HANDOFF}    # chờ chủ studio
# Bước (1..8) trong thiết kế, để giao diện vẽ thanh tiến trình. Bước 5 (tự kiểm) nằm trong EXECUTING.
STEP_OF = {INTAKE: 1, WAITING_ANSWER: 1, AWAITING_BRIEF: 2, PLANNING: 3, EXECUTING: 4, QA: 6,
           HANDOFF: 7, AWAITING_HANDOFF: 7, LESSONS: 8, DONE: 8, BLOCKED: 0}

TRANSITIONS = {
    INTAKE: {WAITING_ANSWER, AWAITING_BRIEF, BLOCKED},
    WAITING_ANSWER: {INTAKE},
    AWAITING_BRIEF: {INTAKE, PLANNING},           # trả lại -> viết lại brief; duyệt -> lập kế hoạch
    PLANNING: {EXECUTING, BLOCKED},
    EXECUTING: {QA, BLOCKED},
    QA: {EXECUTING, HANDOFF, BLOCKED},            # FAIL còn lượt sửa -> EXECUTING; hết lượt -> BLOCKED
    HANDOFF: {AWAITING_HANDOFF, BLOCKED},
    AWAITING_HANDOFF: {LESSONS, EXECUTING},       # trả lại bàn giao -> làm lại
    LESSONS: {DONE},
    DONE: set(),
    # Chủ studio bấm "tiếp tục": quay lại bước đã bị chặn (blocked_from). QA bị chặn thì quay về EXECUTING.
    BLOCKED: {INTAKE, PLANNING, EXECUTING, HANDOFF},
}


# Ai chịu trách nhiệm ở từng trạng thái (giao diện vẽ luồng bàn giao từ bảng này).
# EXECUTING là vai do plan.md chọn nên Orchestrator.actor_of() quyết định lúc chạy.
STATE_ACTOR = {INTAKE: "Giám đốc điều phối", WAITING_ANSWER: staff.OWNER, AWAITING_BRIEF: staff.OWNER,
               PLANNING: "Giám đốc điều phối", EXECUTING: "Kỹ sư phần mềm", QA: "Kiểm định",
               HANDOFF: "Giám đốc điều phối", AWAITING_HANDOFF: staff.OWNER, LESSONS: "Giám đốc điều phối",
               BLOCKED: staff.OWNER, DONE: None}


class InvalidAction(Exception):
    pass


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
        self.db.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
                        (*cols.values(), job_id))
        self.event(job_id, "state", f"{cur} -> {new}")

    def _block(self, job_id: str, reason: str):
        self.event(job_id, "error", reason)
        self.set_state(job_id, BLOCKED, error=reason, blocked_from=self.get(job_id)["state"])

    # --- tạo job ------------------------------------------------------------
    def create_job(self, description: str, files: list[tuple[str, bytes]] | None = None) -> str:
        job_id = f"job-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:3]}"
        d = self.job_dir(job_id)
        for sub in ("inputs", "work", "deliverables"):
            (d / sub).mkdir(parents=True)
        for name, data in files or []:
            (d / "inputs" / Path(name).name).write_bytes(data)  # Path(...).name: bỏ mọi thành phần thư mục trong tên upload
        title = description.strip().splitlines()[0][:80] or job_id
        now = time.time()
        self.db.execute("INSERT INTO jobs(id,title,description,state,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                        (job_id, title, description, INTAKE, now, now))
        self.event(job_id, "state", f"tạo job, trạng thái {INTAKE}")
        return job_id

    # --- hành động của chủ studio (API gọi) ----------------------------------
    def _require(self, job_id: str, state: str) -> dict:
        j = self.get(job_id)
        if j["state"] != state:
            raise InvalidAction(f"Job đang ở '{j['state']}', hành động này cần '{state}'")
        return j

    def answer(self, job_id: str, text: str):
        j = self._require(job_id, WAITING_ANSWER)
        with open(self.job_dir(job_id) / "answers.md", "a", encoding="utf-8") as f:
            f.write(f"## Câu hỏi của Giám đốc\n{j['questions']}\n\n## Trả lời của chủ studio\n{text}\n\n")
        self.set_state(job_id, INTAKE, questions=None)

    def approve_brief(self, job_id: str):
        self._require(job_id, AWAITING_BRIEF)
        self.set_state(job_id, PLANNING, note=None)

    def reject_brief(self, job_id: str, note: str):
        self._require(job_id, AWAITING_BRIEF)
        self.set_state(job_id, INTAKE, note=note)

    def approve_handoff(self, job_id: str):
        self._require(job_id, AWAITING_HANDOFF)
        self.set_state(job_id, LESSONS)

    def retry(self, job_id: str, note: str = ""):
        """Tiếp tục job bị chặn từ đúng bước đã dừng, kèm hướng dẫn của chủ studio (nếu có)."""
        j = self._require(job_id, BLOCKED)
        src = j["blocked_from"] or INTAKE
        # QA bị chặn nghĩa là đã hết vòng sửa: cho Kỹ sư làm lại với phản hồi mới và cấp lại đủ lượt.
        target = EXECUTING if src == QA else src
        fields = {"error": None, "fix_round": 0 if src in (QA, EXECUTING) else j["fix_round"]}
        if note:
            fields["note"] = f"CHỦ STUDIO HƯỚNG DẪN KHI TIẾP TỤC: {note}"
        self.set_state(job_id, target, **fields)

    def reject_handoff(self, job_id: str, note: str):
        self._require(job_id, AWAITING_HANDOFF)
        # Chủ studio trả lại: làm lại với phản hồi của họ, và cho lại đủ lượt sửa.
        self.set_state(job_id, EXECUTING, note=f"CHỦ STUDIO TRẢ LẠI BÀN GIAO: {note}", fix_round=0)

    # --- chạy -----------------------------------------------------------------
    def schedule(self, job_id: str):
        """Chạy job nền tới khi gặp trạng thái chờ/kết thúc. Không chạy hai lần cho cùng một job."""
        t = self._tasks.get(job_id)
        if t and not t.done():
            return
        self._tasks[job_id] = asyncio.create_task(self.run(job_id))

    def resume_interrupted(self):
        """Gọi lúc backend khởi động: job đang ở trạng thái 'đang chạy' mà tiến trình đã chết thì chạy lại
        đúng bước đó (mỗi bước được viết để chạy lại được: ghi đè file, đọc lại từ đĩa)."""
        for j in self.db.query("SELECT id, state FROM jobs"):
            if j["state"] in RUNNING:
                self.event(j["id"], "resume", f"backend khởi động lại giữa chừng, chạy lại bước '{j['state']}'")
                self.schedule(j["id"])

    async def run(self, job_id: str):
        try:
            while (state := self.get(job_id)["state"]) in RUNNING:
                await getattr(self, f"_do_{state}")(job_id)
        except Exception as e:  # noqa: BLE001 - bất kỳ lỗi bất ngờ nào cũng phải dừng job và hiện lên giao diện
            if self.get(job_id)["state"] in RUNNING:
                self._block(job_id, f"lỗi bất ngờ: {type(e).__name__}: {e}")

    # --- các agent --------------------------------------------------------------
    async def _agent(self, job_id: str, who: str, combo: str, system: str, user: str):
        return await run_agent(self.llm, combo, system, user, JobTools(self.job_dir(job_id), self._vision_fn()),
                               lambda k, m: self.event(job_id, k, m, who), config.MAX_STEPS_PER_TASK, who)

    def _vision_fn(self):
        """Cầu nối cho tool describe_image: tool chạy ở thread riêng, còn LLMClient là async trên event loop chính."""
        loop = asyncio.get_running_loop()

        def fn(b64: str, mime: str, question: str) -> str:
            msgs = [{"role": "user", "content": [{"type": "text", "text": question},
                                                  {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]
            fut = asyncio.run_coroutine_threadsafe(self.llm.chat("vision", msgs, max_tokens=2000), loop)
            return fut.result(timeout=600)["message"].get("content") or "(model vision trả nội dung trống)"
        return fn

    def _role(self, job_id: str) -> tuple[str, str, str]:
        """Đọc dòng 'VAI: ...' đầu plan.md; không đọc được thì mặc định Kỹ sư phần mềm."""
        plan = self.job_dir(job_id) / "plan.md"
        first = plan.read_text(encoding="utf-8").strip().splitlines()[0] if plan.exists() and plan.read_text(encoding="utf-8").strip() else ""
        m = re.match(r"\W*VAI\s*:\s*(.+)", first, re.I)
        key = m.group(1).strip().lower() if m else ""
        for name, role in prompts.ROLES.items():
            if name in key:
                return role
        if first:
            self.event(job_id, "warn", f"plan.md không có dòng 'VAI:' hợp lệ, dùng Kỹ sư phần mềm")
        return prompts.ROLES["phần mềm"]

    def actor_of(self, job_id: str, state: str) -> str | None:
        """Nhân viên đang chịu trách nhiệm ở trạng thái này của job (EXIT: vai thực thi đọc từ plan.md)."""
        if state == EXECUTING:
            return self._role(job_id)[1]
        return STATE_ACTOR.get(state)

    def _lessons(self) -> str:
        return self.lessons_path.read_text(encoding="utf-8") if self.lessons_path.exists() else "(chưa có)"

    def _director_sys(self) -> str:
        team = ("- Kỹ sư phần mềm (VAI: phần mềm): viết, chạy, test code, script\n"
                "- Chuyên viên media (VAI: media): logo SVG, vector, xử lý ảnh bằng Inkscape/ImageMagick/Pillow\n"
                "- Kiểm định: chạy thật và đối chiếu tiêu chí, trả PASS/FAIL\n"
                "- (Video, âm thanh, game: CHƯA có ở bản này; job cần những thứ đó thì nói rõ trong brief)")
        return prompts.director_system(self._lessons(), team)

    # Bước 1: tiếp nhận
    async def _do_intake(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        brief = d / "brief.md"
        before = brief.stat().st_mtime if brief.exists() else None
        parts = [f"YÊU CẦU CỦA CHỦ STUDIO:\n{j['description']}", f"Mã job: {job_id}"]
        files = sorted(p.name for p in (d / "inputs").iterdir())
        if files:
            parts.append("File đính kèm trong inputs/: " + ", ".join(files))
        if (d / "answers.md").exists():
            parts.append("ĐÃ HỎI VÀ ĐƯỢC TRẢ LỜI:\n" + (d / "answers.md").read_text(encoding="utf-8"))
        if j["note"] and brief.exists():
            parts.append(f"Chủ studio TRẢ LẠI brief hiện có (brief.md) với ghi chú: {j['note']}\nHãy sửa brief.md.")
        if j["asked"] >= 1:
            parts.append("Bạn đã hỏi một lượt rồi: KHÔNG hỏi thêm, tự chọn phương án mặc định và ghi giả định vào brief.")
        parts.append("Việc của bạn bây giờ: bước 1 (tiếp nhận). Hỏi lại nếu bắt buộc, hoặc viết brief.md.")
        r = await self._agent(job_id, "Giám đốc điều phối", "brain", self._director_sys(), "\n\n".join(parts))
        # Model hay chèn một câu dẫn trước "CÂU HỎI:" nên tìm ở đầu dòng bất kỳ, không chỉ đầu văn bản.
        q = re.search(r"^[\s*#]*CÂU HỎI.*", r.text, re.M | re.S)
        if q and j["asked"] < 1:
            self.set_state(job_id, WAITING_ANSWER, questions=q.group(0).strip(), asked=j["asked"] + 1)
        elif brief.exists() and (before is None or brief.stat().st_mtime > before):
            self.set_state(job_id, AWAITING_BRIEF)
        else:
            self._block(job_id, r.reason or "Giám đốc không viết brief.md cũng không hỏi gì")

    # Bước 3: lập kế hoạch
    async def _do_planning(self, job_id: str):
        d = self.job_dir(job_id)
        plan = d / "plan.md"
        before = plan.stat().st_mtime if plan.exists() else None
        r = await self._agent(job_id, "Giám đốc điều phối", "brain", self._director_sys(),
                              "Brief (brief.md) đã được chủ studio duyệt. Bước 3: đọc brief.md rồi viết plan.md.")
        if plan.exists() and (before is None or plan.stat().st_mtime > before):
            self.set_state(job_id, EXECUTING)
        else:
            self._block(job_id, r.reason or "Giám đốc không viết plan.md")

    # Bước 4-5: thực thi + tự kiểm (Kỹ sư tự chạy sản phẩm trước khi báo xong)
    async def _do_executing(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        known = ["Python có thư viện chuẩn và Pillow; pip install bị chặn."]
        if j["note"]:
            known.append("PHẢN HỒI CẦN XỬ LÝ (nguyên văn):\n" + j["note"])
        if self._lessons().strip() != "(chưa có)":
            known.append("Bài học từ job trước:\n" + self._lessons())
        role_file, role_name, role_combo = self._role(job_id)
        order = prompts.work_order(job_id, "T1", role_name, {
            "Bối cảnh": f"Job {job_id}: {j['title']}. Toàn bộ yêu cầu ở brief.md, phân công ở plan.md.",
            "Việc cần làm": "Thực hiện task T1 trong plan.md sao cho đạt mọi tiêu chí nghiệm thu trong brief.md.",
            "Đầu vào": "brief.md, plan.md, inputs/ (nếu có)",
            "Đầu ra": "File cuối trong deliverables/ kèm README cách chạy. Làm nháp trong work/.",
            "Tiêu chí xong": "Các tiêu chí nghiệm thu trong brief.md, đã tự chạy thử và thấy kết quả thật.",
            "Ràng buộc": "Chỉ đọc/ghi trong thư mục job. Hệ thống tự ghi mọi lệnh và kết quả vào log.md; đừng tự ghi đè log.md.",
            "Điều đã biết": "\n".join(known)})
        (d / "work" / f"phieu-T1-vong{j['fix_round']}.md").write_text(order, encoding="utf-8")
        r = await self._agent(job_id, role_name, role_combo, prompts.specialist_system(role_file), order)
        (d / "work" / f"bao-cao-T1-vong{j['fix_round']}.md").write_text(r.text or f"(không có báo cáo: {r.reason})",
                                                                         encoding="utf-8")
        if not r.ok:
            return self._block(job_id, f"Kỹ sư không hoàn thành: {r.reason}")
        # Giám đốc không tin lời báo cáo: kiểm file thật có trong deliverables/.
        if not any(p.is_file() for p in (d / "deliverables").rglob("*")):
            self.event(job_id, "warn", "deliverables/ trống dù Kỹ sư báo xong; chuyển Kiểm định để có kết luận có bằng chứng")
        self.set_state(job_id, QA, note=None)

    # Bước 6: kiểm định, tối đa hai vòng sửa
    async def _do_qa(self, job_id: str):
        j, d = self.get(job_id), self.job_dir(job_id)
        r = await self._agent(job_id, "Kiểm định", "brain", prompts.qa_system(),
                              "Kiểm định job này. Đọc brief.md, rồi chạy và kiểm tra sản phẩm trong deliverables/. "
                              "Báo cáo của Kỹ sư (đừng tin, chỉ để biết họ nói gì) ở work/.")
        (d / f"qa-bao-cao-vong{j['fix_round']}.md").write_text(r.text or f"(không có báo cáo: {r.reason})", encoding="utf-8")
        verdict = parse_verdict(r.text)
        if verdict == "PASS":
            self.set_state(job_id, HANDOFF)
        elif j["fix_round"] < config.MAX_FIX_ROUNDS:
            note = r.text if verdict == "FAIL" else f"Kiểm định không trả đúng mẫu. Nguyên văn:\n{r.text or r.reason}"
            self.set_state(job_id, EXECUTING, fix_round=j["fix_round"] + 1, note=f"KIỂM ĐỊNH TRẢ FAIL (nguyên văn):\n{note}")
        else:
            self._block(job_id, f"Kiểm định vẫn FAIL sau {config.MAX_FIX_ROUNDS} vòng sửa; cần chủ studio quyết định. Xem qa-bao-cao-vong{j['fix_round']}.md")

    # Bước 7: bàn giao (Giám đốc viết HANDOFF.md, rồi chờ chủ studio)
    async def _do_handoff(self, job_id: str):
        d = self.job_dir(job_id)
        target = d / "deliverables" / "HANDOFF.md"
        before = target.stat().st_mtime if target.exists() else None
        r = await self._agent(job_id, "Giám đốc điều phối", "brain", self._director_sys(),
                              "Kiểm định đã PASS toàn bộ (báo cáo mới nhất là qa-bao-cao-*.md). Bước 7: đọc brief.md, "
                              "báo cáo QA và deliverables/, rồi viết deliverables/HANDOFF.md "
                              "(đã làm gì, cách mở hoặc chạy, giới hạn đã biết, giả định đã dùng).")
        if target.exists() and (before is None or target.stat().st_mtime > before):
            self.set_state(job_id, AWAITING_HANDOFF)
        else:
            self._block(job_id, r.reason or "Giám đốc không viết HANDOFF.md")

    # Bước 8: rút kinh nghiệm. Không quan trọng bằng sản phẩm nên lỗi ở đây không chặn job.
    async def _do_lessons(self, job_id: str):
        r = await self._agent(job_id, "Giám đốc điều phối", "brain", self._director_sys(),
                              "Chủ studio đã duyệt bàn giao. Bước 8: rút kinh nghiệm cho các job sau.")
        lines = [ln for ln in r.text.splitlines() if ln.strip().startswith("- ")][:3]
        if lines:
            with open(self.lessons_path, "a", encoding="utf-8") as f:
                f.write(f"\n<!-- {job_id} -->\n" + "\n".join(lines) + "\n")
            self.event(job_id, "lessons", " | ".join(lines))
        else:
            self.event(job_id, "warn", "Giám đốc không ghi được bài học nào")
        self.set_state(job_id, DONE)


def parse_verdict(text: str) -> str | None:
    """Tìm 'KẾT QUẢ: PASS|FAIL'. Model yếu có thể thêm markdown (**) hoặc đổi hoa/thường nên nới nhẹ."""
    m = re.search(r"KẾT\s*QUẢ\s*[:：]\s*\**\s*(PASS|FAIL)", text or "", re.I)
    return m.group(1).upper() if m else None
