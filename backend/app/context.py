"""Ngữ cảnh theo job truyền ngầm qua các lớp (máy trạng thái -> vòng lặp agent -> client LLM) mà không phải đổi chữ ký hàm.
ContextVar được asyncio.to_thread và run_coroutine_threadsafe sao chép sang luồng khác nên cũng đúng cho tool describe_image."""
from contextvars import ContextVar

job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
tier_var: ContextVar[str] = ContextVar("tier", default="full")   # full = dùng model đúng như cấu hình; economy = hạ bậc Claude
