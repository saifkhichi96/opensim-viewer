"""Video decoding through FFmpeg and OpenCV-format lens models in NumPy."""

import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates


def extract_video_frames(video_path, fps_out, out_dir, limit_n=None):
    """Extract every nth decoded frame, preserving the existing rounded FPS API."""
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(
                f"Video input requires {tool} on PATH. Install FFmpeg and restart."
            )
    if not Path(video_path).is_file():
        raise FileNotFoundError(video_path)
    if limit_n is not None and limit_n <= 0:
        raise ValueError("Frame limit must be positive.")
    if fps_out is not None and (not math.isfinite(fps_out) or fps_out <= 0):
        raise ValueError("Output FPS must be positive and finite.")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(Path(video_path).resolve()),
        ],
        capture_output=True,
        check=True,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if not streams:
        raise ValueError("Input contains no video stream.")
    src_fps = 30.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            candidate = float(Fraction(streams[0][key]))
            if candidate > 0 and math.isfinite(candidate):
                src_fps = candidate
                break
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    stride = max(round(src_fps / fps_out), 1) if fps_out else 1
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="decoded-", dir=out_dir))
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(Path(video_path).resolve()),
        "-map",
        "0:v:0",
        "-vf",
        f"select=not(mod(n\\,{stride}))",
        "-vsync",
        "0",
        "-q:v",
        "2",
        "-start_number",
        "0",
    ]
    if limit_n is not None:
        command += ["-frames:v", str(limit_n)]
    command += [str(target / "frame_%06d.jpg")]
    try:
        with tempfile.TemporaryFile() as errors:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=errors)
            if result.returncode:
                errors.seek(0)
                raise RuntimeError(
                    "FFmpeg decoding failed: "
                    + errors.read()[-8192:].decode(errors="replace")
                )
        frames = sorted(target.glob("frame_*.jpg"))
        if not frames:
            raise RuntimeError("No frames extracted from video.")
        with Image.open(frames[0]) as image:
            width, height = image.size
        return [str(p) for p in frames], width, height, round(src_fps / stride)
    except Exception:
        shutil.rmtree(target)
        raise


def undistortion_map(shape, matrix, coefficients):
    """Map ideal pixels to distorted pixels for 4/5/8/12/14-coefficient lenses.

    Uses the documented OpenCV radial, tangential, thin-prism and tilted-sensor
    model, with the same input/output intrinsic matrix and no rectification.
    """
    k = np.asarray(matrix, dtype=float)
    d = np.asarray(coefficients, dtype=float).ravel()
    if k.shape != (3, 3) or not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0:
        raise ValueError("Invalid camera intrinsic matrix.")
    if d.size not in (4, 5, 8, 12, 14) or not np.isfinite(d).all():
        raise ValueError("Expected 4, 5, 8, 12 or 14 finite distortion coefficients.")
    d = np.pad(d, (0, 14 - d.size))
    yy, xx = np.indices(shape[:2], dtype=float)
    x, y = (xx - k[0, 2]) / k[0, 0], (yy - k[1, 2]) / k[1, 1]
    r2 = x * x + y * y
    radial = (1 + d[0] * r2 + d[1] * r2**2 + d[4] * r2**3) / (
        1 + d[5] * r2 + d[6] * r2**2 + d[7] * r2**3
    )
    xd = (
        x * radial
        + 2 * d[2] * x * y
        + d[3] * (r2 + 2 * x * x)
        + d[8] * r2
        + d[9] * r2**2
    )
    yd = (
        y * radial
        + d[2] * (r2 + 2 * y * y)
        + 2 * d[3] * x * y
        + d[10] * r2
        + d[11] * r2**2
    )
    if d[12] or d[13]:
        cx, sx, cy, sy = np.cos(d[12]), np.sin(d[12]), np.cos(d[13]), np.sin(d[13])
        rotation = np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]]) @ np.array(
            [[1, 0, 0], [0, cx, sx], [0, -sx, cx]]
        )
        projection = np.array(
            [
                [rotation[2, 2], 0, -rotation[0, 2]],
                [0, rotation[2, 2], -rotation[1, 2]],
                [0, 0, 1],
            ]
        )
        tilted = np.einsum(
            "ij,jhw->ihw", projection @ rotation, np.stack((xd, yd, np.ones_like(xd)))
        )
        xd, yd = tilted[0] / tilted[2], tilted[1] / tilted[2]
    return yd * k[1, 1] + k[1, 2], xd * k[0, 0] + k[0, 2]


def undistort(image, matrix, coefficients):
    """Bilinearly sample a lens-corrected image with zero-filled borders."""
    image = np.asarray(image)
    coords = undistortion_map(image.shape, matrix, coefficients)
    # OpenCV's linear sampler quantizes coordinates to 1/32 pixel.
    coords = np.round(np.asarray(coords) * 32) / 32

    def sample(channel):
        return map_coordinates(
            channel.astype(float),
            coords,
            order=1,
            mode="grid-constant",
            cval=0,
            prefilter=False,
        )

    result = (
        sample(image)
        if image.ndim == 2
        else np.stack([sample(image[..., c]) for c in range(image.shape[2])], axis=-1)
    )
    if np.issubdtype(image.dtype, np.integer):
        limits = np.iinfo(image.dtype)
        result = np.clip(np.floor(result + 0.5), limits.min, limits.max)
    return result.astype(image.dtype)
