# OpenSim Viewer

A cross-platform tool for visualizing biomechanical models and motion data from OpenSim with optional synchronized video overlays. Built using [`aitviewer`](https://eth-ait.github.io/aitviewer/), it includes both a command-line interface (CLI) and a PyQt-based GUI.

![Screenshot](screenshot.png)

## Features

- Load `.osim` + `.mot`, optional `.c3d` markers
- Optional video billboard under calibrated camera (TOML)
- CLI (`osim-viewer`) and GUI (`osim-viewer-gui`)
- Buildable as standalone binaries for Windows/macOS/Linux via PyInstaller
- Docker image for headless X11-based Linux usage

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
  --osim /path/to/model.osim \
  --mot /path/to/motion.mot \
  --video /path/to/video.mp4 \
  --calib /path/to/calibration.toml \
  --fps 50 \
  --color_parts \
  --joints \
  --smooth
```

Notes:
- `--calib` is optional. If a video is provided without calibration, the video overlay is skipped.
- A fresh session directory is created under the OS cache dir each run and removed on exit.
- Use `--keep-session` to inspect extracted frames and copied files.
- Use `--smooth` to reduce jitter in marker positions.

Run `osim-viewer -h` for all options.

## GUI

```bash
osim-viewer-gui
```

Use the GUI to browse and select input files, then launch the viewer. The GUI spawns the CLI process and displays log output in real time.

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
