import pytest

from app import config, settings


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path_factory):
    # Test thường không cần Docker; test Docker đặt lại SANDBOX_MODE="docker" và tự skip nếu thiếu image.
    monkeypatch.setattr(config, "SANDBOX_MODE", "local")
    # Không bao giờ đọc/ghi cài đặt thật của người dùng (có khoá API).
    d = tmp_path_factory.mktemp("studio-data")
    monkeypatch.setattr(settings, "DATA_DIR", d)
    monkeypatch.setattr(settings, "SETTINGS_FILE", d / "settings.json")
    monkeypatch.setattr(config, "DATA_DIR", d)
    # Test cũ kiểm luồng chờ chủ duyệt: tắt chế độ tự chạy; test tự chạy bật lại bằng settings.update. Không chờ thật.
    settings.update({"autopilot": False})
    monkeypatch.setattr(config, "AUTO_RETRY_DELAY", 0)
