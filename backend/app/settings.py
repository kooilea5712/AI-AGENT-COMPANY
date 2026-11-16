"""Cài đặt của người dùng: nhà cung cấp model, model theo từng vai, và vài công tắc.

Lưu ở ~/.studio-ai/settings.json (NGOÀI repo, vì chứa khoá API). Chưa có file thì dùng mặc định bên dưới,
mặc định này tái tạo hành vi cũ (OmniRoute -> Ollama) cộng thêm Claude làm lựa chọn đầu khi bạn nhập khoá.

Mỗi vai có một DANH SÁCH ứng viên theo thứ tự ưu tiên: lỗi mạng/khoá/hết quota thì tự chuyển sang ứng viên sau.
Nhờ vậy laptop không có Ollama vẫn chạy (bỏ ứng viên Ollama, dùng cloud) và ngược lại.
"""
import json
import os
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from . import config, context

DATA_DIR = Path(os.getenv("STUDIO_DATA_DIR") or Path.home() / ".studio-ai")
SETTINGS_FILE = DATA_DIR / "settings.json"

# Tên model Claude hiện hành. Đổi trong Cài đặt khi có bản mới (không cần sửa code).
OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"

ROLES: dict[str, dict] = {
    "director": {"label": "Giám đốc điều phối", "hint": "Viết brief, duyệt brief, chia việc, bàn giao. Nên dùng model mạnh nhất (Claude Opus)."},
    "engineer": {"label": "Kỹ sư phần mềm", "hint": "Viết và chạy code. Cần gọi tool tốt."},
    "media": {"label": "Chuyên viên media", "hint": "Vector/ảnh bằng ArtCraft, Inkscape, ImageMagick."},
    "qa_author": {"label": "Kiểm định: thiết kế testcase", "hint": "Đọc brief và sản phẩm, viết bộ testcase. Nên dùng Claude Sonnet."},
    "qa_runner": {"label": "Kiểm thử viên: chạy testcase", "hint": "Chạy hết testcase và ghi kết quả. Model rẻ/nhanh (Haiku hoặc model free)."},
    "vision": {"label": "Mắt (model vision)", "hint": "Nhìn ảnh để tự kiểm. Cần model có vision."},
}
TIERS = ("full", "economy")
LEGACY_ROLE = {"brain": "director", "coder": "engineer", "fast": "qa_runner", "vision": "vision"}


def _local(url: str) -> bool:
    return (urlparse(url).hostname or "") in ("localhost", "127.0.0.1", "::1")


def defaults() -> dict:
    direct = config.LLM_MODE == "direct"
    dm = config.DIRECT_MODELS
    conns = {
        "anthropic": {"label": "Anthropic (Claude API)", "base_url": "https://api.anthropic.com/v1", "api_key": "", "enabled": True},
        "omniroute": {"label": "OmniRoute (cổng nhiều nhà cung cấp)", "base_url": config.OMNIROUTE_URL.rstrip("/") + "/v1", "api_key": "", "enabled": not direct},
        "ollama": {"label": "Ollama (model chạy trên máy này)", "base_url": config.OLLAMA_URL.rstrip("/") + "/v1", "api_key": "", "enabled": True},
    }

    def chain(claude: str | None, combo: str, local: str) -> list[dict]:
        out = []
        if claude:
            out.append({"connection": "anthropic", "model": claude})
        out.append({"connection": "omniroute", "model": combo})
        out.append({"connection": "ollama", "model": local})
        return out

    return {
        "connections": conns,
        "roles": {
            "director": chain(OPUS, "brain", dm["brain"]),
            "engineer": chain(None, "coder", dm["coder"]),
            "media": chain(None, "coder", dm["coder"]),
            "qa_author": chain(SONNET, "brain", dm["brain"]),
            "qa_runner": chain(HAIKU, "fast", dm["fast"]),
            "vision": chain(None, "vision", dm["vision"]),
        },
        "owner_approves_brief": False,       # False: Giám đốc tự chốt brief; chủ chỉ xem kết quả cuối
        # Tự chạy: Giám đốc không hỏi lại (tự chọn mặc định), job bị chặn thì tự thử lại vài lần, tự chấp nhận bàn giao
        # (chủ vẫn phản hồi được sau đó). Tắt đi thì mọi chỗ dừng đều chờ chủ như cũ.
        "autopilot": True,
        "autopilot_retries": 3,
        "sandbox_mode": config.SANDBOX_MODE,  # docker | local
        # Mức đầu tư mặc định của job mới: full = đúng model đã cấu hình; economy = hạ bậc Claude theo bảng `downgrade`.
        "default_tier": "full",
        "downgrade": {OPUS: SONNET, SONNET: HAIKU},
        # Hạn mức chi phí mỗi job (USD); 0 = không giới hạn. Chỉ tính các model có đơn giá trong `prices`.
        "job_budget_usd": 0.0,
        # Đơn giá USD cho 1 triệu token: {"claude-opus-5-5": {"in": x, "out": y}}. KHÔNG có sẵn số liệu: bạn tự nhập theo bảng giá hiện hành.
        "prices": {},
    }


