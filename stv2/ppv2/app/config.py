from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """
    Directory where the sqlite DB will live.
    Defaults to: ~/.profitplug
    Override with: PROFITPLUG_DATA_DIR
    """
    raw = os.getenv("PROFITPLUG_DATA_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = Path.home() / ".profitplug"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "portfolio.db"


def openai_model() -> str:
    # Keep as env override so you can change without code edits
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")

