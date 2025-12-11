import json
import os
from pathlib import Path
from typing import Optional

# Config will live in the user's home folder as a simple JSON file
CONFIG_PATH = Path.home() / ".sysreview_config.json"
ENV_VAR_NAME = "OPENAI_API_KEY"


def _read_config() -> Optional[str]:
    """Read the API key from the local config file, if it exists."""
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            key = data.get(ENV_VAR_NAME) or data.get("openai_api_key")
            if key:
                return key.strip()
        except Exception:
            # If anything goes wrong, just treat as no key found
            return None
    return None


def _write_config(key: str) -> None:
    """Save the API key to the local config file."""
    data = {ENV_VAR_NAME: key.strip()}
    try:
        CONFIG_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        # Not fatal if we can't write, the key will just not be saved
        pass


def get_api_key() -> Optional[str]:
    """
    Non-GUI way to get the API key (for CLI tools like chatgpt_helper.py).

    Order:
    1) Environment variable OPENAI_API_KEY
    2) Local JSON config (~/.sysreview_config.json)
    3) Console input (only if running in a terminal)
    """
    # 1) Environment variable
    key = os.getenv(ENV_VAR_NAME)
    if key and key.strip():
        return key.strip()

    # 2) Local config file
    key = _read_config()
    if key:
        return key

    # 3) Console input fallback
    try:
        key = input("Enter your OpenAI API key (it will be saved locally): ").strip()
    except EOFError:
        key = ""

    if not key:
        return None

    _write_config(key)
    return key


def get_api_key_gui() -> Optional[str]:
    """
    GUI-friendly way to get the API key (for your Tkinter app).

    Order:
    1) Local JSON config
    2) Tkinter password-style dialog

    (We deliberately ignore environment variables here so GUI behavior is predictable.)
    """
    # 1) Local config file
    key = _read_config()
    if key:
        return key

    # 2) Tkinter dialog ONLY (no console fallback here)
    import tkinter as tk
    from tkinter import simpledialog, messagebox

    root = tk.Tk()
    root.withdraw()  # Hide the root window

    key = simpledialog.askstring(
        "OpenAI API key",
        "Enter your OpenAI API key.\n\n"
        "It will be stored only on this computer and used to call OpenAI.",
        show="*",
        parent=root,
    )

    if not key:
        messagebox.showerror(
            "Missing API key",
            "An OpenAI API key is required to use this app."
        )
        root.destroy()
        return None

    key = key.strip()
    _write_config(key)
    root.destroy()
    return