"""Local lens model and video-input contracts; OpenCV is an optional oracle."""

import numpy as np
import pytest
from PIL import Image

from osim_viewer._rendering.utils.media import (
    extract_video_frames,
    undistort,
    undistortion_map,
)
from osim_viewer._rendering.utils.video import VideoWriter

K = np.array([[90.0, 0, 40], [0, 95, 30], [0, 0, 1]])


@pytest.mark.parametrize("count", [4, 5, 8, 12, 14])
def test_opencv_lens_parity(count):
    cv2 = pytest.importorskip("cv2")
    d = np.array(
        [
            0.15,
            -0.08,
            0.003,
            -0.005,
            0.03,
            0.01,
            -0.02,
            0.004,
            0.001,
            -0.002,
            0.003,
            -0.001,
            0.04,
            -0.03,
        ]
    )[:count]
    y, x = undistortion_map((60, 80), K, d)
    ox, oy = cv2.initUndistortRectifyMap(K, d, None, K, (80, 60), cv2.CV_32FC1)
    np.testing.assert_allclose(x, ox, atol=4e-6, rtol=0)
    np.testing.assert_allclose(y, oy, atol=4e-6, rtol=0)
    image = np.random.default_rng(2).integers(0, 256, (60, 80, 3), dtype=np.uint8)
    actual = undistort(image, K, d)
    expected = cv2.undistort(image, K, d)
    error = np.abs(actual.astype(float) - expected.astype(float))
    assert error.max() <= 1


def test_identity_and_invalid_lens():
    image = np.random.default_rng(2).integers(0, 256, (60, 80, 4), dtype=np.uint8)
    np.testing.assert_array_equal(image, undistort(image, K, np.zeros(5)))
    with pytest.raises(ValueError):
        undistort(image, K, [0, 0])


def test_frame_selection_limits_and_repeated_output(tmp_path):
    path = tmp_path / "with spaces.mp4"
    with VideoWriter(path, 30) as writer:
        for n in range(6):
            writer.write(Image.new("RGB", (32, 24), (n * 30, 0, 0)))
    frames, w, h, fps = extract_video_frames(path, 15, tmp_path / "out", 2)
    assert (len(frames), w, h, fps) == (2, 32, 24, 15)
    with Image.open(frames[1]) as image:
        assert abs(np.asarray(image)[12, 16, 0].item() - 60) < 8
    again, *_ = extract_video_frames(path, None, tmp_path / "out", 1)
    assert len(again) == 1 and again[0] != frames[0]
