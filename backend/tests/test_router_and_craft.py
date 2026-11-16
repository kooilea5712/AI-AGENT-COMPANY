import json
import os

import httpx
import pytest

from app import config, settings
from app.llm.client import AllFailed, LLMClient
from app.tools.sandbox import JobTools, ToolError


def resp(status=200, content="ok", model="m"):
    body = {"model": model, "choices": [{"message": {"role": "assistant", "content": content}}]} if status == 200 else {"error": "x"}
    return httpx.Response(status, json=body)


@pytest.fixture
def seen(monkeypatch):
    calls = []

    async def fake_post(base_url, body, headers):
        calls.append((base_url, body, headers))
        out = fake_post.script.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    fake_post.script = []
    monkeypatch.setattr(LLMClient, "_post", staticmethod(fake_post))
    return calls, fake_post


async def test_anthropic_without_key_is_skipped_then_fallback_serves(seen):
    calls, post = seen
    post.script = [resp(model="brain-combo")]
    r = await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    assert r["connection"] == "omniroute" and "chưa nhập khoá API" in " ".join(r["failed"])
    assert len(calls) == 1 and "20128" in calls[0][0]                    # không hề gọi Anthropic khi chưa có khoá


async def test_director_uses_claude_opus_when_key_present(seen):
    calls, post = seen
    settings.update({"connections": {"anthropic": {"api_key": "sk-ant-test-0000"}}})
    post.script = [resp(model="claude-opus-5-5")]
    r = await LLMClient().chat("director", [{"role": "user", "content": "hi"}], max_tokens=100)
    base, body, headers = calls[0]
    assert base == "https://api.anthropic.com/v1" and body["model"] == settings.OPUS
    assert headers["Authorization"] == "Bearer sk-ant-test-0000" and "temperature" not in body and body["max_tokens"] == 100
    assert r["connection"] == "anthropic"


async def test_falls_through_errors_to_next_candidate(seen):
    calls, post = seen
    settings.update({"connections": {"anthropic": {"api_key": "sk-ant-test-0000"}}})
    post.script = [resp(429), httpx.ConnectError("không kết nối được"), resp(content="từ ollama")]
    r = await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    assert r["connection"] == "ollama" and r["message"]["content"] == "từ ollama"
    assert any("HTTP 429" in f for f in r["failed"]) and any("ConnectError" in f for f in r["failed"])


async def test_all_failed_reports_every_reason(seen):
    calls, post = seen
    post.script = [resp(500), resp(500)]
    with pytest.raises(AllFailed) as e:
        await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    assert "anthropic" in str(e.value) and "omniroute" in str(e.value) and "ollama" in str(e.value)


async def test_laptop_without_ollama_cloud_only(seen):
    calls, post = seen
    settings.update({"connections": {"anthropic": {"api_key": "sk-ant-test-0000"}, "ollama": {"enabled": False}, "omniroute": {"enabled": False}},
                     "roles": {r: [{"connection": "anthropic", "model": settings.SONNET}] for r in ("engineer", "media")}})
    post.script = [resp(content="từ claude")]
    r = await LLMClient().chat("engineer", [{"role": "user", "content": "hi"}])
    assert r["connection"] == "anthropic" and len(calls) == 1             # không đụng tới Ollama


def test_settings_validation_and_masking():
    with pytest.raises(ValueError):
        settings.update({"roles": {"director": []}})
    with pytest.raises(ValueError):
        settings.update({"sandbox_mode": "yolo"})
    settings.update({"connections": {"mine": {"label": "Của tôi", "base_url": "https://x.example/v1", "api_key": "abcdefgh1234"}}})
    pub = settings.public()
    assert "api_key" not in json.dumps(pub) and pub["connections"]["mine"]["key_hint"] == "…1234"
    settings.update({"connections": {"mine": {"api_key": "__clear__"}}})
    assert settings.candidates("director")[0]["skip"]                      # vẫn chưa có khoá cho anthropic
    assert settings.load()["connections"]["mine"]["api_key"] == ""