def load() -> dict:
    s = defaults()
    try:
        user = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return s
    for name, c in (user.get("connections") or {}).items():
        s["connections"].setdefault(name, {"label": name, "base_url": "", "api_key": "", "enabled": True}).update(c)
    for role, lst in (user.get("roles") or {}).items():
        if role in ROLES and isinstance(lst, list) and lst:
            s["roles"][role] = lst
    for k in ("owner_approves_brief", "autopilot", "autopilot_retries", "sandbox_mode", "default_tier", "job_budget_usd"):
        if k in user:
            s[k] = user[k]
    s["downgrade"].update(user.get("downgrade") or {})
    s["prices"] = user.get("prices") or {}
    return s


def _write(user: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")


def update(patch: dict) -> dict:
    """Gộp `patch` vào file cài đặt. Khoá API: bỏ trống/không gửi = giữ nguyên, "__clear__" = xoá."""
    try:
        user = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        user = {}
    user.setdefault("connections", {})
    for name, c in (patch.get("connections") or {}).items():
        if c.get("_delete"):
            user["connections"].pop(name, None)
            continue
        cur = user["connections"].setdefault(name, {})
        for k in ("label", "base_url", "enabled"):
            if k in c:
                cur[k] = c[k]
        key = c.get("api_key")
        if key == "__clear__":
            cur["api_key"] = ""
        elif key:
            cur["api_key"] = key.strip()
    if "roles" in patch:
        user.setdefault("roles", {})
        for role, lst in patch["roles"].items():
            if role not in ROLES:
                raise ValueError(f"Vai không tồn tại: {role}")
            clean = [{"connection": str(x["connection"]), "model": str(x["model"]).strip()} for x in lst if x.get("model", "").strip()]
            if not clean:
                raise ValueError(f"Vai {role} phải có ít nhất một model")
            user["roles"][role] = clean
    for k in ("owner_approves_brief", "autopilot", "autopilot_retries", "sandbox_mode", "default_tier", "job_budget_usd"):
        if k in patch:
            if k == "sandbox_mode" and patch[k] not in ("docker", "local"):
                raise ValueError("sandbox_mode phải là docker hoặc local")
            if k == "default_tier" and patch[k] not in TIERS:
                raise ValueError("default_tier phải là full hoặc economy")
            if k == "autopilot_retries" and (not isinstance(patch[k], int) or isinstance(patch[k], bool) or not 0 <= patch[k] <= 10):
                raise ValueError("autopilot_retries phải là số nguyên 0-10")
            if k == "job_budget_usd" and (not isinstance(patch[k], (int, float)) or patch[k] < 0):
                raise ValueError("job_budget_usd phải là số >= 0 (0 = không giới hạn)")
            user[k] = patch[k]
    if "downgrade" in patch:
        user["downgrade"] = {str(a): str(b) for a, b in patch["downgrade"].items() if str(a).strip() and str(b).strip()}
    if "prices" in patch:
        clean = {}
        for model, p in patch["prices"].items():
            try:
                clean[str(model)] = {"in": float(p["in"]), "out": float(p["out"])}
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Đơn giá của {model} phải có dạng {{in: số, out: số}} (USD cho 1 triệu token)")
            if clean[str(model)]["in"] < 0 or clean[str(model)]["out"] < 0:
                raise ValueError("Đơn giá không được âm")
        user["prices"] = clean
    _write(user)
    return load()


def apply_runtime(s: dict | None = None) -> None:
    """Đẩy công tắc có tác dụng toàn cục vào config (sandbox_mode được đọc ở nhiều nơi)."""
    s = s or load()
    config.SANDBOX_MODE = s["sandbox_mode"]


def public(s: dict | None = None) -> dict:
    """Bản trả cho giao diện: KHÔNG bao giờ gửi khoá, chỉ gửi has_key và 4 ký tự cuối."""
    s = deepcopy(s or load())
    for c in s["connections"].values():
        k = c.pop("api_key", "") or ""
        c["has_key"] = bool(k)
        c["key_hint"] = ("…" + k[-4:]) if len(k) >= 8 else ""
        c["needs_key"] = not _local(c.get("base_url", ""))
    return s


def candidates(role: str, s: dict | None = None, tier: str | None = None) -> list[dict]:
    """Danh sách ứng viên đã giải quyết cho một vai. Ứng viên không dùng được có `skip` kèm lý do.
    tier=economy (lấy từ job hiện tại qua context nếu không truyền): model Claude được hạ bậc theo bảng `downgrade`
    (Opus -> Sonnet, Sonnet -> Haiku); ứng viên không phải Anthropic giữ nguyên."""
    s = s or load()
    tier = tier or context.tier_var.get()
    role = LEGACY_ROLE.get(role, role)
    out = []
    for x in s["roles"][role]:
        c = s["connections"].get(x["connection"])
        model = x["model"]
        if tier == "economy" and x["connection"] == "anthropic":
            model = s["downgrade"].get(model, model)
        item = {"connection": x["connection"], "model": model, "label": (c or {}).get("label", x["connection"]),
                "base_url": (c or {}).get("base_url", ""), "api_key": (c or {}).get("api_key", ""), "skip": None}
        if c is None:
            item["skip"] = "kết nối không tồn tại"
        elif not c.get("enabled", True):
            item["skip"] = "kết nối đang tắt"
        elif not _local(item["base_url"]) and not item["api_key"]:
            item["skip"] = "chưa nhập khoá API"
        out.append(item)
    return out
