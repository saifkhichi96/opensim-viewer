# OpenSim Viewer runtime

The private `osim_viewer._rendering` package supports OpenSim visualization, not a general-purpose public rendering API.

## Workflows

- OpenSim models and motion through NimblePhysics; animated meshes, markers, joint axes and per-part colors.
- Optional C3D markers, calibrated cameras and synchronized video billboards.
- Camera following, orbit/pan/zoom, timeline, scene tree and selection.
- Lighting, floor, shadows, screenshots, frame sequences and video export.
- CLI and integrated ImGui setup in a Pyglet window.

Setup provides file browsing, input paths, options, smoothing and bounded application logs. Loading runs on the graphics thread and can temporarily pause interaction. Native library diagnostics appear in the terminal. Loading errors leave setup available to retry.

## Geometry and motion

Bundled Geometry includes 108 VTP surfaces with precomputed PLY companions. Missing companions are copied to app data only when the original VTP matches the bundled asset; custom geometry is not overwritten.

The local VTP reader supports ASCII, inline base64, raw/base64 appended arrays, zlib blocks, little/big endian, UInt32/UInt64 headers, multiple pieces, polygons and triangle strips. It consumes positions and topology only. Unsupported compressors and malformed/non-simple polygons fail explicitly. The bundled `hat_spine.vtp` and `hat_skull.vtp` use precomputed partial surfaces because their source polygons are not all valid. OBJ conversion uses Trimesh.

Motion smoothing uses NumPy tables and SciPy filtering, preserving headers, column order, time and constant columns.

## Settings and sessions

Settings are flat TOML: packaged `_rendering/viewer.toml` defaults, then `OSIM_VIEWER_CONFIG` (a file or directory containing `viewer.toml`), then working-directory `osim-viewer.toml`. Unknown keys are rejected.

UI layout and mouse input use logical coordinates; scene rendering uses full framebuffer resolution. DejaVu Sans text is rasterized at display density. `ui_scale = 1.0` is the default; use 1.25 or 1.5 for larger controls. Accepted range: 0.5–3. Restart after editing settings.

Camera settings use validated, versioned JSON in `camera_params/cam_params.json`. Unique session cache directories remain until their scene is replaced or the viewer closes. `--keep-session` preserves them for inspection.

## Dependencies and export

NimblePhysics depends on PyTorch. Rendering uses NumPy/SciPy, ModernGL, Pyglet, ImGui, Trimesh and Pillow. No separate AITViewer, Qt, OpenCV, VTK/PyVista, Pandas, OmegaConf or Joblib package is required.

Video input requires FFmpeg and FFprobe on PATH. Frame extraction selects every
nth decoded frame and reports rounded playback FPS; it is not a timestamp-aware
variable-frame-rate synchronization pipeline. Image loading uses Pillow, and
rotation-vector conversion uses SciPy. Lens correction supports OpenCV-format
4/5/8/12/14-coefficient models (radial, tangential, rational, thin-prism and sensor
tilt), including zero-filled image borders. Calibration distortion coefficients
are applied by the video billboard. Local sampling is tested against OpenCV to
within one intensity level; optional oracle tests require OpenCV only for testing.

Video export pipes RGB/RGBA frames to system FFmpeg, which must be on `PATH`. MP4 uses H.264; WebM uses VP9 and supports transparent output. GIF conversion also uses FFmpeg. PNG-only export requires no encoder. FFmpeg is installed in the Docker image but is not bundled in the Python wheel.

Frames are sampled at the requested output rate. Camera, frame and animation state are restored on success or failure. Encoder errors appear in the export dialog. GIF conversion removes its intermediate video only after success.

## Licensing

The rendering foundation derives from AITViewer and its OpenSim extension at commit `d56964ab5b9665acee7928ae49f29f7d2c08362f`. ETH Zurich and MPI copyright notices and MIT terms are retained in `_rendering/LICENSE` and source headers. DejaVu Sans terms are in `resources/fonts/LICENSE_DEJAVU`.

## Validation

Local Python 3.11 tests cover resources/imports, meshes, markers, rotations, calibrated cameras, video frame extraction, geometry, filtering, configuration, camera persistence, sessions, UI coordinates and video export. Optional VTK differential tests run when VTK is installed as a test oracle.

Native macOS checks cover model loading, setup/browser rendering, resizing, synthetic input, reload/error recovery, PNG export and a decoded three-frame MP4. Screenshots were inspected. MP4/WebM/GIF encoding and decoding are tested, including odd dimensions, sampling and missing/failed encoders. Wheels contain Geometry, shaders, fonts, settings and licence notices.

Still requiring validation: full manual interaction, physical mixed-DPI monitor changes, Windows/Linux, fullscreen, frozen executables, Docker execution, long recordings, transparent WebM alpha fidelity, real C3D captures and calibrated video alignment. Native model-compatibility and depth-texture warnings occur with the local demo; these checks do not establish full cross-platform parity.
