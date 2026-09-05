"""Qt-free setup, shared preparation and session lifetime contracts."""

from contextlib import ExitStack
from pathlib import Path

import pytest

from osim_viewer import cli, session
from osim_viewer.gui import build_arguments


def test_setup_arguments(tmp_path):
    model = tmp_path / "model with spaces.osim"
    model.touch()
    args = build_arguments(
        {"osim": str(model)}, {"smooth": True, "no-symlink": True}, 50
    )
    assert args[:2] == ["--osim", str(model)]
    assert "--smooth" in args and "--no-symlink" in args
    assert args[args.index("--fps") + 1] == "50"


@pytest.mark.parametrize("paths,fps", [({}, 0), ({"osim": "/missing.osim"}, 0)])
def test_invalid_inputs(paths, fps):
    with pytest.raises(ValueError):
        build_arguments(paths, {}, fps)


def test_session_isolation_and_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "cache_root", lambda: tmp_path)
    with session.session_context() as first:
        with session.session_context(keep=True) as second:
            assert first != second and first.is_dir()
        assert second.is_dir()
    assert not first.exists() and second.is_dir()


def test_shared_preparation_copies_and_retains_until_viewer_closes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session, "cache_root", lambda: tmp_path / "cache")
    geometry = tmp_path / "Geometry"
    geometry.mkdir()
    (geometry / "test.ply").touch()
    model = tmp_path / "model.osim"
    model.touch()
    monkeypatch.setattr(cli, "ensure_appdata_geometry", lambda: geometry)
    calls = []
    monkeypatch.setattr(
        cli, "display_model_in_viewer", lambda **kwargs: calls.append(kwargs)
    )
    viewer = object()
    with ExitStack() as sessions:
        cli.main(
            ["--osim", str(model), "--no-symlink"], viewer=viewer, sessions=sessions
        )
        prepared = Path(calls[0]["osim"])
        assert calls[0]["viewer"] is viewer
        assert prepared.is_file()
        assert (prepared.parent / "Geometry/test.ply").is_file()
        assert not (prepared.parent / "Geometry").is_symlink()
    assert not prepared.exists()
