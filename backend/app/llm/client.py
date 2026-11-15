"""Client OpenAI-compatible duy nhất. Agent chỉ truyền tên combo, không biết model thật.

Dùng httpx thẳng thay vì SDK openai: ít phụ thuộc, và ta thấy rõ từng byte gửi đi
khi gỡ lỗi model yếu trả tool call sai định dạng.
"""
import asyncio

import httpx

from .. import config

# Model local chỉ nạp được một cái một lúc (12 GB VRAM) nên mọi lời gọi đi qua một khoá.
# Với cloud thì khoá này hơi thừa nhưng giữ đơn giản quan trọng hơn tốc độ ở bản thô.
_lock = asyncio.Lock()


class LLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or config.LLM_API_KEY

    def model_for(self, combo: str) -> str:
        # Chế độ direct: ánh xạ combo -> model Ollama. Chế độ omniroute: gửi nguyên tên combo.
        if config.LLM_MODE == "direct":
            return config.DIRECT_MODELS[combo]
        return combo

    async def chat(self, combo: str, messages: list[dict], tools: list[dict] | None = None,
                   max_tokens: int = 4096) -> dict:
        """Trả về {'model': tên model phục vụ, 'message': dict assistant, 'usage': ...}."""
        body: dict = {"model": self.model_for(combo), "messages": messages,
                      "max_tokens": max_tokens, "temperature": 0.2, "stream": False}
        if tools:
            body["tools"] = tools
        async with _lock:
            async with httpx.AsyncClient(timeout=600) as c:
                r = await c.post(f"{self.base_url}/chat/completions", json=body,
                                 headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code != 200:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        return {"model": data.get("model"), "message": data["choices"][0]["message"],
                "usage": data.get("usage")}
