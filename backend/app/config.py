"""Cấu hình đọc từ .env (gốc repo). Mọi thứ đổi được mà không sửa code nằm ở đây."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

JOBS_DIR = Path(os.getenv("JOBS_DIR", ROOT / "jobs")).resolve()
PROMPTS_DIR = ROOT / "prompts"
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "studio.sqlite"))

# Một client OpenAI-compatible duy nhất. Muốn bỏ qua OmniRoute (chưa có khoá cloud)
# thì đặt LLM_BASE_URL=http://localhost:11434/v1 và LLM_MODE=direct.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:20128/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")  # Ollama không cần khoá
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://localhost:20128")

# Agent chỉ biết tên combo (brain/coder/fast/vision). Ở chế độ direct, ta ánh xạ
# tên combo sang tên model Ollama thật; ở chế độ OmniRoute, tên combo được gửi nguyên.
LLM_MODE = os.getenv("LLM_MODE", "omniroute")  # omniroute | direct
COMBOS = ["brain", "coder", "fast", "vision"]
DIRECT_MODELS = {
    "brain": os.getenv("DIRECT_MODEL_BRAIN", "gemma4:12b"),
    # qwen2.5-coder:14b bị loại: trả tool call dạng JSON trong content và lặp mãi (xem docs/moi-truong.md).
    "coder": os.getenv("DIRECT_MODEL_CODER", "gemma4:12b"),
    "fast": os.getenv("DIRECT_MODEL_FAST", "qwen3:4b"),
    "vision": os.getenv("DIRECT_MODEL_VISION", "gemma4:12b"),
}

MAX_STEPS_PER_TASK = int(os.getenv("MAX_STEPS_PER_TASK", "25"))
MAX_FIX_ROUNDS = 2  # theo thiết kế: tối đa hai vòng sửa sau FAIL
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "60"))

REQUIRED_CLI_TOOLS = ["git", "python", "node", "ffmpeg", "ffprobe", "magick", "inkscape"]
