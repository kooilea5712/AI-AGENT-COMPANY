"""Tool cho agent, khoá trong jobs/<mã-job>/.

GIỚI HẠN (đây chỉ là thay thế tạm cho Docker): chặn đường dẫn thoát ra ngoài và vài lệnh nguy hiểm
theo danh sách, nhưng lệnh chạy bằng quyền của bạn nên script Python do agent viết vẫn có thể làm
bất cứ gì. Đừng coi nó là sandbox thật.
"""
import base64
import os
import re
import subprocess
import sys
from pathlib import Path

from .. import config

# Danh sách đen theo từ khoá: dễ đọc, dễ bị lách. Chấp nhận ở bản thô.
BLOCKED = [r"\brm\s+-rf\b", r"\bdel\s+/[sfq]", r"\brmdir\s+/s", r"Remove-Item\b.*-Recurse", r"\bformat\b\s+[a-z]:",
           r"\bshutdown\b", r"\breg\s+(add|delete)", r"\bnetsh\b", r"\bcurl\b", r"\bwget\b", r"Invoke-WebRequest",
           r"Invoke-RestMethod", r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\bwinget\b", r"\bsudo\b",
           r"\.\.[\\/]"]


class ToolError(Exception):
    """Lỗi trả lại cho model dưới dạng văn bản để nó tự sửa."""


def _command_env() -> dict:
    """PATH cho lệnh của agent: python của venv backend đứng đầu (có Pillow; `python` và `py` đều chạy được),
    rồi các công cụ media cài bằng winget (PATH của tiến trình backend có thể cũ hơn registry)."""
    from ..health import _fresh_path
    extra = [str(Path(sys.executable).parent), r"C:\Program Files\Inkscape\bin"]
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(extra + [_fresh_path()])
    return env


class JobTools:
    def __init__(self, job_dir: Path, vision=None):
        self.root = job_dir.resolve()
        # vision(b64, mime, câu_hỏi) -> văn bản; do máy trạng thái truyền vào (gọi combo `vision`).
        self.vision = vision

    def _safe(self, rel: str) -> Path:
        # resolve() xử lý cả '..' lẫn symlink; relative_to ném lỗi nếu thoát khỏi root.
        p = (self.root / rel).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ToolError(f"Đường dẫn '{rel}' nằm ngoài thư mục job; bị chặn.")
        return p

    def read_file(self, path: str) -> str:
        p = self._safe(path)
        if not p.is_file():
            raise ToolError(f"Không có file: {path}")
        return p.read_text(encoding="utf-8", errors="replace")[:20000]

    def write_file(self, path: str, content: str) -> str:
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Đã ghi {len(content)} ký tự vào {path}"

    def list_dir(self, path: str = ".") -> str:
        p = self._safe(path)
        if not p.is_dir():
            raise ToolError(f"Không phải thư mục: {path}")
        return "\n".join(sorted(f"{c.name}{'/' if c.is_dir() else ''}" for c in p.iterdir())) or "(trống)"

    def run_command(self, command: str) -> str:
        for pat in BLOCKED:
            if re.search(pat, command, re.I):
                raise ToolError(f"Lệnh bị chặn (khớp '{pat}'). Hãy xin Giám đốc nếu thật sự cần.")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", command], cwd=self.root,
                               capture_output=True, text=True, timeout=config.COMMAND_TIMEOUT, env=_command_env(),
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise ToolError(f"Lệnh quá {config.COMMAND_TIMEOUT}s nên bị dừng.")
        return f"exit={r.returncode}\n--stdout--\n{r.stdout[-6000:]}\n--stderr--\n{r.stderr[-3000:]}"

    def describe_image(self, path: str, question: str = "Mô tả chi tiết ảnh này.") -> str:
        """Để agent 'nhìn' ảnh qua model vision (tự kiểm của Chuyên viên media, bằng chứng của Kiểm định)."""
        p = self._safe(path)
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(p.suffix.lower())
        if not mime:
            raise ToolError("Chỉ xem được png/jpg/webp. SVG thì xuất PNG trước (inkscape file.svg -o file.png).")
        if not p.is_file():
            raise ToolError(f"Không có file: {path}")
        if p.stat().st_size > 5_000_000:
            raise ToolError("Ảnh quá 5 MB; hãy thu nhỏ trước (magick in.png -resize 1024x1024 out.png).")
        if self.vision is None:
            raise ToolError("Không có model vision trong ngữ cảnh này.")
        return self.vision(base64.b64encode(p.read_bytes()).decode(), mime, question)


# Schema theo chuẩn OpenAI function calling.
def _fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


TOOL_SPECS = [
    _fn("read_file", "Đọc một file trong thư mục job", {"path": {"type": "string"}}, ["path"]),
    _fn("write_file", "Ghi (ghi đè) một file trong thư mục job",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("list_dir", "Liệt kê thư mục trong job", {"path": {"type": "string"}}, []),
    _fn("run_command", "Chạy lệnh PowerShell với thư mục job làm thư mục hiện tại",
        {"command": {"type": "string"}}, ["command"]),
    _fn("describe_image", "Nhìn một ảnh png/jpg/webp trong job bằng model vision và trả lời câu hỏi về nó",
        {"path": {"type": "string"}, "question": {"type": "string"}}, ["path"]),
]
