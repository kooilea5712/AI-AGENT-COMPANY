"""Thử gọi tool thật với một model Ollama: yêu cầu nó ghi file rồi chạy lệnh, rồi kiểm tra kết quả trên đĩa.
Dùng: backend\\.venv\\Scripts\\python scripts\\probe_tools.py studio-gemma4-12b [tag khác...]
Chạy lệnh qua sandbox hiện hành (docker nếu bật). Dùng khi đổi model/phiên bản Ollama để biết tool call còn đúng chuẩn không.
"""
import asyncio
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agents.loop import run_agent  # noqa: E402
from app.tools.sandbox import JobTools, tool_specs  # noqa: E402

TASK = ("Dùng tool write_file tạo file work/hello.py có nội dung đúng một dòng mã Python: print('xin chao studio'). "
        "Sau đó dùng tool run_command chạy `python work/hello.py` và báo lại kết quả thật.")


class Direct:
    """LLM trỏ thẳng một model Ollama (bỏ qua cấu hình vai): tham số `role` chính là tên model."""
    async def chat(self, model, messages, tools=None, max_tokens=4096):
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post("http://localhost:11434/v1/chat/completions",
                             json={"model": model, "messages": messages, "tools": tools, "max_tokens": max_tokens, "temperature": 0.2, "stream": False})
        r.raise_for_status()
        d = r.json()
        return {"model": d.get("model"), "connection": "ollama", "message": d["choices"][0]["message"], "failed": []}


async def probe(model: str):
    d = Path(tempfile.mkdtemp()) / "probe"
    d.mkdir()
    events = []
    t = time.time()
    # Công cụ của vai engineer; lệnh chạy trong sandbox hiện hành.
    r = await run_agent(Direct(), model, "Bạn là kỹ sư. Làm việc bằng tool, không bằng lời.", TASK, JobTools(d),
                        lambda k, m: events.append((k, m)), 8, "probe", specs=tool_specs("engineer"))
    wrote = (d / "work" / "hello.py").exists()
    ran = any(k == "tool" and "xin chao studio" in m for k, m in events)
    bad = sum(1 for k, _ in events if k == "tool_error")
    print(f"{model}: ok={r.ok} ghi_file={wrote} chay_dung={ran} tool_loi={bad} buoc={r.steps} {time.time()-t:.0f}s {r.reason}")
    for k, m in events:
        if k in ("tool", "tool_error"):
            print("   ", k, m[:160])


for m in sys.argv[1:]:
    asyncio.run(probe(m))
