"""Nạp prompt từ prompts/*.md MỖI LẦN dùng (không cache) để bạn sửa file là có hiệu lực ngay."""
from pathlib import Path

from . import config


def _read(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _join(*parts: str) -> str:
    return "\n\n".join(parts)


def director_system(lessons: str, team: str) -> str:
    body = _read("giam-doc").replace("{danh_sách_vai_và_năng_lực}", team).replace("{nội_dung_lessons.md}", lessons)
    return _join(_read("hien-phap"), body, _read("phu-giam-doc"), _read("phu-moi-truong"))


# Vai thực thi: tên trong plan.md ("VAI: ...") -> (file prompt, tên hiển thị, combo)
ROLES = {"phần mềm": ("ky-su-phan-mem", "Kỹ sư phần mềm", "coder"),
         "media": ("chuyen-vien-media", "Chuyên viên media", "coder")}


def specialist_system(role_file: str) -> str:
    # File vai: vài dòng "khoá: giá trị", dấu --- rồi nguyên tắc riêng của vai.
    head, _, principles = _read(role_file).partition("\n---\n")
    meta = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    body = (_read("khung-chuyen-vien").replace("{tên vai}", meta["ten_vai"].strip())
            .replace("{cách tự kiểm của vai}", meta["cach_tu_kiem"].strip())
            .replace("{nguyên tắc riêng của vai}", principles.strip()))
    return _join(_read("hien-phap"), body, _read("phu-moi-truong"))


def qa_system() -> str:
    return _join(_read("hien-phap"), _read("kiem-dinh"), _read("phu-kiem-dinh"), _read("phu-moi-truong"))


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
