"""Nạp prompt từ prompts/*.md MỖI LẦN dùng (không cache) để bạn sửa file là có hiệu lực ngay."""
from . import config


def _read(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def task_prompt(name: str) -> str:
    """Đoạn chỉ dẫn cho một bước cụ thể (duyệt brief, lập kế hoạch...)."""
    return _read(name)


def _env_note() -> str:
    """Phụ lục môi trường phải khớp chế độ sandbox: container Linux (bash) hay PowerShell trên máy."""
    return _read("phu-moi-truong-docker" if config.SANDBOX_MODE == "docker" else "phu-moi-truong")


def _join(*parts: str) -> str:
    return "\n\n".join(parts)


def director_system(lessons: str, team: str) -> str:
    body = _read("giam-doc").replace("{danh_sách_vai_và_năng_lực}", team).replace("{nội_dung_lessons.md}", lessons)
    return _join(_read("hien-phap"), body, _read("phu-giam-doc"), _env_note())


# Vai thực thi: tên trong plan.json ("role") -> (file prompt, tên hiển thị, vai LLM)
ROLES = {"software": ("ky-su-phan-mem", "Kỹ sư phần mềm", "engineer"),
         "media": ("chuyen-vien-media", "Chuyên viên media", "media")}


def specialist_system(role_file: str) -> str:
    # File vai: vài dòng "khoá: giá trị", dấu --- rồi nguyên tắc riêng của vai.
    head, _, principles = _read(role_file).partition("\n---\n")
    meta = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    body = (_read("khung-chuyen-vien").replace("{tên vai}", meta["ten_vai"].strip())
            .replace("{cách tự kiểm của vai}", meta["cach_tu_kiem"].strip())
            .replace("{nguyên tắc riêng của vai}", principles.strip()))
    return _join(_read("hien-phap"), body, _env_note())


def qa_author_system() -> str:
    return _join(_read("hien-phap"), _read("kiem-dinh-thiet-ke"), _env_note())


def qa_runner_system() -> str:
    return _join(_read("hien-phap"), _read("kiem-thu-chay"), _env_note())


def work_order(job_id: str, task_id: str, role: str, fields: dict[str, str]) -> str:
    """Điền phiếu giao việc theo mẫu trong prompts/phieu-giao-viec.md: mỗi dòng 'Nhãn: {mô tả}' -> 'Nhãn: giá trị'."""
    out = []
    for line in _read("phieu-giao-viec").splitlines():
        if line.startswith("PHIẾU GIAO VIỆC"):
            out.append(f"PHIẾU GIAO VIỆC — {job_id} / {task_id}")
        elif line.startswith("Gửi:"):
            out.append(f"Gửi: {role}")
        else:
            label = line.split(":", 1)[0]
            out.append(f"{label}: {fields.get(label, '')}")
    return "\n".join(out)
