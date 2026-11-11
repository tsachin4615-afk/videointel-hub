from __future__ import annotations

from pathlib import Path

from backend.config import Settings
from backend.security import sanitize_input, verify_token


def test_settings_default_paths():
    settings = Settings()
    assert Path(settings.DATA_DIR).name == "data"
    assert "videointel.db" in settings.DATABASE_URL


def test_sanitize_input_handles_none_and_control_chars():
    assert sanitize_input(None) == ""
    assert sanitize_input("hello\x00world") == "helloworld"


def test_verify_token_requires_match():
    assert verify_token(None) is False
    assert verify_token("abc") is False
