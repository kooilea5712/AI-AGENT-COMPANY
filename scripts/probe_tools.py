"""Thử gọi tool thật với một model Ollama: yêu cầu nó ghi file rồi chạy lệnh, rồi kiểm tra kết quả trên đĩa.
Dùng: backend\\.venv\\Scripts\\python scripts\\probe_tools.py qwen2.5-coder:14b [...]
"""
import asyncio
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agents.loop import run_agent  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.tools.sandbox import JobTools  # noqa: E402

TASK = ("Dùng tool write_file tạo file work/hello.py có nội dung đúng một dòng mã Python: print('xin chao studio'). "
        "Sau đó dùng tool run_command chạy `py work/hello.py` và báo lại kết quả thật.")


async def probe(model: str):
    # Ép direct: dùng thẳng Ollama, tên 'combo' chính là tên model.
    from app import config
    config.LLM_MODE = "direct"
    config.DIRECT_MODELS["probe"] = model
    llm = LLMClient("http://localhost:11434/v1")
    d = Path(tempfile.mkdtemp()) / "probe"
    d.mkdir()
    events = []
    t = time.time()
    r = await run_agent(llm, "probe", "Bạn là kỹ sư. Làm việc bằng tool, không bằng lời.", TASK,
                        JobTools(d), lambda k, m: events.append((k, m)), 8, "probe")
    f = d / "work" / "hello.py"
    wrote = f.exists()
    ran = any(k == "tool" and "xin chao studio" in m for k, m in events)
    bad = sum(1 for k, _ in events if k == "tool_error")
    print(f"{model}: ok={r.ok} ghi_file={wrote} chay_dung={ran} tool_loi={bad} "
          f"buoc={r.steps} {time.time()-t:.0f}s {r.reason}")
    for k, m in events:
        if k in ("tool", "tool_error"):
            print("   ", k, m[:160])


for m in sys.argv[1:]:
    asyncio.run(probe(m))
