"""Tool cho agent, khoá trong thư mục làm việc của job.

Có HAI thư mục:
- work_root: nơi agent làm việc và là thư mục hiện tại của mọi lệnh. Mặc định là thư mục job (jobs/<mã-job>/); nếu job gắn
  với một thư mục trên máy (workspace) thì là thư mục đó, để agent sửa thẳng project thật (mọi thay đổi vẫn bị bắt commit Git).
- meta_root: thư mục job chứa brief.md, plan.json, inputs/... Khi khác work_root, agent đọc chúng qua tiền tố `@job/`.

Hai chế độ chạy lệnh (config.SANDBOX_MODE):
- docker (mặc định): mỗi lệnh chạy trong một container dùng một lần, không mạng, giới hạn RAM/CPU/số tiến trình,
  chỉ mount work_root (+ meta_root chỉ-đọc). Đây là sandbox thật.
- local: PowerShell trên máy bạn + danh sách đen từ khoá. CHỈ là rào chắn mềm.
read_file/write_file/list_dir luôn chạy trên host và luôn bị chặn thoát khỏi hai thư mục trên.
`craft` chạy các công cụ ArtCraft (bản Windows nên không vào được container): chỉ whitelist lệnh, mọi đường dẫn phải nằm trong work_root.
"""
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

from .. import config

# Danh sách đen theo từ khoá: dễ đọc, dễ bị lách. Chỉ dùng ở chế độ local.
BLOCKED = [r"\brm\s+-rf\b", r"\bdel\s+/[sfq]", r"\brmdir\s+/s", r"Remove-Item\b.*-Recurse", r"\bformat\b\s+[a-z]:",
           r"\bshutdown\b", r"\breg\s+(add|delete)", r"\bnetsh\b", r"\bcurl\b", r"\bwget\b", r"Invoke-WebRequest",
           r"Invoke-RestMethod", r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\bwinget\b", r"\bsudo\b",
           r"\.\.[\\/]"]

# Lệnh con ArtCraft được phép (bỏ `mcp` và `ui`: mở cổng/điều khiển app đang chạy).
CRAFT_ALLOWED = {
    "vectorcraft": {"run", "convert", "info", "commands"},
    "pdfcraft": {"info", "render", "text", "edit", "combine", "extract", "split", "check", "audit", "batch", "tools", "run"},
}


class ToolError(Exception):
    """Lỗi trả lại cho model dưới dạng văn bản để nó tự sửa."""


def _command_env() -> dict:
    """PATH cho lệnh local: python của venv backend đứng đầu, rồi công cụ cài bằng winget."""
    from ..health import _fresh_path
    extra = [str(Path(sys.executable).parent), r"C:\Program Files\Inkscape\bin"]
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(extra + [_fresh_path()])
    return env


