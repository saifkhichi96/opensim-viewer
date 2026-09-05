"""Streaming video export through the system FFmpeg, without scikit-video."""

import copy
import math
import os
import shutil
import subprocess
import tempfile
from contextlib import ExitStack

import numpy as np
from PIL import Image

from osim_viewer._rendering.scene.camera import ViewerCamera
from osim_viewer._rendering.utils.utils import get_video_paths, video_to_gif


class VideoWriter:
    """Pipe RGB/RGBA frames to FFmpeg and report encoder failures."""

    def __init__(self, path, fps, quality="medium", transparent=False):
        self.executable = shutil.which("ffmpeg")
        if not self.executable:
            raise RuntimeError(
                "Video export requires FFmpeg on PATH. Install FFmpeg and restart the viewer."
            )
        if transparent and not str(path).endswith(".webm"):
            raise ValueError("Transparent video requires WebM output.")
        self.path, self.fps = str(path), fps
        self.quality, self.transparent = quality, transparent
        self.process = None
        self.errors = tempfile.TemporaryFile()
        self.shape = None

    def write(self, image):
        """Encode one frame, starting the encoder on the first image."""
        frame = np.asarray(image.convert("RGBA" if self.transparent else "RGB"))
        if self.process is None:
            self.shape = frame.shape
            height, width = frame.shape[:2]
            codec = (
                ["-c:v", "libvpx-vp9", "-b:v", "0"]
                if self.path.endswith(".webm")
                else ["-c:v", "libx264", "-preset", "slow"]
            )
            args = [
                self.executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba" if self.transparent else "rgb24",
                "-s",
                f"{width}x{height}",
                "-r",
                str(self.fps),
                "-i",
                "pipe:0",
                "-an",
                *codec,
                "-crf",
                str({"high": 23, "medium": 28, "low": 33}[self.quality]),
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-pix_fmt",
                "yuva420p" if self.transparent else "yuv420p",
                self.path,
            ]
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self.errors,
            )
        if frame.shape != self.shape:
            raise ValueError("Export frame dimensions changed during encoding.")
        try:
            self.process.stdin.write(frame.tobytes())
        except BrokenPipeError:
            self.process.wait()
            raise RuntimeError(self.error_message()) from None

    def error_message(self):
        """Read a bounded tail of encoder diagnostics."""
        self.errors.seek(0, os.SEEK_END)
        self.errors.seek(max(0, self.errors.tell() - 8192))
        return "FFmpeg export failed: " + self.errors.read().decode(errors="replace")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.process:
                try:
                    self.process.stdin.close()
                except BrokenPipeError:
                    pass
                result = self.process.wait()
                if result and exc_type is None:
                    raise RuntimeError(self.error_message())
        finally:
            self.errors.close()


def export_video(
    viewer,
    output_path,
    frame_dir=None,
    animation=True,
    animation_range=None,
    duration=10.0,
    frame=None,
    output_fps=60.0,
    rotate_camera=False,
    rotation_degrees=360.0,
    scale_factor=None,
    transparent=False,
    quality="medium",
    ensure_no_overwrite=True,
):
    """Export sampled scene frames and restore viewer state even on failure."""
    if not math.isfinite(output_fps) or output_fps <= 0:
        raise ValueError("Output FPS must be positive and finite.")
    if scale_factor is not None and (
        not math.isfinite(scale_factor) or scale_factor <= 0
    ):
        raise ValueError("Export scale must be positive and finite.")
    if quality not in ("high", "medium", "low"):
        raise ValueError("Unknown video quality.")
    if output_path is None and frame_dir is None:
        raise ValueError("Choose a video or frame output path.")
    if rotate_camera and not isinstance(viewer.scene.camera, ViewerCamera):
        raise ValueError("Camera rotation requires the interactive viewer camera.")
    first, last = (
        animation_range
        if animation_range is not None
        else (0, viewer.scene.n_frames - 1)
    )
    if animation:
        if not 0 <= first <= last < viewer.scene.n_frames:
            raise ValueError("Animation range is outside the scene.")
        if not math.isfinite(viewer.playback_fps) or viewer.playback_fps <= 0:
            raise ValueError("Playback FPS must be positive and finite.")
        duration = (last - first + 1) / viewer.playback_fps
    elif frame is not None and not 0 <= frame < viewer.scene.n_frames:
        raise ValueError("Frame is outside the scene.")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Export duration must be positive and finite.")
    count = max(1, math.ceil(duration * output_fps))
    if frame_dir is not None:
        os.makedirs(frame_dir, exist_ok=True)
        frame_dir = tempfile.mkdtemp(prefix="frames-", dir=frame_dir)
    saved = viewer.scene.camera, viewer.scene.current_frame_id, viewer.run_animations
    try:
        with ExitStack() as stack:
            writer = None
            if output_path is not None:
                path_video, path_gif, is_gif = get_video_paths(
                    str(output_path), ensure_no_overwrite
                )
                writer = stack.enter_context(
                    VideoWriter(path_video, output_fps, quality, transparent)
                )
            viewer.run_animations = False
            if rotate_camera:
                viewer.scene.camera = copy.deepcopy(saved[0])
            for index in range(count):
                viewer.scene.current_frame_id = (
                    min(last, first + int(index * viewer.playback_fps / output_fps))
                    if animation
                    else (saved[1] if frame is None else frame)
                )
                if rotate_camera and index:
                    viewer.scene.camera.rotate_azimuth(
                        np.radians(rotation_degrees) / count
                    )
                viewer.render(
                    index / output_fps,
                    1 / output_fps,
                    export=True,
                    transparent_background=transparent,
                )
                image = viewer.get_current_frame_as_image(alpha=transparent)
                if scale_factor is not None:
                    image = image.resize(
                        (
                            max(1, int(image.width * scale_factor)),
                            max(1, int(image.height * scale_factor)),
                        ),
                        Image.Resampling.LANCZOS,
                    )
                if frame_dir is not None:
                    image.save(os.path.join(frame_dir, f"frame_{index:06d}.png"))
                if writer:
                    writer.write(image)
        if output_path is not None:
            if is_gif:
                video_to_gif(path_video, path_gif, remove=True)
            print(f"Video saved to {path_gif if is_gif else path_video}")
        else:
            print(f"Frames saved to {frame_dir}")
    finally:
        viewer.scene.camera, viewer.scene.current_frame_id, viewer.run_animations = (
            saved
        )
        viewer._last_frame_rendered_at = viewer.timer.time
