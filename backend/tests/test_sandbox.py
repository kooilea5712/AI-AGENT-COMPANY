import pytest

from app.tools.sandbox import JobTools, ToolError


@pytest.fixture
def tools(tmp_path):
    return JobTools(tmp_path / "job1")


def test_write_then_read(tools):
    tools.root.mkdir()
    tools.write_file("work/a.txt", "xin chào")
    assert tools.read_file("work/a.txt") == "xin chào"


@pytest.mark.parametrize("bad", ["../x.txt", "..\\x.txt", "a/../../x.txt", "C:\\Windows\\win.ini", "/etc/passwd"])
def test_path_escape_blocked(tools, bad):
    tools.root.mkdir()
    with pytest.raises(ToolError):
        tools.write_file(bad, "x")
    with pytest.raises(ToolError):
        tools.read_file(bad)


def test_sibling_prefix_not_confused(tmp_path):
    # 'job1-evil' bắt đầu bằng 'job1' nhưng không nằm trong job1: bẫy kinh điển của startswith().
    (tmp_path / "job1").mkdir()
    (tmp_path / "job1-evil").mkdir()
    t = JobTools(tmp_path / "job1")
    with pytest.raises(ToolError):
        t.read_file("../job1-evil/x")


def test_blocked_command(tools):
    tools.root.mkdir()
    with pytest.raises(ToolError):
        tools.run_command("curl http://example.com")


def test_command_runs_in_job_dir(tools):
    tools.root.mkdir()
    out = tools.run_command("Get-Location | Select -Expand Path")
    assert "job1" in out and "exit=0" in out


def test_timeout(tools, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "COMMAND_TIMEOUT", 1)
    tools.root.mkdir()
    with pytest.raises(ToolError):
        tools.run_command("Start-Sleep 5")


def test_command_env_has_pillow_and_media_tools(tools):
    tools.root.mkdir()
    out = tools.run_command("python -c 'import PIL; print(PIL.__version__)'; inkscape --version; ffmpeg -version | Select -First 1")
    assert "exit=0" in out and "Inkscape" in out and "ffmpeg" in out.lower()


def test_describe_image_rules(tools):
    tools.root.mkdir()
    (tools.root / "a.svg").write_text("<svg/>")
    with pytest.raises(ToolError):
        tools.describe_image("a.svg")          # SVG không xem trực tiếp được
    (tools.root / "a.png").write_bytes(b"x")
    with pytest.raises(ToolError):
        tools.describe_image("a.png")          # chưa gắn vision
    t = JobTools(tools.root, vision=lambda b64, mime, q: f"{mime}|{q}")
    assert t.describe_image("a.png", "gì đây?") == "image/png|gì đây?"
    with pytest.raises(ToolError):
        t.describe_image("../x.png")
