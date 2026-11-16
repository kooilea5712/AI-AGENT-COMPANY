"""Client OpenAI-compatible duy nhất, định tuyến theo VAI (director, engineer, ...) chứ không theo tên model.

Mỗi vai có danh sách ứng viên (xem settings.py). Gọi lần lượt; lỗi (mạng, khoá sai, hết quota, model không có...) thì thử ứng viên
kế tiếp, và báo lại ai đã phục vụ để nhật ký ghi rõ. Anthropic có endpoint tương thích OpenAI nên Claude đi cùng đường này.

Dùng httpx thẳng thay vì SDK: ít phụ thuộc, và thấy rõ từng byte gửi đi khi gỡ lỗi model yếu trả tool call sai định dạng.
"""
import asyncio
from urllib.parse import urlparse

import httpx

from .. import settings

# Model local chỉ nạp được một cái một lúc (12 GB VRAM) nên các lời gọi tới máy này đi qua một khoá. Cloud thì không cần.
_local_lock = asyncio.Lock()


class AllFailed(RuntimeError):
    """Mọi ứng viên của vai đều lỗi hoặc bị bỏ qua."""


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in ("localhost", "127.0.0.1", "::1")


class LLMClient:
    async def chat(self, role: str, messages: list[dict], tools: list[dict] | None = None,
                   max_tokens: int = 4096) -> dict:
        """Trả {'model', 'message', 'usage', 'connection', 'failed': [...]} từ ứng viên đầu tiên chạy được."""
        failed: list[str] = []
        cands = settings.candidates(role)
        for c in cands:
            tag = f"{c['connection']}/{c['model']}"
            if c["skip"]:
                failed.append(f"{tag}: bỏ qua ({c['skip']})")
                continue
            body: dict = {"model": c["model"], "messages": messages, "max_tokens": max_tokens, "stream": False}
            if "anthropic.com" not in c["base_url"]:
                body["temperature"] = 0.2   # Claude mới có thể từ chối tham số này nên không gửi cho Anthropic
            if tools:
                body["tools"] = tools
            headers = {"Authorization": f"Bearer {c['api_key'] or 'not-needed'}"}
            try:
                if _is_local(c["base_url"]):
                    async with _local_lock:
                        r = await self._post(c["base_url"], body, headers)
                else:
                    r = await self._post(c["base_url"], body, headers)
            except (httpx.HTTPError, OSError) as e:
                failed.append(f"{tag}: {type(e).__name__} {str(e)[:120]}")
                continue
            if r.status_code != 200:
                failed.append(f"{tag}: HTTP {r.status_code} {r.text[:200]}")
                continue
            try:
                data = r.json()
                msg = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError):
                failed.append(f"{tag}: phản hồi không đúng định dạng")
                continue
            return {"model": data.get("model") or c["model"], "message": msg, "usage": data.get("usage"),
                    "connection": c["connection"], "failed": failed}
        raise AllFailed(f"Vai '{role}': không có ứng viên nào chạy được. " + " | ".join(failed))

    @staticmethod
    async def _post(base_url: str, body: dict, headers: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=600) as c:
            return await c.post(f"{base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
