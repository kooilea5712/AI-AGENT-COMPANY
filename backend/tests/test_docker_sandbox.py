"""Test sandbox Docker thật. Tự skip nếu máy không có engine hoặc chưa dựng image studio-sandbox."""
import shutil
import subprocess

import pytest

from app import config
from app.tools.sandbox import JobTools, ToolError


def _ready() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", "studio-sandbox"], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _ready(), reason="chưa có Docker/image studio-sandbox")


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SANDBOX_MODE", "docker")
    root = tmp_path / "job1"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("bí mật", encoding="utf-8")   # file NGOÀI thư mục job
    return JobTools(root)


def test_runs_in_container_and_writes_back(tools):
    out = tools.run_command("echo hi > work.txt; uname -s; pwd")
    assert "exit=0" in out and "Linux" in out and "/job" in out
    assert (tools.root / "work.txt").read_text().strip() == "hi"      # chỉ thư mục job được mount


def test_cannot_see_host_files(tools, tmp_path):
    out = tools.run_command(f"cat ../secret.txt; ls /mnt 2>&1; ls /d 2>&1; echo END")
    assert "bí mật" not in out


def test_no_network(tools, monkeypatch):
    monkeypatch.setattr(config, "SANDBOX_NETWORK", "none")      # kiểm chế độ cô lập, dù .env của máy đang mở mạng
    out = tools.run_command("python -c \"import urllib.request as u; u.urlopen('http://example.com', timeout=5)\"")
    assert "exit=0" not in out


def test_dangerous_command_is_contained(tools, tmp_path):
    tools.run_command("rm -rf / 2>/dev/null; rm -rf /job/* 2>/dev/null")
    assert (tmp_path / "secret.txt").exists()                          # host không bị đụng


def test_timeout_kills_container(tools, monkeypatch):
    monkeypatch.setattr(config, "COMMAND_TIMEOUT", 3)
    with pytest.raises(ToolError):
        tools.run_command("sleep 30")
    left = subprocess.run(["docker", "ps", "-q", "--filter", "name=studio-"], capture_output=True, text=True).stdout
    assert left.strip() == ""                                          # không bỏ sót container chạy ngầm


def test_media_tools_present(tools):
    out = tools.run_command("python -c 'import PIL;print(PIL.__version__)'; ffmpeg -version | head -1; magick -version | head -1; inkscape --version")
    assert "exit=0" in out and "ffmpeg" in out.lower() and "inkscape" in out.lower() and "ImageMagick" in out
