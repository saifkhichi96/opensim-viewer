from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from platformdirs import user_cache_dir

APP_NAME = "osim-viewer"
APP_AUTHOR = "mukh07"


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
    cache_root().mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="session-", dir=cache_root()))
    try:
        yield root
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
