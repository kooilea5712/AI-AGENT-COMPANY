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
