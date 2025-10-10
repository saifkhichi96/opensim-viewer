from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from .core import display_model_in_viewer
from .resources import ensure_appdata_geometry, link_or_copy_geometry
from .session import session_context
from .utils import smooth_mot_file

_LOG = logging.getLogger("osim-viewer")


def _setup_logging(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Command-line OpenSim model and motion viewer (OSIM Viewer)"
    )
    parser.add_argument("--osim", type=str, help="Path to the .osim file", default=None)
    parser.add_argument(
        "--mot", type=str, help="Path to the motion (.mot) file", default=None
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="Resample output FPS for the OSIM sequence.",
    )
    parser.add_argument(
        "--color_parts", action="store_true", help="Color skeleton parts."
    )
    parser.add_argument(
        "--color_markers", action="store_true", help="Color markers by parent part."
    )
    parser.add_argument("--mocap", type=str, help="Optional .c3d to visualize markers.")
    parser.add_argument(
        "--joints", action="store_true", help="Show model joints as spheres."
    )
    parser.add_argument(
        "--video",
        type=str,
        help="Path to a video file to render under the model.",
        default=None,
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Use video FPS instead of motion FPS for playback.",
    )
    parser.add_argument(
        "--calib", type=str, required=False, help="Path to TOML calibration file."
    )

    # App switches
    parser.add_argument(
        "--keep-session", action="store_true", help="Keep session cache after exit."
    )
    parser.add_argument(
        "--no-symlink", action="store_true", help="Copy Geometry instead of linking."
    )
    parser.add_argument(
        "--smooth",
        action="store_true",
        help="Apply low-pass filter to motion (.mot) before viewing.",
    )
    parser.add_argument(
        "--cutoff", type=float, default=6.0, help="Cutoff frequency for smoothing (Hz)."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.log_level)

    # Sanity: if video given without calib, we proceed but warn; core will skip overlay.
    if args.video and not args.calib:
        _LOG.warning("Video provided without --calib; overlay will be disabled.")

    with session_context(keep=args.keep_session) as session_root:
        work_dir = session_root / "exec"
        frames_dir = session_root / "frames"
        work_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Prepare Geometry in AppData and link/copy into work_dir
        appdata_geom = ensure_appdata_geometry()
        dst_geom = work_dir / "Geometry"
        mode = (
            link_or_copy_geometry(appdata_geom, dst_geom)
            if not args.no_symlink
            else "copy"
        )
        if mode == "copy" and not args.no_symlink:
            # Force copy as fallback if linking failed
            from .resources import shutil as _shutil  # type: ignore

            if dst_geom.exists():
                _shutil.rmtree(dst_geom, ignore_errors=True)
            _shutil.copytree(appdata_geom, dst_geom)
        _LOG.info("Geometry prepared via %s → %s", mode, dst_geom)

        # Copy OSIM and MOT into work_dir (they commonly use relative 'Geometry/')
        osim_path = Path(args.osim).resolve() if args.osim else None
        mot_path = Path(args.mot).resolve() if args.mot else None
        if osim_path:
            osim_dest = work_dir / osim_path.name
            shutil.copy2(osim_path, osim_dest)
            osim_path = osim_dest
        if mot_path:
            mot_dest = work_dir / mot_path.name
            shutil.copy2(mot_path, mot_dest)
            mot_path = mot_dest

        # Optionally smooth the MOT file in-place
        if args.smooth and mot_path:
            smoothed_path = work_dir / f"{mot_path.stem}_smooth.mot"
            smooth_mot_file(mot_path, smoothed_path, cutoff_hz=args.cutoff)
            mot_path = smoothed_path

        # Launch viewer
        display_model_in_viewer(
            osim=str(osim_path) if osim_path else None,
            mot=str(mot_path) if mot_path else None,
            fps=args.fps,
            color_parts=args.color_parts,
            color_markers=args.color_markers,
            mocap=args.mocap,
            joints=args.joints,
            video=args.video,
            calib=args.calib,
            sync_to_mot=not args.no_sync,
            frames_out_dir=frames_dir,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
