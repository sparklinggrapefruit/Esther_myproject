from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

ENV_VAR_NAME = "OPENAI_API_KEY"
KEY_FILENAME = "sysreviewhelper_key.txt"


def _app_dir() -> Path:
    """
    Directory to store config next to the .exe when packaged, or next to this file in dev.
    """
    if getattr(sys, "frozen", False):  # PyInstaller exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _key_path() -> Path:
    return _app_dir() / KEY_FILENAME


def load_api_key() -> Optional[str]:
    """
    Load key from:
      1) Environment variable (optional override)
      2) sysreviewhelper_key.txt next to the exe
    """
    env = os.getenv(ENV_VAR_NAME)
    if env and env.strip():
        return env.strip()

    p = _key_path()
    if p.exists():
        key = p.read_text(encoding="utf-8", errors="ignore").strip()
        return key or None

    return None


def save_api_key(key: str) -> None:
    """
    Save key to sysreviewhelper_key.txt next to the exe.
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("Empty API key.")
    _key_path().write_text(key, encoding="utf-8")


def delete_api_key() -> None:
    """
    Optional helper if you want a 'Log out' / 'Remove key' button later.
    """
    p = _key_path()
    if p.exists():
        p.unlink()
