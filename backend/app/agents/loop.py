"""Vòng lặp agent viết tay bằng function calling.

Ý tưởng: gọi model -> nếu nó yêu cầu tool thì chạy và trả kết quả -> lặp tới khi model
trả lời bằng văn bản thường (coi là xong) hoặc hết giới hạn bước. Model yếu hay trả tool call
sai nên mọi lỗi đều được ĐƯA LẠI cho model dưới dạng kết quả tool để nó tự sửa, không làm sập vòng lặp.
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Callable

from ..tools.sandbox import JobTools, ToolError, tool_specs

LogFn = Callable[[str, str], None]  # (loại sự kiện, nội dung)
MAX_CONSECUTIVE_BAD = 5  # quá số lần tool call hỏng liên tiếp thì bỏ cuộc thay vì đốt quota


@dataclass
class AgentResult:
    text: str
    steps: int
    ok: bool          # False nếu hết bước hoặc model liên tục sai định dạng
    reason: str = ""


def _text_tool_calls(content: str, names: set[str]) -> list[dict]:
    """Một số model local (vd. qwen2.5-coder) viết tool call thành JSON trong content, thường
    bọc trong ```json và có khi nhiều call một lượt, thay vì trường tool_calls.
    Quét từng object JSON bằng raw_decode (regex tham lam sẽ dính hai khối làm một)."""
    dec, i, out = json.JSONDecoder(), 0, []
    content = content or ""
    while (i := content.find("{", i)) != -1:
        try:
            d, end = dec.raw_decode(content, i)
        except json.JSONDecodeError:
            i += 1
            continue
        i = end
        if isinstance(d, dict) and d.get("name") in names and "arguments" in d:
            args = d["arguments"]
            out.append({"id": f"text-call-{len(out)}", "type": "function",
                        "function": {"name": d["name"],
                                     "arguments": args if isinstance(args, str) else json.dumps(args)}})
    return out


async def run_agent(llm, role: str, system: str, user: str, tools: JobTools, log: LogFn,
                    max_steps: int, name: str = "agent", specs: list[dict] | None = None,
                    max_tokens: int = 4096) -> AgentResult:
    """role = vai LLM (director, engineer, ...): quyết định model nào được gọi VÀ agent có những công cụ nào."""
    specs = specs if specs is not None else tool_specs(role)
    names = {t["function"]["name"] for t in specs}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    bad = 0
    recent: list[str] = []
    empty = 0
    for step in range(1, max_steps + 1):
        log("llm", f"[{name}] bước {step}: gọi vai '{role}'")
        try:
            resp = await llm.chat(role, messages, tools=specs, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 - lỗi mạng/model: dừng agent, để máy trạng thái quyết định
            log("error", f"[{name}] lỗi LLM: {e}")
            return AgentResult("", step, False, f"lỗi LLM: {e}")
        msg = resp["message"]
        log("llm", f"[{name}] model phục vụ: {resp.get('connection', '?')}/{resp.get('model')}")
        for f in resp.get("failed") or []:
            log("warn", f"[{name}] ứng viên bị bỏ qua: {f}")   # để chủ thấy khi đang chạy bằng model dự phòng
        calls = msg.get("tool_calls") or []
        if not calls:
            calls = _text_tool_calls(msg.get("content") or "", names)
            if calls:
                log("llm", f"[{name}] tool call nằm trong content, đã tự tách ({len(calls)})")
                msg = {"role": "assistant", "content": None}
        if not calls and not (msg.get("content") or "").strip() and empty < 2:
            # Model "suy nghĩ" (gemma4) đôi khi hết lượt mà content trống: nhắc rồi hỏi lại.
            empty += 1
            log("warn", f"[{name}] model trả nội dung trống, nhắc lần {empty}")
            messages.append({"role": "user", "content": "Câu trả lời của bạn trống. Hãy gọi công cụ cần thiết hoặc trả lời bằng văn bản."})
            continue
        if not calls:
            log("final", f"[{name}] {msg.get('content') or '(trống)'}")  # để chủ studio thấy agent đã nói gì
            return AgentResult(msg.get("content") or "", step, True)

        # Lưu đúng lượt assistant (có tool_calls) vào lịch sử trước khi trả kết quả tool.
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        # Chống lặp vô tận: model yếu hay gọi lại y hệt một call mãi (đã gặp ở qwen2.5-coder:14b).
        sig = json.dumps([(c["function"]["name"], c["function"].get("arguments")) for c in calls], sort_keys=True)
        recent.append(sig)
        if len(recent) >= 3 and len(set(recent[-3:])) == 1:
            log("error", f"[{name}] lặp cùng một tool call 3 lần liên tiếp, dừng")
            return AgentResult("", step, False, "model lặp lại cùng một tool call")
        for c in calls:
            fn = c["function"]["name"]
            raw = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(args, dict):
                    raise ValueError("arguments phải là object JSON")
                if fn not in names:
                    raise ToolError(f"Không có tool '{fn}'")
                # Tool chạy ở thread riêng để lệnh dài (subprocess) không làm đứng SSE/API.
                result = await asyncio.to_thread(getattr(tools, fn), **args)
                bad = 0
                log("tool", f"[{name}] {fn}({_short(args)}) -> {_short(result)}")
            except (ToolError, ValueError, TypeError, json.JSONDecodeError) as e:
                bad += 1
                result = f"LỖI: {e}. Hãy gọi lại đúng định dạng."
                log("tool_error", f"[{name}] {fn}: {e}")
            messages.append({"role": "tool", "tool_call_id": c.get("id", "x"), "content": str(result)})
        if bad >= MAX_CONSECUTIVE_BAD:
            return AgentResult("", step, False, "model liên tục gọi tool sai định dạng")
    return AgentResult("", max_steps, False, f"hết giới hạn {max_steps} bước")


def _short(x, n=200) -> str:
    s = json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"
