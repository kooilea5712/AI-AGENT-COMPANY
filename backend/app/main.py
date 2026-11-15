import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import config, health
from .db import DB
from .jobs import machine
from .llm.client import LLMClient

db = DB(config.DB_PATH)
orch = machine.Orchestrator(db, LLMClient())
config.JOBS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    orch.resume_interrupted()  # job đang dở khi backend chết sẽ chạy lại từ bước gần nhất
    yield


app = FastAPI(title="Studio AI", lifespan=lifespan)
# Chỉ frontend dev (Vite) được gọi; backend vốn chỉ nghe trên localhost.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class Text(BaseModel):
    text: str = ""


def _job(job_id: str) -> dict:
    try:
        return orch.get(job_id)
    except KeyError:
        raise HTTPException(404, "Không có job này")


# Các endpoint hành động phải là `async def`: schedule() gọi asyncio.create_task, mà hàm `def` thường
# bị FastAPI chạy ở thread không có event loop (lỗi này từng làm job đứng im sau khi bạn trả lời).
def _act(job_id: str, fn, *args):
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


@app.post("/jobs")
async def create_job(description: str = Form(...), files: list[UploadFile] = File(default=[])):
    if not description.strip():
        raise HTTPException(422, "Mô tả trống")
    job_id = orch.create_job(description, [(f.filename or "file", await f.read()) for f in files])
    orch.schedule(job_id)
    return {"id": job_id}


@app.get("/jobs")
def list_jobs():
    rows = db.query("SELECT id,title,state,fix_round,created_at,updated_at FROM jobs ORDER BY created_at DESC")
    return [{**r, "step": machine.STEP_OF[r["state"]]} for r in rows]


@app.get("/jobs/{job_id}")
def job_detail(job_id: str):
    j = _job(job_id)
    d = orch.job_dir(job_id)
    qa = sorted(d.glob("qa-bao-cao-vong*.md"))
    return {**j, "step": machine.STEP_OF[j["state"]],
            "brief": _read(job_id, "brief.md"), "plan": _read(job_id, "plan.md"),
            "handoff": _read(job_id, "deliverables/HANDOFF.md"),
            "qa_reports": [{"name": p.name, "text": p.read_text(encoding="utf-8")} for p in qa]}


@app.post("/jobs/{job_id}/answer")
async def answer(job_id: str, body: Text):
    return _act(job_id, orch.answer, body.text)


@app.post("/jobs/{job_id}/brief/approve")
async def approve_brief(job_id: str):
    return _act(job_id, orch.approve_brief)


@app.post("/jobs/{job_id}/brief/reject")
async def reject_brief(job_id: str, body: Text):
    return _act(job_id, orch.reject_brief, body.text)


@app.post("/jobs/{job_id}/handoff/approve")
async def approve_handoff(job_id: str):
    return _act(job_id, orch.approve_handoff)


@app.post("/jobs/{job_id}/handoff/reject")
async def reject_handoff(job_id: str, body: Text):
    return _act(job_id, orch.reject_handoff, body.text)


@app.post("/jobs/{job_id}/retry")
async def retry(job_id: str, body: Text):
    return _act(job_id, orch.retry, body.text)


@app.get("/jobs/{job_id}/events")
async def events(job_id: str, after: int = 0):
    """SSE. Đọc sự kiện từ DB theo id tăng dần thay vì giữ hàng đợi trong RAM:
    nhờ vậy giao diện nối lại (hoặc backend khởi động lại) vẫn thấy đủ nhật ký."""
    _job(job_id)

    async def gen():
        last = after
        while True:
            for e in db.query("SELECT id,ts,kind,message FROM events WHERE job_id=? AND id>? ORDER BY id", (job_id, last)):
                last = e["id"]
                yield f"id: {last}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _files(job_id: str) -> list[dict]:
    d = orch.job_dir(job_id)
    return [{"path": p.relative_to(d).as_posix(), "size": p.stat().st_size}
            for p in sorted(d.rglob("*")) if p.is_file()]


@app.get("/jobs/{job_id}/files")
def list_files(job_id: str):
    _job(job_id)
    return _files(job_id)


@app.get("/jobs/{job_id}/files/{path:path}")
def get_file(job_id: str, path: str):
    _job(job_id)
    root = orch.job_dir(job_id).resolve()
    p = (root / path).resolve()
    # Cùng kiểu chặn thoát đường dẫn như tool của agent: file tải về phải nằm trong thư mục job.
    if root not in p.parents or not p.is_file():
        raise HTTPException(404, "Không có file")
    return FileResponse(p, filename=p.name)
