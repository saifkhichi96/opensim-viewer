from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "osim-viewer"
APP_AUTHOR = "mukh07"


def appdata_root() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def ensure_appdata_geometry() -> Path:
    """
    Ensure the 'Geometry' assets exist in per-user AppData.
    If missing, copy from bundled assets (wheel or PyInstaller).
    Returns the AppData Geometry path.
    """
    target = appdata_root() / "Geometry"
    if target.exists():
        return target

    # Discover bundled assets in both dev/wheel and PyInstaller contexts.
    candidates = []

    # 1) Package-relative (editable/wheel)
    pkg_assets = Path(__file__).resolve().parent.parent.parent / "assets" / "Geometry"
    candidates.append(pkg_assets)
    print(f"Looking for assets in {pkg_assets}")

    # 2) PyInstaller _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "Geometry")

    for src in candidates:
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, target)
            return target

    raise FileNotFoundError(
        "Could not find bundled Geometry assets. "
        "Ensure assets/Geometry is present in the project or included by PyInstaller."
    )


def _try_symlink(src: Path, dst: Path) -> bool:
    try:
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst, ignore_errors=True)
            else:
                dst.unlink(missing_ok=True)
        os.symlink(src, dst, target_is_directory=True)
        return True
    except Exception:
        return False


def _try_windows_junction(src: Path, dst: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        # mklink /J "dst" "src"
        subprocess.check_call(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)], shell=False
        )
        return True
    except Exception:
        return False


def link_or_copy_geometry(src_dir: Path, dst_link: Path) -> str:
    """
    Create 'dst_link' pointing to 'src_dir'. Prefer symlink; on Windows, try junction; fallback to copy.
    Returns: 'symlink' | 'junction' | 'copy'
    """
    if _try_symlink(src_dir, dst_link):
        return "symlink"
    if _try_windows_junction(src_dir, dst_link):
        return "junction"
    # Final fallback: copy
    if dst_link.exists():
        shutil.rmtree(dst_link, ignore_errors=True)
    shutil.copytree(src_dir, dst_link)
    return "copy"
