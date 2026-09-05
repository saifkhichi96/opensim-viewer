"""Local replacements and optional VTK differential checks."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.signal import butter, filtfilt

from osim_viewer._rendering.utils.vtp import read_vtp, triangulate
from osim_viewer.utils import smooth_mot_file


@pytest.mark.parametrize("mode", ["ascii", "binary", "appended", "raw"])
@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("wide", [False, True])
def test_vtk_differential(tmp_path, mode, compressed, wide):
    vtk = pytest.importorskip("vtk")
    points = vtk.vtkPoints()
    for point in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (1, 1, 0), (0, 2, 0)]:
        points.InsertNextPoint(*point)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(5)
    for index in range(5):
        cells.InsertCellPoint(index)
    mesh = vtk.vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetInputData(mesh)
    writer.SetFileName(str(tmp_path / "mesh.vtp"))
    if mode == "ascii":
        writer.SetDataModeToAscii()
    elif mode == "binary":
        writer.SetDataModeToBinary()
    else:
        writer.SetDataModeToAppended()
        writer.SetEncodeAppendedData(mode != "raw")
    if not compressed:
        writer.SetCompressorTypeToNone()
    if wide:
        writer.SetHeaderTypeToUInt64()
        writer.SetByteOrderToBigEndian()
    assert writer.Write()
    vertices, faces = read_vtp(tmp_path / "mesh.vtp")
    assert vertices.shape == (5, 3) and faces.shape == (3, 3)
    triangles = vertices[faces]
    area = (
        np.linalg.norm(
            np.cross(
                triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            ),
            axis=1,
        ).sum()
        / 2
    )
    assert area == pytest.approx(3)


def test_all_bundled_vtp():
    files = list((Path(__file__).parents[1] / "assets/Geometry").glob("*.vtp"))
    assert files
    for path in files:
        try:
            points, faces = read_vtp(path)
        except ValueError as exc:
            assert "Degenerate or non-simple" in str(exc), path
            assert path.name in {"hat_spine.vtp", "hat_skull.vtp"}, path
            # Legacy bundled surfaces retain the VTK-generated reference mesh.
            import trimesh

            mesh = trimesh.load(str(path) + ".ply", process=False)
            points, faces = mesh.vertices, mesh.faces
        assert np.isfinite(points).all(), path
        assert faces.min() >= 0 and faces.max() < len(points), path


def test_invalid_polygon():
    with pytest.raises(ValueError):
        triangulate(np.zeros((4, 3)), [0, 1, 2, 3])


def test_truncated_binary_payload():
    from osim_viewer._rendering.utils.vtp import payload

    with pytest.raises(ValueError):
        payload(b"\x00", np.dtype("<u4"), False)
    with pytest.raises(ValueError):
        payload(np.array([100], dtype="<u4").tobytes(), np.dtype("<u4"), False)


def test_existing_geometry_upgrade_preserves_custom_meshes(tmp_path):
    from osim_viewer.resources import refresh_preconverted_geometry

    source, target = tmp_path / "package", tmp_path / "user"
    source.mkdir()
    target.mkdir()
    for name in ("stock", "custom", "converted"):
        (source / (name + ".vtp")).write_text("original")
        (source / (name + ".vtp.ply")).write_text("reference")
        (target / (name + ".vtp")).write_text("original")
    (target / "custom.vtp").write_text("user change")
    (target / "converted.vtp.ply").write_text("user conversion")
    refresh_preconverted_geometry(source, target)
    assert (target / "stock.vtp.ply").read_text() == "reference"
    assert not (target / "custom.vtp.ply").exists()
    assert (target / "converted.vtp.ply").read_text() == "user conversion"


def test_numpy_motion_smoothing(tmp_path):
    t = np.arange(100) / 100
    data = np.column_stack([t, np.sin(t * 8) + 0.1 * np.cos(t * 100), np.ones(100)])
    source, out = tmp_path / "input.mot", tmp_path / "out.mot"
    with source.open("w") as file:
        file.write("name test\nendheader\n\ntime angle constant\n")
        np.savetxt(file, data)
    smooth_mot_file(source, out)
    result = np.loadtxt(out, skiprows=3)
    b, a = butter(3, 6 / 50, btype="low")
    np.testing.assert_allclose(result[:, 1], filtfilt(b, a, data[:, 1]), atol=5e-9)
    np.testing.assert_allclose(result[:, [0, 2]], data[:, [0, 2]], atol=5e-9)
    assert out.read_text().startswith("name test\nendheader\n")


def test_camera_json_roundtrip(tmp_path, monkeypatch):
    from osim_viewer._rendering.scene import camera

    monkeypatch.setattr(camera, "C", SimpleNamespace(export_dir=str(tmp_path)))
    state = dict(
        position=np.array([1.0, 2.0, 3.0]),
        target=np.zeros(3),
        up=np.array([0.0, 1.0, 0.0]),
        ZOOM_FACTOR=1.0,
        ROT_FACTOR=2.0,
        PAN_FACTOR=3.0,
        near=0.1,
        far=100.0,
    )
    source = SimpleNamespace(**state)
    camera.ViewerCamera.save_cam(source)
    dest = SimpleNamespace()
    camera.ViewerCamera.load_cam(dest)
    np.testing.assert_array_equal(dest.position, source.position)
    assert dest.far == 100
    path = tmp_path / "camera_params/cam_params.json"
    value = json.loads(path.read_text())
    value["camera"]["near"] = 200
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        camera.ViewerCamera.load_cam(dest)


def test_config_precedence(tmp_path, monkeypatch):
    from osim_viewer._rendering.configuration import Configuration

    monkeypatch.chdir(tmp_path)
    env = tmp_path / "custom.toml"
    env.write_text("window_width = 800\nwindow_height = 400\n")
    (tmp_path / "osim-viewer.toml").write_text("window_width = 900\n")
    monkeypatch.setenv("OSIM_VIEWER_CONFIG", str(env))
    monkeypatch.setattr(Configuration, "instance", None)
    config = Configuration()
    assert config.window_width == 900 and config.window_height == 400
    with pytest.raises(ValueError):
        config.update_conf({"nonsense": 1})
