"""Git cho job. Quy tắc cứng: SAU MỖI LẦN CHẠY của agent, hệ thống phải commit (không phải agent tự nhớ commit).

- Job thường: thư mục job tự là một repo, commit mọi thứ (brief, plan, work/, deliverables/...).
- Job gắn workspace (thư mục project thật trên máy): làm trên nhánh riêng `studio/<mã-job>` tạo từ HEAD hiện tại, commit ở đó.
  Không bao giờ đụng nhánh khác, không push, không force; muốn đưa vào main thì bạn tự merge. Cây làm việc phải sạch lúc bắt đầu
  để không lẫn việc dở dang của bạn vào commit của agent.
Hook của repo (pre-commit...) vẫn chạy; hook fail thì job dừng và báo lý do, chứ không bỏ qua hook.
"""
import os
import re
import subprocess
from pathlib import Path

BRANCH_PREFIX = "studio/"
_ID = ["-c", "user.name=Studio AI", "-c", "user.email=studio@local", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false"]


class GitError(Exception):
    pass


def git(cwd: Path, *args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *_ID, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args[:2])} lỗi: {(r.stderr or r.stdout).strip()[:500]}")
    return r


def is_repo(path: Path) -> bool:
    r = git(path, "rev-parse", "--is-inside-work-tree", check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def toplevel(path: Path) -> Path | None:
    r = git(path, "rev-parse", "--show-toplevel", check=False)
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 else None


def init_repo(path: Path) -> None:
    """Tạo repo nếu chưa có, kèm một commit gốc để mọi thứ sau đó có điểm tựa."""
    if is_repo(path) and toplevel(path) == path.resolve():
        return
    git(path, "init", "-b", "main")
    git(path, "commit", "--allow-empty", "-m", "[studio] khởi tạo repo")


def has_commits(path: Path) -> bool:
    return git(path, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def is_clean(path: Path) -> bool:
    return git(path, "status", "--porcelain").stdout.strip() == ""


def current_branch(path: Path) -> str:
    return git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def check_workspace_allowed(path: Path) -> None:
    """Chặn các thư mục không bao giờ nên giao cho agent sửa."""
    p = path.resolve()
    home = Path.home().resolve()
    sysroot = Path(os.environ.get("SystemRoot", "C:" + chr(92) + "Windows"))
    pf = [Path("C:" + chr(92) + "Program Files"), Path("C:" + chr(92) + "Program Files (x86)")]
    appdata = home / "AppData"
    exact = {Path(p.anchor), home, sysroot, *pf, appdata}
    under_bad = [sysroot, *pf]
    # AppData chứa dữ liệu ứng dụng/khoá: cấm, trừ thư mục Temp (dùng cho thử nghiệm).
    in_appdata = appdata in p.parents and (appdata / "Local" / "Temp") not in p.parents
    if p in exact or any(b in p.parents for b in under_bad) or in_appdata:
        raise GitError(f"Không cho phép dùng '{p}' làm thư mục làm việc (thư mục hệ thống hoặc quá rộng). Hãy chọn thư mục của một project.")
    if not p.is_dir():
        raise GitError(f"Không phải thư mục: {p}")


def prepare_workspace(ws: Path, job_id: str) -> str:
    """Chuẩn bị thư mục làm việc ngoài: kiểm tra, (khởi tạo repo nếu chưa có), tạo nhánh riêng. Trả mô tả để ghi nhật ký."""
    check_workspace_allowed(ws)
    note = []
    if not is_repo(ws):
        git(ws, "init", "-b", "main")
        note.append("thư mục chưa là repo Git: đã `git init`")
    if toplevel(ws) != ws.resolve():
        raise GitError(f"'{ws}' nằm BÊN TRONG một repo lớn hơn ({toplevel(ws)}). Hãy chọn đúng thư mục gốc của repo để commit không lẫn file ngoài.")
    if not has_commits(ws):
        git(ws, "add", "-A")
        git(ws, "commit", "--allow-empty", "-m", "[studio] commit gốc trước khi agent làm việc")
        note.append("repo chưa có commit: đã tạo commit gốc từ trạng thái hiện tại")
    if not is_clean(ws):
        raise GitError("Thư mục làm việc có thay đổi chưa commit. Hãy commit hoặc stash trước, để agent không lẫn việc dở dang của bạn vào commit của nó.")
    base = current_branch(ws)
    branch = BRANCH_PREFIX + job_id
    if git(ws, "rev-parse", "--verify", branch, check=False).returncode == 0:
        git(ws, "checkout", branch)
    else:
        git(ws, "checkout", "-b", branch)
    note.append(f"làm trên nhánh {branch} (tách từ {base}); nhánh {base} không bị đụng")
    return "; ".join(note)


def commit_all(path: Path, message: str) -> dict:
    """Commit mọi thay đổi (kể cả khi không có: --allow-empty để mỗi lần chạy đều có dấu vết). Trả {hash, files, empty}."""
    git(path, "add", "-A")
    n = len([ln for ln in git(path, "diff", "--cached", "--name-only").stdout.splitlines() if ln.strip()])
    git(path, "commit", "--allow-empty", "-m", message)
    h = git(path, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"hash": h, "files": n, "empty": n == 0}


def history(path: Path, limit: int = 50) -> list[dict]:
    if not is_repo(path) or not has_commits(path):
        return []
    out = git(path, "log", f"-{limit}", "--pretty=format:%h%x1f%s%x1f%ct%x1f%D", "--shortstat").stdout
    commits, cur = [], None
    for line in out.splitlines():
        if "\x1f" in line:
            h, s, ts, refs = line.split("\x1f")
            cur = {"hash": h, "subject": s, "ts": int(ts), "refs": refs, "changed": ""}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["changed"] = line.strip()
    return commits


def show_stat(path: Path, rev: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", rev):
        raise GitError("mã commit không hợp lệ")
    return git(path, "show", "--stat", "--format=%h %s%n%b", rev).stdout[-6000:]
