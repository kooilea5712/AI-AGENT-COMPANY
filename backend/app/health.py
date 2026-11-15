"""Kiểm tra sức khoẻ hệ thống: OmniRoute, Ollama, từng combo, từng công cụ dòng lệnh."""
import os
import shutil
import subprocess

import httpx

from . import config

# Inkscape/ImageMagick cài bằng winget thường không nằm trong PATH của tiến trình đang chạy
# nên thử thêm vài đường dẫn mặc định.
_EXTRA = {
    "inkscape": [r"C:\Program Files\Inkscape\bin\inkscape.exe"],
    "magick": [r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"],
}


def _fresh_path() -> str:
    """winget sửa PATH trong registry; tiến trình đã chạy từ trước không thấy. Đọc lại từ registry."""
    try:
        import winreg
        parts = []
        for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            with winreg.OpenKey(hive, sub) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        return os.pathsep.join(parts + [os.environ.get("PATH", "")])
    except Exception:  # noqa: BLE001 - không phải Windows hoặc lỗi registry: dùng PATH hiện tại
        return os.environ.get("PATH", "")


def _tool(name: str) -> dict:
    path = shutil.which(name) or shutil.which(name, path=_fresh_path())
    if not path:
        for p in _EXTRA.get(name, []):
            if shutil.which(p):
                path = p
    if not path and name == "python":
        path = shutil.which("py")
    if not path:
        return {"ok": False, "version": None, "path": None}
    flag = {"ffmpeg": "-version", "ffprobe": "-version", "magick": "-version"}.get(name, "--version")
    try:
        out = subprocess.run([path, flag], capture_output=True, text=True, timeout=15).stdout
        version = (out.strip().splitlines() or [""])[0][:100]
    except Exception as e:  # noqa: BLE001 - chỉ báo lại cho người dùng
        version = f"không chạy được: {e}"
    return {"ok": True, "version": version, "path": path}


async def _combo(client: httpx.AsyncClient, name: str) -> dict:
    """Gọi thật một yêu cầu 1 token tới combo; trả model nào đã phục vụ."""
    from .llm.client import LLMClient

    try:
        r = await LLMClient().chat(name, [{"role": "user", "content": "Trả lời đúng một chữ: ok"}], max_tokens=300)
        return {"ok": True, "served_by": r.get("model")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def _sandbox() -> dict:
    """Chế độ sandbox + (nếu docker) engine có chạy và image đã dựng chưa."""
    info = {"mode": config.SANDBOX_MODE, "network": config.SANDBOX_NETWORK}
    if config.SANDBOX_MODE != "docker":
        return {**info, "ok": True, "note": "local: chỉ là rào chắn mềm, không cô lập thật"}
    docker = shutil.which("docker") or shutil.which("docker", path=_fresh_path())
    if not docker:
        return {**info, "ok": False, "error": "không tìm thấy docker"}
    try:
        r = subprocess.run([docker, "image", "inspect", config.SANDBOX_IMAGE, "--format", "{{.Size}}"],
                           capture_output=True, text=True, timeout=20)
    except Exception as e:  # noqa: BLE001
        return {**info, "ok": False, "error": str(e)[:200]}
    if r.returncode != 0:
        return {**info, "ok": False, "error": f"chưa có image '{config.SANDBOX_IMAGE}' hoặc engine tắt: {r.stderr.strip()[:200]}"}
    return {**info, "ok": True, "image": config.SANDBOX_IMAGE}


async def check(deep: bool = False) -> dict:
    """deep=True gọi thật từng combo (chậm: Ollama phải nạp model). Mặc định chỉ kiểm cổng và công cụ."""
    result: dict = {"llm_mode": config.LLM_MODE, "llm_base_url": config.LLM_BASE_URL}
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r = await c.get(f"{config.OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            result["ollama"] = {"ok": True, "models": models}
        except Exception as e:  # noqa: BLE001
            result["ollama"] = {"ok": False, "error": str(e)[:200]}
        try:
            # /v1/models đòi khoá nên không dùng để kiểm "còn sống"; /api/health thì không.
            r = await c.get(f"{config.OMNIROUTE_URL}/api/health")
            result["omniroute"] = {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:  # noqa: BLE001
            result["omniroute"] = {"ok": False, "error": str(e)[:200]}
    # Local model chạy tuần tự (12 GB VRAM) nên kiểm combo lần lượt, không gather.
    result["combos"] = {}
    if deep:
        async with httpx.AsyncClient(timeout=180) as c:
            for name in config.COMBOS:
                result["combos"][name] = await _combo(c, name)
    result["tools"] = {t: _tool(t) for t in config.REQUIRED_CLI_TOOLS}
    result["sandbox"] = _sandbox()
    return result
