# OpenSim Viewer

OpenSim visualization with [aitviewer-skel](https://github.com/MarilynKeller/aitviewer-skel) overlays. Use a fast CLI or a minimal PyQt GUI, with meshes packaged in per-user AppData and safe, self-cleaning sessions.

## Features

- Load `.osim` + `.mot`, optional `.c3d` markers
- Optional video billboard under calibrated camera (TOML)
- Geometry meshes shipped in AppData and symlinked per run
- No cache bloat: session directory is replaced every launch
- CLI (`osim-viewer`) and GUI (`osim-viewer-gui`)
- Windows/macOS/Linux binaries via PyInstaller
- Docker image for Linux (X11)

## Install (dev)

```bash
python3.9 -m venv .venv && source .venv/bin/activate
pip install deps/aitviewer-1.13.0-py2.py3-none-any.whl
pip install -r requirements.txt
pip install -e .

pip install -r requirements-dev.txt
pre-commit install --install-hooks
```

## Usage

### CLI

```bash
osim-viewer \
  --osim /path/model.osim \
  --mot /path/motion.mot \
  --video /path/video.mp4 \
  --calib /path/calibration.toml \
  --fps 60 --color_parts --joints
```

Notes:
- `--calib` is optional. If a video is provided without calibration, the video overlay is skipped.
- A fresh session directory is created under the OS cache dir each run and removed on exit.
- Use `--keep-session` to inspect extracted frames and copied files.

Run `osim-viewer -h` for all options.

## GUI

```bash
osim-viewer-gui
```

Pick files and hit **Launch Viewer**. The GUI spawns the CLI and streams logs.

## Packaging

### PyInstaller (all platforms)

Install build deps, then:

```bash
pyinstaller -y packaging/pyinstaller-cli.spec
pyinstaller -y packaging/pyinstaller-gui.spec
```

Artifacts:
- `dist/osim-viewer` (CLI binary)
- `dist/osim-viewer-gui` (GUI app)

Ensure your `assets/Geometry/` contains the meshes you intend to ship; they are copied to per-user AppData on first run.

### Docker (Linux)

```bash
docker build -t osim-viewer:latest .
xhost +local:root
docker run --rm -it \
  -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v $PWD:/data osim-viewer:latest \
  --osim /data/model.osim --mot /data/motion.mot
```

## Calibration

The TOML calibration must have a section named after the video filename stem, with fields:

```toml
[my_video]
matrix = [[fx,0,cx],[0,fy,cy],[0,0,1]]
distortions = [k1,k2,p1,p2]   # or with extra terms
rotation = [rx, ry, rz]       # Rodrigues
translation = [tx, ty, tz]
size = [width, height]
```

The app will warn and skip overlay if `--video` is given without `--calib`.

## Python Support

- Python 3.9 (recommended). Other versions are not tested.
- Heavy deps (`nimblephysics`, `pyvista`) are required by `aitviewer-osim`.

## Acknowledgements

- [OpenSim](https://opensim.stanford.edu/) for biomechanics modeling
- [aitviewer-skel](https://github.com/MarilynKeller/aitviewer-skel) for 3D visualization

## License

MIT License. See [LICENSE](LICENSE).

Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.