def run_in_sandbox(work_root: Path, command: str, meta_root: Path | None = None, timeout: int | None = None,
                   isolated: bool = False) -> tuple[int, str, str]:
    """Chạy một lệnh shell trong sandbox. Trả (exit_code, stdout, stderr). Ném ToolError khi quá giờ/lỗi hạ tầng.
    Dùng chung cho tool run_command và cho bước kiểm tra lại của Kiểm định.
    isolated=True (Kiểm định/Kiểm thử): work_root được mount CHỈ-ĐỌC và lệnh chạy trên bản sao dùng một lần trong /tmp, nên dù testcase
    đổi tên/xoá file thì sản phẩm thật (kể cả project của bạn) không bị đụng. Chế độ local không làm được điều này."""
    timeout = timeout or config.COMMAND_TIMEOUT
    work_root = work_root.resolve()
    if config.SANDBOX_MODE == "docker":
        name = f"studio-{uuid.uuid4().hex[:10]}"
        cmd = ["docker", "run", "--rm", "--name", name,
               "--network", config.SANDBOX_NETWORK,        # mặc định none: không ra mạng, không tải được gì
               "--memory", config.SANDBOX_MEMORY, "--cpus", config.SANDBOX_CPUS, "--pids-limit", "256",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--mount", f"type=bind,source={work_root},target=/job" + (",readonly" if isolated else ""), "-w", "/job"]
        if meta_root and meta_root.resolve() != work_root:
            cmd += ["--mount", f"type=bind,source={meta_root.resolve()},target=/studio-job,readonly"]
        if isolated:
            command = ("mkdir -p /tmp/job && tar -C /job --exclude=.git -cf - . | tar -C /tmp/job -xf - && cd /tmp/job && bash -c "
                       + shlex.quote(command))
        cmd += [config.SANDBOX_IMAGE, "bash", "-c", command]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)   # giết CLI không giết container
            raise ToolError(f"Lệnh quá {timeout}s nên bị dừng.")
        except FileNotFoundError:
            raise ToolError("Không tìm thấy docker. Cài Docker Desktop hoặc chọn sandbox 'local' trong Cài đặt.")
        if r.returncode == 125 or (r.returncode == 126 and "docker" in r.stderr.lower()):   # lỗi của docker, không phải của lệnh
            raise ToolError(f"Docker không chạy được lệnh: {r.stderr.strip()[:400]}")
        return r.returncode, r.stdout, r.stderr
    for pat in BLOCKED:
        if re.search(pat, command, re.I):
            raise ToolError(f"Lệnh bị chặn (khớp '{pat}'). Hãy xin Giám đốc nếu thật sự cần.")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", command], cwd=work_root, capture_output=True, text=True,
                           timeout=timeout, env=_command_env(), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise ToolError(f"Lệnh quá {timeout}s nên bị dừng.")
    return r.returncode, r.stdout, r.stderr


def _fmt(code: int, out: str, err: str) -> str:
    return f"exit={code}\n--stdout--\n{out[-6000:]}\n--stderr--\n{err[-3000:]}"