# ---- ArtCraft ----
@pytest.fixture
def tools(tmp_path):
    root = tmp_path / "job"
    root.mkdir()
    return JobTools(root)


@pytest.mark.parametrize("tool,args,msg", [
    ("vectorcraft", ["mcp"], "không được phép"),
    ("pdfcraft", ["ui", "--control", "x"], "không được phép"),
    ("vectorcraft", ["convert", "C:/Windows/win.ini", "out.svg"], "ngoài thư mục"),
    ("vectorcraft", ["convert", "in.svg", "../ra-ngoai.svg"], "ngoài thư mục"),
    ("pdfcraft", ["render", "a.pdf", "--out", "/etc/x.png"], "ngoài thư mục"),
    ("gimp", ["x"], "tool phải là"),
])
def test_craft_rejects_escapes_and_unknown(tools, tool, args, msg):
    with pytest.raises(ToolError, match=msg):
        tools.craft(tool, args)


def test_craft_scans_json_params_and_command_files(tools):
    (tools.root / "steps.json").write_text(json.dumps([{"command": "document.export", "params": {"path": "C:/Users/x/steal.svg"}}]), encoding="utf-8")
    with pytest.raises(ToolError, match="ngoài thư mục"):
        tools.craft("vectorcraft", ["run", "--commands", "steps.json"])
    with pytest.raises(ToolError, match="ngoài thư mục"):
        tools.craft("vectorcraft", ["run", "--cmd", "file.open", "--params", '{"path": "C:/secret.ai"}'])


@pytest.mark.skipif(not os.path.isfile(config.VECTORCRAFT_CLI), reason="chưa cài ArtCraft VectorCraft")
def test_vectorcraft_really_draws_svg_and_png(tools):
    steps = [{"command": "file.new", "params": {"width": 256, "height": 256, "units": "Pixels"}},
             {"command": "shape.ellipse", "params": {"x": 28, "y": 28, "width": 200, "height": 200}},
             {"command": "paint.setFill", "params": {"color": "#FF8C00"}}]
    tools.write_file("work/steps.json", json.dumps(steps))
    out = tools.craft("vectorcraft", ["run", "--commands", "work/steps.json", "--export", "deliverables/logo.svg", "--export", "deliverables/logo.png"])
    assert "exit=0" in out
    assert "#ff8c00" in (tools.root / "deliverables" / "logo.svg").read_text(encoding="utf-8").lower()
    assert (tools.root / "deliverables" / "logo.png").stat().st_size > 100
    assert "shape.ellipse" in tools.craft_help("ellipse")


def test_tools_per_role_are_minimal():
    from app.tools.sandbox import tool_specs
    names = lambda r: {t["function"]["name"] for t in tool_specs(r)}
    assert names("director") == {"read_file", "write_file", "list_dir"}               # Giám đốc không chạy lệnh
    assert "craft" in names("media") and "craft" not in names("engineer") and "craft" not in names("qa_runner")


def test_write_scopes(tmp_path):
    job = tmp_path / "job"; ws = tmp_path / "ws"
    job.mkdir(); ws.mkdir()
    d = JobTools(ws, meta_root=job, write_scope="meta")
    d.write_file("@job/brief.md", "x")                                   # Giám đốc: ghi được tài liệu job
    with pytest.raises(ToolError, match="không được ghi"):
        d.write_file("app.py", "x")                                      # ...nhưng không sửa project
    q = JobTools(ws, meta_root=job, isolated=True, write_scope="qa")
    q.write_file("@job/qa/results.json", "[]")
    with pytest.raises(ToolError, match="không được ghi"):
        q.write_file("@job/brief.md", "sửa brief")                       # Kiểm định không sửa brief
    with pytest.raises(ToolError, match="không được ghi"):
        q.write_file("app.py", "sửa sản phẩm")
    with pytest.raises(ToolError, match=".git"):
        JobTools(ws).write_file(".git/config", "x")
