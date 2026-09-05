"""Headless contracts for the self-contained OpenSim renderer."""

import ast
import importlib.util
from pathlib import Path

import numpy as np

from osim_viewer import _rendering
from osim_viewer._rendering.renderables.markers import Markers
from osim_viewer._rendering.renderables.meshes import Meshes
from osim_viewer._rendering.scene.camera import OpenCVCamera
from osim_viewer._rendering.utils.so3 import euler2rot_numpy, rot2euler_numpy
from osim_viewer.core import extract_video_frames, load_calibration


def test_no_external_viewer_or_unused_model_imports():
    assert importlib.util.find_spec("aitviewer") is None
    root = Path(_rendering.__file__).parent
    for file in root.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not {n.split(".")[0] for n in names} & {
                "aitviewer",
                "smplx",
                "roma",
                "torch",
                "pxr",
                "websockets",
            }, file
    assert (root / "viewer.toml").is_file()
    assert (root / "resources/fonts/Custom.ttf").is_file()
    assert (root / "shaders/lit_with_edges.glsl").is_file()
    assert (root / "LICENSE").is_file()


def test_mesh_and_marker_animation_without_gl():
    vertices = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    vertices = np.concatenate([vertices, vertices + 1])
    mesh = Meshes(vertices, np.array([[0, 1, 2]]))
    assert mesh.n_frames == 2
    mesh.current_frame_id = 1
    np.testing.assert_allclose(mesh.current_vertices, vertices[1])
    markers = Markers(vertices, markers_labels=["a", "b", "c"])
    assert markers.n_frames == 2
    markers.current_frame_id = 1


def test_rotation_roundtrip():
    angles = np.array([[0.1, 0.2, -0.3], [0.2, -0.2, 0.4]])
    np.testing.assert_allclose(rot2euler_numpy(euler2rot_numpy(angles)), angles)


def test_calibrated_camera(tmp_path):
    file = tmp_path / "camera.toml"
    file.write_text(
        "[clip]\nmatrix=[[500,0,320],[0,500,180],[0,0,1]]\n"
        "distortions=[0,0,0,0]\nrotation=[0,0,0]\n"
        "translation=[0,0,0]\nsize=[640,360]\n"
    )
    calibration = load_calibration(file, "clip")
    rt = np.concatenate([calibration["R"], calibration["T"][:, None]], axis=1)
    camera = OpenCVCamera(calibration["K"], rt, 640, 360)
    assert camera.n_frames == 1


def test_video_extraction(tmp_path):
    import cv2

    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (64, 48))
    assert writer.isOpened()
    for value in range(6):
        writer.write(np.full((48, 64, 3), value * 20, np.uint8))
    writer.release()
    frames, width, height, fps = extract_video_frames(path, 15, tmp_path / "frames")
    assert (len(frames), width, height, fps) == (3, 64, 48, 15)