class JobTools:
    def __init__(self, work_root: Path, vision=None, meta_root: Path | None = None, isolated: bool = False, write_scope: str = "all"):
        self.root = work_root.resolve()
        self.write_scope = write_scope   # all | meta (chỉ ghi trong thư mục job: Giám đốc) | qa (chỉ ghi trong qa/: Kiểm định)
        self.isolated = isolated   # True cho Kiểm định/Kiểm thử: chỉ được ghi vào @job/, và lệnh chạy trên bản sao
        self.meta = (meta_root or work_root).resolve()
        # vision(b64, mime, câu_hỏi) -> văn bản; do máy trạng thái truyền vào (gọi vai `vision`).
        self.vision = vision

    # ---- đường dẫn ----
    def _safe(self, rel: str, write: bool = False) -> Path:
        """`@job/...` trỏ tới thư mục job (meta); còn lại trỏ tới work_root. resolve() xử lý cả '..' lẫn symlink."""
        base, sub = self.root, rel
        if rel.startswith("@job/") or rel == "@job":
            base, sub = self.meta, rel[5:]
        p = (base / sub).resolve()
        try:
            p.relative_to(base)
        except ValueError:
            raise ToolError(f"Đường dẫn '{rel}' nằm ngoài thư mục được phép; bị chặn.")
        if ".git" in p.relative_to(base).parts:
            raise ToolError("Không được đụng vào thư mục .git (Git do hệ thống quản lý).")
        if write and self.write_scope != "all":
            allowed = self.meta if self.write_scope == "meta" else (self.meta / "qa").resolve()
            try:
                p.relative_to(allowed)
            except ValueError:
                raise ToolError("Vai của bạn không được ghi ở đây. Chỉ ghi vào " + ("@job/ (tài liệu của job)." if self.write_scope == "meta" else "@job/qa/."))
        return p

    def read_file(self, path: str) -> str:
        p = self._safe(path)
        if not p.is_file():
            raise ToolError(f"Không có file: {path}")
        return p.read_text(encoding="utf-8", errors="replace")[:20000]

    def write_file(self, path: str, content: str) -> str:
        p = self._safe(path, write=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Đã ghi {len(content)} ký tự vào {path}"

    def list_dir(self, path: str = ".") -> str:
        p = self._safe(path)
        if not p.is_dir():
            raise ToolError(f"Không phải thư mục: {path}")
        return "\n".join(sorted(f"{c.name}{'/' if c.is_dir() else ''}" for c in p.iterdir() if c.name != ".git")) or "(trống)"

    def run_command(self, command: str) -> str:
        return _fmt(*run_in_sandbox(self.root, command, self.meta, isolated=self.isolated))

    # ---- ArtCraft ----
    def _craft_exe(self, tool: str) -> Path:
        exe = Path({"vectorcraft": config.VECTORCRAFT_CLI, "pdfcraft": config.PDFCRAFT_CLI}[tool])
        if not exe.is_file():
            raise ToolError(f"Không tìm thấy {tool}-cli tại {exe}. Cài ArtCraft hoặc đặt biến VECTORCRAFT_CLI/PDFCRAFT_CLI trong .env.")
        return exe

    def _in_root(self, token: str) -> None:
        p = (self.root / token).resolve() if not re.match(r"^[A-Za-z]:[\\/]|^\\\\", token) else Path(token).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ToolError(f"Đường dẫn '{token}' nằm ngoài thư mục làm việc; bị chặn.")

    @staticmethod
    def _pathlike(s: str) -> bool:
        return bool(re.search(r"[\\/]|^\.\.|^[A-Za-z]:|\.\w{1,5}$", s)) and not re.match(r"^-?\d+(\.\d+)?$", s)

    def _scan_json(self, node) -> None:
        """Lệnh VectorCraft nhận đường dẫn trong params JSON (file.open, document.export...): quét mọi chuỗi."""
        if isinstance(node, dict):
            for v in node.values():
                self._scan_json(v)
        elif isinstance(node, list):
            for v in node:
                self._scan_json(v)
        elif isinstance(node, str) and (re.match(r"^[A-Za-z]:[\\/]|^\\\\|^/", node) or re.search(r"(^|[\\/])\.\.([\\/]|$)", node)):
            self._in_root(node)

    def craft(self, tool: str, args: list) -> str:
        """Chạy vectorcraft-cli / pdfcraft-cli (ArtCraft) trên máy, cwd = work_root, không qua shell."""
        if tool not in CRAFT_ALLOWED:
            raise ToolError("tool phải là 'vectorcraft' hoặc 'pdfcraft'")
        if not isinstance(args, list) or not args or not all(isinstance(a, (str, int, float)) for a in args):
            raise ToolError("args phải là danh sách chuỗi, ví dụ [\"run\",\"--commands\",\"work/steps.json\",\"--export\",\"deliverables/logo.svg\"]")
        args = [str(a) for a in args]
        if args[0] not in CRAFT_ALLOWED[tool]:
            raise ToolError(f"Lệnh con '{args[0]}' không được phép. Cho phép: {', '.join(sorted(CRAFT_ALLOWED[tool]))}")
        for i, a in enumerate(args[1:], 1):
            val = a.split("=", 1)[1] if a.startswith("--") and "=" in a else a
            if a.startswith("-") and "=" not in a:
                continue
            if val.startswith("{") or val.startswith("["):      # --params '{...}'
                try:
                    self._scan_json(json.loads(val))
                except ValueError:
                    pass
                continue
            if self._pathlike(val):
                self._in_root(val)
                # Công cụ ArtCraft không tự tạo thư mục đích; đường dẫn đã nằm trong vùng cho phép nên tạo hộ cho agent.
                if i >= 1 and args[i - 1] in ("--export", "--out", "--out-dir"):
                    dest = (self.root / val).resolve()
                    (dest if args[i - 1] == "--out-dir" else dest.parent).mkdir(parents=True, exist_ok=True)
                if i >= 1 and args[i - 1] == "--commands":      # quét luôn file lệnh
                    f = (self.root / val).resolve()
                    if f.is_file():
                        try:
                            self._scan_json(json.loads(f.read_text(encoding="utf-8")))
                        except ValueError:
                            pass
        exe = self._craft_exe(tool)
        try:
            r = subprocess.run([str(exe), *args], cwd=self.root, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               timeout=config.COMMAND_TIMEOUT * 2, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise ToolError("Lệnh ArtCraft quá thời gian nên bị dừng.")
        return _fmt(r.returncode, r.stdout, r.stderr)

    def craft_help(self, query: str) -> str:
        """Tra danh mục 885 lệnh của VectorCraft theo từ khoá (id + tham số)."""
        cache = config.DATA_DIR / "vectorcraft-commands.json"
        if not cache.is_file():
            exe = self._craft_exe("vectorcraft")
            r = subprocess.run([str(exe), "commands"], capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise ToolError("Không lấy được danh mục lệnh: " + r.stderr[-200:])
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(r.stdout, encoding="utf-8")
        cat = json.loads(cache.read_text(encoding="utf-8"))
        words = [w.lower() for w in re.split(r"\W+", query) if w]
        if not words:
            raise ToolError("Cần từ khoá, ví dụ 'ellipse', 'fill', 'text', 'export'.")
        scored = []
        for c in cat:
            hay = f"{c.get('id','')} {c.get('label','')}".lower()
            s = sum(w in hay for w in words)
            if s:
                scored.append((s, c))
        scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
        if not scored:
            return "Không có lệnh khớp. Thử từ khoá khác (tiếng Anh)."
        return "\n\n".join(f"{c['id']}: {str(c.get('params',''))[:450]}" for _, c in scored[:8])

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


_ALL = {
    "read_file": _fn("read_file", "Đọc một file (đường dẫn tương đối thư mục làm việc; `@job/...` để đọc brief, plan, inputs của job)", {"path": {"type": "string"}}, ["path"]),
    "write_file": _fn("write_file", "Ghi (ghi đè) một file", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "list_dir": _fn("list_dir", "Liệt kê thư mục", {"path": {"type": "string"}}, []),
    "run_command": _fn("run_command", "Chạy lệnh shell trong sandbox với thư mục làm việc là thư mục hiện tại", {"command": {"type": "string"}}, ["command"]),
    "describe_image": _fn("describe_image", "Nhìn một ảnh png/jpg/webp bằng model vision và trả lời câu hỏi về nó",
                          {"path": {"type": "string"}, "question": {"type": "string"}}, ["path"]),
    "craft": _fn("craft", "Chạy công cụ ArtCraft trên máy: tool='vectorcraft' (vẽ vector, xuất SVG/PNG/PDF) hoặc 'pdfcraft' (xử lý PDF). args là danh sách đối số của CLI",
                 {"tool": {"type": "string", "enum": ["vectorcraft", "pdfcraft"]}, "args": {"type": "array", "items": {"type": "string"}}}, ["tool", "args"]),
    "craft_help": _fn("craft_help", "Tra danh mục lệnh VectorCraft theo từ khoá tiếng Anh (ellipse, fill, text, export...)", {"query": {"type": "string"}}, ["query"]),
}
_FILES = ["read_file", "write_file", "list_dir"]
# Mỗi vai chỉ có đúng công cụ cần: Giám đốc không chạy lệnh; chỉ Chuyên viên media có ArtCraft.
ROLE_TOOLS = {
    "director": _FILES,
    "engineer": _FILES + ["run_command", "describe_image"],
    "media": _FILES + ["run_command", "describe_image", "craft", "craft_help"],
    "qa_author": _FILES + ["run_command", "describe_image"],
    "qa_runner": _FILES + ["run_command", "describe_image"],
}


def tool_specs(role: str) -> list[dict]:
    return [_ALL[n] for n in ROLE_TOOLS.get(role, _FILES)]
