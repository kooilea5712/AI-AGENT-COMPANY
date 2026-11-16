import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, gitops, health, prompts, settings, staff
from .db import DB
from .jobs import machine
from .llm.client import LLMClient

db = DB(config.DB_PATH)
orch = machine.Orchestrator(db, LLMClient())
config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
settings.apply_runtime()
LLMClient.budget_guard = orch.check_budget
LLMClient.usage_sink = orch.on_usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    orch.resume_interrupted()  # job đang dở khi backend chết sẽ chạy lại từ bước gần nhất
    yield


app = FastAPI(title="Studio AI", lifespan=lifespan)
# Chỉ frontend dev (Vite) được gọi; backend vốn chỉ nghe trên localhost.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _job(job_id: str) -> dict:
    try:
        return orch.get(job_id)
    except KeyError:
        raise HTTPException(404, "Không có job này")


async def _upload(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    return [(f.filename or "file", await f.read()) for f in files if f.filename]


async def _act(job_id: str, fn, *args):
    """Chạy một hành động của chủ studio; sai trạng thái thì trả 409; xong thì cho job chạy tiếp ở nền."""
    _job(job_id)
    try:
        fn(job_id, *args)
    except machine.InvalidAction as e:
        raise HTTPException(409, str(e))
    orch.schedule(job_id)
    return {"state": orch.get(job_id)["state"]}


def _read(job_id: str, rel: str) -> str | None:
    p = orch.job_dir(job_id) / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


@app.get("/health")
async def get_health(deep: bool = False):
    return await health.check(deep)


# ---------------- job ----------------
@app.post("/jobs")
async def create_job(description: str = Form(...), workspace: str = Form(""), tier: str = Form(""), budget: str = Form(""),
                     files: list[UploadFile] = File(default=[])):
    if not description.strip():
        raise HTTPException(422, "Mô tả trống")
    try:
        usd = float(budget) if budget.strip() else None
    except ValueError:
        raise HTTPException(422, "Hạn mức phải là số (USD)")
    try:
        job_id = orch.create_job(description, await _upload(files), workspace or None, tier or None, usd)
    except gitops.GitError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    orch.schedule(job_id)
    return {"id": job_id}


@app.post("/workspace/check")
async def workspace_check(path: str = Form(...)):
    """Giao diện hỏi trước: thư mục này có dùng được làm thư mục làm việc không (chưa tạo gì cả)."""
    try:
        p = gitops.parse_path(path)
        gitops.check_workspace_allowed(p)
        if gitops.is_repo(p):
            if gitops.toplevel(p) != p.resolve():
                return {"ok": False, "error": f"Nằm bên trong repo {gitops.toplevel(p)}; hãy chọn thư mục gốc của repo."}
            if not gitops.is_clean(p):
                return {"ok": False, "error": "Có thay đổi chưa commit; hãy commit hoặc stash trước."}
            return {"ok": True, "note": f"Repo Git, nhánh hiện tại {gitops.current_branch(p)}. Agent sẽ làm trên nhánh riêng studio/<mã-job>."}
        return {"ok": True, "note": "Chưa là repo Git: sẽ tự `git init` và tạo commit gốc từ trạng thái hiện tại."}
    except gitops.GitError as e:
        return {"ok": False, "error": str(e)}


@app.get("/jobs")
def list_jobs():
    rows = db.query("SELECT id,title,state,fix_round,round,workspace,created_at,updated_at FROM jobs ORDER BY created_at DESC")
    return [{**r, "step": machine.STEP_OF[r["state"]], "actor": orch.actor_of(r["id"], r["state"])} for r in rows]


@app.get("/jobs/{job_id}")
def job_detail(job_id: str):
    j = _job(job_id)
    d = orch.job_dir(job_id)
    qa = sorted(d.glob("qa-bao-cao-vong*.md"))
    # Model có thể ghi testcases.json dở dang/hỏng JSON: giao diện vẫn phải mở được job, nên parse có bảo vệ.
    try:
        cases = json.loads(_read(job_id, "qa/testcases.json") or "null")
        cases = cases["cases"] if isinstance(cases, dict) and isinstance(cases.get("cases"), list) else []
    except ValueError:
        cases = []
    return {**j, "step": machine.STEP_OF[j["state"]],
            "brief": _read(job_id, "brief.md"), "plan": _read(job_id, "plan.md"),
            "handoff": _read(job_id, "deliverables/HANDOFF.md"),
            "qa_reports": [{"name": p.name, "text": p.read_text(encoding="utf-8")} for p in qa],
            "testcases": cases,
            "owner_approves_brief": settings.load()["owner_approves_brief"], "usage": orch.job_cost(job_id)}


@app.get("/jobs/{job_id}/usage")
def job_usage(job_id: str):
    _job(job_id)
    return orch.job_cost(job_id)


class BudgetBody(BaseModel):
    usd: float | None = None     # None = dùng hạn mức mặc định trong Cài đặt; 0 = không giới hạn


@app.put("/jobs/{job_id}/budget")
def put_budget(job_id: str, body: BudgetBody):
    _job(job_id)
    try:
        orch.set_budget(job_id, body.usd)
    except machine.InvalidAction as e:
        raise HTTPException(422, str(e))
    return orch.job_cost(job_id)


@app.post("/jobs/{job_id}/answer")
async def answer(job_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    return await _act(job_id, orch.answer, text, await _upload(files))


@app.post("/jobs/{job_id}/brief/approve")
async def approve_brief(job_id: str):
    return await _act(job_id, orch.approve_brief)


@app.post("/jobs/{job_id}/brief/reject")
async def reject_brief(job_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    return await _act(job_id, orch.reject_brief, text, await _upload(files))


@app.post("/jobs/{job_id}/handoff/approve")
async def approve_handoff(job_id: str):
    return await _act(job_id, orch.approve_handoff)


@app.post("/jobs/{job_id}/handoff/reject")
async def reject_handoff(job_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    return await _act(job_id, orch.feedback, text, await _upload(files))


@app.post("/jobs/{job_id}/retry")
async def retry(job_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    return await _act(job_id, orch.retry, text, await _upload(files))


@app.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    _job(job_id)
    try:
        orch.cancel(job_id)
    except machine.InvalidAction as e:
        raise HTTPException(409, str(e))
    return {"state": orch.get(job_id)["state"]}


@app.post("/jobs/{job_id}/message")
async def message(job_id: str, text: str = Form(""), files: list[UploadFile] = File(default=[])):
    """Chủ nhắn Giám đốc bất cứ lúc nào (kèm file). Tuỳ trạng thái mà là câu trả lời/phản hồi/hướng dẫn tiếp tục/tin xếp hàng."""
    up = await _upload(files)
    if not text.strip() and not up:
        raise HTTPException(422, "Tin nhắn trống")
    return await _act(job_id, orch.message, text or "(đính kèm file)", up)


@app.get("/jobs/{job_id}/conversation")
def conversation(job_id: str):
    _job(job_id)
    return orch.conversation(job_id)


@app.get("/jobs/{job_id}/events")
async def events(job_id: str, after: int = 0):
    """SSE. Đọc sự kiện từ DB theo id tăng dần thay vì giữ hàng đợi trong RAM:
    nhờ vậy giao diện nối lại (hoặc backend khởi động lại) vẫn thấy đủ nhật ký."""
    _job(job_id)

    async def gen():
        last = after
        while True:
            for e in db.query("SELECT id,ts,kind,message,actor FROM events WHERE job_id=? AND id>? ORDER BY id", (job_id, last)):
                last = e["id"]
                yield f"id: {last}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(gen(), media_type="text/event-stream")


STATE_LABEL = {
    "intake": "Tiếp nhận yêu cầu, viết brief", "waiting_answer": "Chờ chủ studio trả lời câu hỏi", "brief_review": "Giám đốc tự duyệt brief",
    "awaiting_brief": "Chờ chủ studio duyệt brief", "planning": "Lập kế hoạch, chia việc", "executing": "Thực thi và tự kiểm",
    "qa_design": "Thiết kế testcase", "qa_run": "Chạy testcase", "handoff": "Viết bàn giao",
    "awaiting_handoff": "Chủ xem kết quả cuối", "lessons": "Rút kinh nghiệm", "done": "Hoàn tất", "blocked": "Dừng, chờ chủ studio quyết định",
}


@app.get("/jobs/{job_id}/tasks")
def job_tasks(job_id: str):
    _job(job_id)
    rows = db.query("SELECT task_id, round, role, title, depends, status, started, ended, report FROM tasks WHERE job_id=? ORDER BY id", (job_id,))
    return [{**r, "depends": json.loads(r["depends"]), "actor": prompts.ROLES[r["role"]][1]} for r in rows]


@app.get("/jobs/{job_id}/flow")
def job_flow(job_id: str):
    """Luồng công việc của một job: các đoạn (ai làm, bước nào, từ lúc nào), các lần bàn giao giữa nhân viên,
    và ai đang cầm việc. Dựng lại từ nhật ký sự kiện + bảng task nên vẫn đúng sau khi backend khởi động lại."""
    j = _job(job_id)
    evs = db.query("SELECT id,ts,kind,message,actor FROM events WHERE job_id=? ORDER BY id", (job_id,))
    tasks = db.query("SELECT task_id, role, title, started, ended, status FROM tasks WHERE job_id=? AND started IS NOT NULL ORDER BY started", (job_id,))
    marks = []   # (thời điểm, trạng thái bắt đầu)
    for e in evs:
        if e["kind"] != "state":
            continue
        m = re.search(r"(\w+) -> (\w+)$", e["message"])
        if m:
            marks.append((e["ts"], m.group(2)))
        elif "trạng thái" in e["message"]:
            marks.append((e["ts"], e["message"].rsplit(" ", 1)[-1]))

    def stats(ts, end):
        inside = [e for e in evs if e["ts"] >= ts and (end is None or e["ts"] < end)]
        return {"tool_calls": sum(1 for e in inside if e["kind"] == "tool"),
                "llm_calls": sum(1 for e in inside if e["kind"] == "llm" and "gọi vai" in e["message"]),
                "errors": sum(1 for e in inside if e["kind"] in ("error", "tool_error"))}

    segs = []
    for i, (ts, st) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else None
        step = machine.STEP_OF.get(st, 0)
        if st == machine.EXECUTING:
            inner = [t for t in tasks if t["started"] >= ts and (end is None or t["started"] < end)]
            if inner:
                for t in inner:
                    segs.append({"state": st, "label": f"{t['task_id']} · {t['title']}", "step": step, "actor": prompts.ROLES[t["role"]][1],
                                 "started": t["started"], "ended": t["ended"] if t["ended"] else end, "task_id": t["task_id"],
                                 **stats(t["started"], t["ended"] or end)})
                continue
        segs.append({"state": st, "label": STATE_LABEL.get(st, st), "step": step, "actor": orch.actor_of(job_id, st),
                     "started": ts, "ended": end, **stats(ts, end)})
    handoffs = []
    for a, b in zip(segs, segs[1:]):
        if a["actor"] and b["actor"] and a["actor"] != b["actor"]:
            handoffs.append({"from": a["actor"], "to": b["actor"], "at": b["started"], "why": b["label"]})
    cur = segs[-1] if segs else None
    return {"job_id": job_id, "state": j["state"], "segments": segs, "handoffs": handoffs,
            "current": cur and {"actor": cur["actor"], "label": cur["label"], "since": cur["started"],
                                "working": j["state"] in machine.RUNNING,
                                "waiting_owner": j["state"] in machine.WAITING or j["state"] == machine.BLOCKED}}


@app.get("/jobs/{job_id}/git")
def job_git(job_id: str):
    j = _job(job_id)
    d = orch.job_dir(job_id)
    return {"workspace": j["workspace"], "branch": f"studio/{job_id}" if j["workspace"] else None,
            "job_repo": gitops.history(d), "workspace_repo": gitops.history(Path(j["workspace"])) if j["workspace"] else [],
            "commits": db.query("SELECT ts, repo, hash, message, files FROM commits WHERE job_id=? ORDER BY id DESC", (job_id,))}


@app.get("/jobs/{job_id}/git/{rev}")
def job_git_show(job_id: str, rev: str, repo: str = "job"):
    j = _job(job_id)
    path = Path(j["workspace"]) if repo == "workspace" and j["workspace"] else orch.job_dir(job_id)
    try:
        return {"text": gitops.show_stat(path, rev)}
    except gitops.GitError as e:
        raise HTTPException(400, str(e))


def _files(job_id: str) -> list[dict]:
    d = orch.job_dir(job_id)
    return [{"path": p.relative_to(d).as_posix(), "size": p.stat().st_size}
            for p in sorted(d.rglob("*")) if p.is_file() and ".git" not in p.relative_to(d).parts]


@app.get("/jobs/{job_id}/files")
def list_files(job_id: str):
    _job(job_id)
    return _files(job_id)


@app.get("/jobs/{job_id}/files/{path:path}")
def get_file(job_id: str, path: str):
    _job(job_id)
    root = orch.job_dir(job_id).resolve()
    p = (root / path).resolve()
    # Cùng kiểu chặn thoát đường dẫn như tool của agent: file tải về phải nằm trong thư mục job (và không phải .git).
    if root not in p.parents or not p.is_file() or ".git" in p.relative_to(root).parts:
        raise HTTPException(404, "Không có file")
    return FileResponse(p, filename=p.name)


# ---------------- file của project (workspace) ----------------
_WS_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "dist", "build"}


def _ws_root(job_id: str) -> Path:
    ws = _job(job_id)["workspace"]
    if not ws:
        raise HTTPException(404, "Job này không gắn với thư mục project trên máy")
    root = Path(ws).resolve()
    if not root.is_dir():
        raise HTTPException(404, f"Thư mục project không còn tồn tại: {root}")
    return root


@app.get("/jobs/{job_id}/workspace/files")
def ws_files(job_id: str):
    """Mọi file trong project (trừ .git, node_modules, __pycache__...), kèm cờ A/M/D cho file job này đã thêm/sửa/xoá
    (gồm cả phần đang sửa dở chưa commit)."""
    import os
    root = _ws_root(job_id)
    first = db.one("SELECT hash FROM commits WHERE job_id=? AND repo='workspace' ORDER BY id LIMIT 1", (job_id,))
    try:
        changed = gitops.changed_files(root, f"{first['hash']}^" if first else None)
    except gitops.GitError:
        changed = {}
    out, truncated = [], False
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _WS_SKIP)
        for n in sorted(names):
            if n.endswith(".pyc"):
                continue
            if len(out) >= 1500:
                truncated = True
                break
            p = Path(dirpath) / n
            rel = p.relative_to(root).as_posix()
            out.append({"path": rel, "size": p.stat().st_size, "changed": changed.get(rel)})
    for rel, c in changed.items():   # file bị xoá không còn trên đĩa nhưng vẫn nên hiện
        if c == "D" and not any(f["path"] == rel for f in out):
            out.append({"path": rel, "size": 0, "changed": "D"})
    return {"root": str(root), "files": out, "truncated": truncated}


@app.get("/jobs/{job_id}/workspace/files/{path:path}")
def ws_file(job_id: str, path: str):
    root = _ws_root(job_id)
    p = (root / path).resolve()
    # Cùng kiểu chặn thoát đường dẫn: chỉ file nằm trong project, và không cho đọc ruột .git.
    if root not in p.parents or not p.is_file() or ".git" in p.relative_to(root).parts:
        raise HTTPException(404, "Không có file")
    return FileResponse(p, filename=p.name)


# ---------------- nhân viên ----------------
@app.get("/staff")
def get_staff():
    """Danh bạ nhân viên + ai đang làm gì ở các job chưa xong."""
    jobs = db.query("SELECT id,title,state FROM jobs WHERE state NOT IN ('done')")
    busy: dict[str, list] = {}
    for j in jobs:
        who = orch.actor_of(j["id"], j["state"])
        if who:
            busy.setdefault(who, []).append({"id": j["id"], "title": j["title"], "state": j["state"], "label": STATE_LABEL.get(j["state"], j["state"])})
    handled = {r["actor"]: r["n"] for r in db.query("SELECT actor, COUNT(DISTINCT job_id) n FROM events WHERE kind IN ('tool','task','qa') GROUP BY actor")}
    out = []
    for p in staff.STAFF:
        tasks = busy.get(p["name"], [])
        if not p["active"]:
            status = "planned"
        elif any(t["state"] in machine.RUNNING for t in tasks):
            status = "working"
        elif tasks:
            status = "waiting"      # việc đang nằm ở người này nhưng cần họ (chủ studio) hành động
        else:
            status = "idle"
        out.append({**p, "status": status, "tasks": tasks, "jobs_touched": handled.get(p["name"], 0), "models": staff.model_chain(p["role"])})
    return {"staff": out}


# ---------------- cài đặt ----------------
class SettingsPatch(BaseModel):
    connections: dict | None = None
    roles: dict | None = None
    owner_approves_brief: bool | None = None
    autopilot: bool | None = None
    autopilot_retries: int | None = None
    sandbox_mode: str | None = None
    default_tier: str | None = None
    job_budget_usd: float | None = None
    downgrade: dict | None = None
    prices: dict | None = None


# Bộ cấu hình dựng sẵn cho các tình huống hay gặp: có Claude API, laptop không có Ollama, chỉ chạy máy.
PRESETS = [
    {"id": "claude", "label": "Claude làm Giám đốc + Kiểm định (khuyên dùng)",
     "note": "Opus: Giám đốc. Sonnet: thiết kế testcase. Haiku: chạy testcase. Model con dùng OmniRoute/Ollama.",
     "roles": {"director": [["anthropic", settings.OPUS], ["omniroute", "brain"], ["ollama", "studio-gemma4-12b"]],
               "qa_author": [["anthropic", settings.SONNET], ["omniroute", "brain"]],
               "qa_runner": [["anthropic", settings.HAIKU], ["omniroute", "fast"]]}},
    {"id": "claude-all", "label": "Toàn bộ dùng Claude (laptop không có Ollama)", "note": "Không cần Ollama. Tốn quota API hơn.",
     "roles": {"director": [["anthropic", settings.OPUS]], "engineer": [["anthropic", settings.SONNET]], "media": [["anthropic", settings.SONNET]],
               "qa_author": [["anthropic", settings.SONNET]], "qa_runner": [["anthropic", settings.HAIKU]], "vision": [["anthropic", settings.SONNET]]}},
    {"id": "local", "label": "Chỉ dùng model trên máy (Ollama)", "note": "Miễn phí, chạy offline, chất lượng thấp hơn.",
     "roles": {r: [["ollama", m]] for r, m in {"director": "studio-gemma4-12b", "engineer": "studio-gemma4-12b", "media": "studio-gemma4-12b",
                                               "qa_author": "studio-gemma4-12b", "qa_runner": "studio-qwen3-4b", "vision": "studio-gemma4-12b"}.items()}},
]


@app.get("/settings")
def get_settings():
    s = settings.public()
    s["roles_meta"] = dict(settings.ROLES)
    s["presets"] = PRESETS
    s["data_file"] = str(settings.SETTINGS_FILE)
    return s


@app.put("/settings")
def put_settings(patch: SettingsPatch):
    data = patch.model_dump(exclude_none=True)
    if "roles" in data:   # giao diện/preset gửi [kết_nối, model]; chuẩn hoá về {connection, model}
        data["roles"] = {r: [x if isinstance(x, dict) else {"connection": x[0], "model": x[1]} for x in lst] for r, lst in data["roles"].items()}
    try:
        settings.update(data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    settings.apply_runtime()
    return get_settings()


class RoleTest(BaseModel):
    role: str


@app.post("/settings/test")
async def test_role(body: RoleTest):
    """Gọi thật một yêu cầu nhỏ tới vai để biết cấu hình có chạy không (và ứng viên nào đã phục vụ)."""
    if body.role not in settings.ROLES:
        raise HTTPException(404, "Vai không tồn tại")
    return await health._role_check(body.role)


# Giao diện build sẵn (frontend/dist) được phục vụ cùng nguồn với API: app exe chỉ cần mở cổng 8000.
# Mount SAU CÙNG để không che các route API.
_dist = config.ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
