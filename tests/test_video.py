"""Video encoding and deterministic sampling without a graphics context."""

import shutil
from types import SimpleNamespace

import cv2
import pytest
from PIL import Image

from osim_viewer._rendering.utils import video


def fake_viewer():
    frames = []
    viewer = SimpleNamespace(
        scene=SimpleNamespace(camera=object(), current_frame_id=2, n_frames=3),
        run_animations=True,
        playback_fps=30,
        timer=SimpleNamespace(time=7),
        get_current_frame_as_image=lambda **kw: Image.new("RGB", (33, 25), "red"),
    )
    viewer.render = lambda *a, **kw: frames.append(viewer.scene.current_frame_id)
    return viewer, frames


@pytest.mark.parametrize("extension", ["mp4", "webm", "gif"])
def test_real_encoding(tmp_path, extension):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    viewer, frames = fake_viewer()
    destination = tmp_path / f"output.{extension}"
    video.export_video(viewer, destination, output_fps=60, ensure_no_overwrite=False)
    assert frames == [0, 0, 1, 1, 2, 2]
    assert viewer.scene.current_frame_id == 2 and viewer.run_animations
    if extension == "gif":
        with Image.open(destination) as image:
            assert image.size == (34, 26)
    else:
        cap = cv2.VideoCapture(str(destination))
        count = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            assert image.shape[:2] == (26, 34)
            count += 1
        cap.release()
        assert count == 6


def test_single_frame_downsample_and_static_default(tmp_path):
    viewer, frames = fake_viewer()
    video.export_video(
        viewer, None, frame_dir=tmp_path, animation_range=(1, 1), output_fps=1
    )
    assert frames == [1]
    frames.clear()
    video.export_video(
        viewer, None, frame_dir=tmp_path, animation=False, duration=0.1, output_fps=10
    )
    assert frames == [2]


def test_failure_restores_state(tmp_path):
    viewer, _ = fake_viewer()
    camera = viewer.scene.camera

    def fail(*args, **kwargs):
        raise RuntimeError("render failed")

    viewer.render = fail
    with pytest.raises(RuntimeError, match="render failed"):
        video.export_video(viewer, None, frame_dir=tmp_path)
    assert viewer.scene.camera is camera
    assert viewer.scene.current_frame_id == 2 and viewer.run_animations
    assert viewer._last_frame_rendered_at == 7


def test_missing_encoder(monkeypatch, tmp_path):
    monkeypatch.setattr(video.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Install FFmpeg"):
        video.VideoWriter(tmp_path / "output.mp4", 30)


def test_encoder_failure(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    with (
        pytest.raises(RuntimeError, match="FFmpeg export failed"),
        video.VideoWriter(tmp_path / "missing" / "output.mp4", 30) as writer,
    ):
        writer.write(Image.new("RGB", (32, 24)))
