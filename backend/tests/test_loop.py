from app.agents.loop import run_agent
from app.tools.sandbox import JobTools


class FakeLLM:
    """Phát lại các câu trả lời đã định sẵn: để test vòng lặp mà không cần model thật."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    async def chat(self, combo, messages, tools=None, max_tokens=4096):
        self.seen.append([m.copy() for m in messages])
        return {"model": "fake", "message": self.replies.pop(0)}


def call(name, args, id="1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": id, "type": "function", "function": {"name": name, "arguments": args}}]}


async def test_tool_then_final(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("write_file", '{"path":"a.txt","content":"hi"}'), {"role": "assistant", "content": "xong"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok and r.text == "xong"
    assert (tmp_path / "j" / "a.txt").read_text() == "hi"


async def test_bad_json_is_returned_to_model_then_recovers(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("write_file", "{không phải json"), call("list_dir", "{}"),
                   {"role": "assistant", "content": "ok"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok
    # Lượt gọi thứ hai phải thấy thông báo lỗi trong kết quả tool.
    assert "LỖI" in llm.seen[1][-1]["content"]


async def test_unknown_tool_and_escape_reported(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("hack", "{}"), call("read_file", '{"path":"../x"}'), {"role": "assistant", "content": "ok"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok
    assert "Không có tool" in llm.seen[1][-1]["content"]
    assert "ngoài thư mục được phép" in llm.seen[2][-1]["content"]


async def test_step_limit(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("write_file", '{"path":"f%d","content":"x"}' % i, str(i)) for i in range(10)])  # khác nhau để không dính bộ phát hiện lặp
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 3)
    assert not r.ok and "giới hạn" in r.reason


async def test_gives_up_after_repeated_garbage(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("write_file", "xxx%d" % i, str(i)) for i in range(10)])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 20)
    assert not r.ok and "sai định dạng" in r.reason


async def test_two_fenced_calls_in_content(tmp_path):
    (tmp_path / "j").mkdir()
    txt = ('```json\n{"name":"write_file","arguments":{"path":"a.txt","content":"1"}}\n```\n\n'
           '```json\n{"name":"write_file","arguments":{"path":"b.txt","content":"2"}}\n```')
    llm = FakeLLM([{"role": "assistant", "content": txt}, {"role": "assistant", "content": "xong"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok and (tmp_path / "j" / "a.txt").exists() and (tmp_path / "j" / "b.txt").exists()


async def test_json_in_content_fallback(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([{"role": "assistant", "content": '{"name":"write_file","arguments":{"path":"b.txt","content":"z"}}'},
                   {"role": "assistant", "content": "xong"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok and (tmp_path / "j" / "b.txt").exists()


async def test_empty_reply_is_nudged(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([{"role": "assistant", "content": ""}, {"role": "assistant", "content": "xong"}])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 5)
    assert r.ok and r.text == "xong" and "trống" in llm.seen[1][-1]["content"]


async def test_identical_call_loop_detected(tmp_path):
    (tmp_path / "j").mkdir()
    llm = FakeLLM([call("list_dir", "{}", str(i)) for i in range(10)])
    r = await run_agent(llm, "coder", "s", "u", JobTools(tmp_path / "j"), lambda *a: None, 20)
    assert not r.ok and "lặp" in r.reason and r.steps == 3
