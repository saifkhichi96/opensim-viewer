from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from platformdirs import user_cache_dir

APP_NAME = "AITV-OSIM-App"
APP_AUTHOR = "saifkhichi96"


def cache_root() -> Path:
    return Path(user_cache_dir(APP_NAME, APP_AUTHOR))


def session_root() -> Path:
    return cache_root() / "session"


def reset_session() -> Path:
    """Delete previous session (if any), create fresh directory, return its path."""
    root = session_root()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextmanager
def session_context(keep: bool = False) -> Iterator[Path]:
    """
    Context manager that yields a fresh session root and cleans up on exit unless `keep` is True.
    """
    root = reset_session()
    try:
        yield root
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
