import pytest

from app import config


@pytest.fixture(autouse=True)
def _local_sandbox_by_default(monkeypatch):
    # Test thường không cần Docker; test Docker đặt lại SANDBOX_MODE="docker" và tự skip nếu thiếu image.
    monkeypatch.setattr(config, "SANDBOX_MODE", "local")
