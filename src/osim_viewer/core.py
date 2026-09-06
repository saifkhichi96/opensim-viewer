from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import toml
from scipy.spatial.transform import Rotation

from osim_viewer._rendering.renderables.billboard import Billboard
from osim_viewer._rendering.renderables.markers import Markers
from osim_viewer._rendering.renderables.osim import OSIMSequence
from osim_viewer._rendering.scene.camera import OpenCVCamera
from osim_viewer._rendering.utils.vtp_to_ply import convert_meshes
from osim_viewer._rendering.viewer import Viewer

_LOG = logging.getLogger(__name__)


def load_calibration(toml_path: str | Path, camera_name: str) -> dict:
    """
    Load camera intrinsics/extrinsics from TOML.

    Structure expected:
      [<camera_name>]
      matrix = [[...],[...],[...]]
      distortions = [k1,k2,p1,p2] or [k1,k2,p1,p2,k3,k4,k5,k6]
      rotation = [rx, ry, rz]  # Rodrigues
      translation = [tx, ty, tz]
      size = [width, height]
    """
    toml_path = str(toml_path)
    data = toml.load(toml_path)
    if camera_name not in data:
        raise KeyError(
            f"Camera '{camera_name}' not found in calibration file '{toml_path}'."
        )

    c = data[camera_name]
    K = np.asarray(c["matrix"], dtype=float)
    dist = np.asarray(c["distortions"], dtype=float).reshape(-1)
    rvec = np.asarray(c["rotation"], dtype=float).reshape(3)
    tvec = np.asarray(c["translation"], dtype=float).reshape(3)
    R = Rotation.from_rotvec(rvec).as_matrix()

    size = tuple(int(x) for x in c["size"])
    if K.shape != (3, 3):
        raise ValueError(f"K must be 3x3; got {K.shape}")
    if R.shape != (3, 3):
        raise ValueError(f"R must be 3x3; got {R.shape}")
    if len(size) != 2:
        raise ValueError(f"size must be [w,h]; got {size}")

    return {"K": K, "dist": dist, "R": R, "T": tvec, "size": size}


def extract_video_frames(
    video_path: str | Path,
    fps_out: Optional[int],
    out_dir: Path,
    limit_n: Optional[int] = None,
) -> Tuple[List[str], int, int, int]:
    """
    Extract frames to out_dir. Returns (frame_paths, cols, rows, fps_used).
    If fps_out is set, decimate frames to approximately match fps_out (assumes constant fps).
    """
    from osim_viewer._rendering.utils.media import extract_video_frames as decode

    return decode(video_path, fps_out, out_dir, limit_n)


def display_model_in_viewer(
    *,
    osim: Optional[str] = None,
    mot: Optional[str] = None,
    fps: Optional[int] = None,
    color_parts: bool = False,
    color_markers: bool = False,
    mocap: Optional[str] = None,
    joints: bool = False,
    video: Optional[str] = None,
    calib: Optional[str] = None,
    sync_to_mot: bool = True,
    frames_out_dir: Optional[Path] = None,
    viewer: Optional[Viewer] = None,
) -> None:
    """
    Load an OpenSim model and motion, optionally overlay a video using a calibrated camera.

    Notes
    -----
    - `osim` and its sibling `Geometry` directory are expected to be prepared by the caller
      (CLI/GUI wires this up via a session working directory with a symlinked Geometry).
    - If `video` is provided without `calib`, no billboard or camera is added (by design).
    - `frames_out_dir` is managed by the session layer to avoid cache growth.
    """

    if osim is not None:
        # Ensure Geometry exists and contains some .ply (convert in-place if needed)
        osim_dir = Path(osim).resolve().parent
        geom_dir = osim_dir / "Geometry"
        if not geom_dir.exists():
            raise FileNotFoundError(
                f"Missing Geometry folder next to OSIM at: {geom_dir}\n"
                "The CLI/GUI normally symlinks this from AppData before calling core."
            )
        if any(
            p.suffix.lower() in (".vtp", ".obj") and not Path(str(p) + ".ply").exists()
            for p in geom_dir.iterdir()
        ):
            _LOG.info("Converting missing PLY geometry locally...")
            convert_meshes(str(geom_dir), str(geom_dir))

    if mot is None:
        osim_seq = OSIMSequence.a_pose(
            osim,
            name="OpenSim template",
            show_joint_angles=joints,
            color_skeleton_per_part=color_parts,
            color_markers_per_part=color_markers,
        )
        mot_fps = fps or 30
    else:
        osim_seq = OSIMSequence.from_files(
            osim_path=osim,
            mot_file=mot,
            show_joint_angles=joints,
            color_skeleton_per_part=color_parts,
            color_markers_per_part=color_markers,
            fps_out=fps,
        )
        mot_fps = getattr(osim_seq, "fps", None) or fps or 30

    v = viewer if viewer is not None else Viewer(title="OpenSim Viewer")
    v.scene.add(osim_seq)

    # Optional mocap markers
    if mocap is not None:
        assert mocap.endswith(".c3d"), "Mocap file must be in .c3d format."
        marker_seq = Markers.from_c3d(mocap, fps_out=mot_fps, color=[0, 255, 0, 255])
        v.scene.add(marker_seq)

    # Video + calibrated camera overlay (optional, only if both provided)
    if video is not None and calib is not None:
        if frames_out_dir is None:
            raise ValueError("frames_out_dir must be provided by the session layer.")
        target_fps = mot_fps if sync_to_mot else (fps or None)
        frame_paths, cols, rows, vid_fps_used = extract_video_frames(
            video_path=video, fps_out=target_fps, out_dir=frames_out_dir
        )

        camera_name = os.path.splitext(os.path.basename(video))[0]
        C = load_calibration(calib, camera_name)
        K, R, T = C["K"], C["R"], C["T"]
        cols, rows = C["size"]  # enforce calibrated size

        # Compose camera extrinsics 4x4
        cam_extrinsics = np.eye(4)
        cam_extrinsics[:3, :3] = R
        cam_extrinsics[:3, 3] = T

        # Coordinate-system transforms (as in your script)
        transform1 = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
        transform2 = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1]])
        cam_extrinsics = cam_extrinsics @ transform1 @ transform2

        cv_cam = OpenCVCamera(
            K, cam_extrinsics[:3], cols, rows, viewer=v, dist_coeffs=C["dist"]
        )
        pc = Billboard.from_camera_and_distance(cv_cam, 50.0, cols, rows, frame_paths)
        v.scene.add(pc)
        v.set_temp_camera(cv_cam)
        v.scene.floor.enabled = False
        v.scene.origin.enabled = False
        v.shadows_enabled = False

        v.playback_fps = mot_fps if sync_to_mot else vid_fps_used
    else:
        if video is not None and calib is None:
            _LOG.warning(
                "Video provided without calibration; skipping billboard/camera overlay."
            )
        v.lock_to_node(osim_seq, (5, 2, 0), smooth_sigma=5.0)
        v.playback_fps = mot_fps

    v.run_animations = True
    if viewer is None:
        v.run()
