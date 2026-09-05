"""Single-window OpenSim setup and viewing, using Dear ImGui and Pyglet."""

from __future__ import annotations

import logging
import math
import sys
from collections import deque
from contextlib import ExitStack
from pathlib import Path

import imgui

from osim_viewer._rendering.viewer import Viewer
from osim_viewer.cli import main as run_session

FILE_FIELDS = {
    "osim": ("Model (.osim)", (".osim",)),
    "mot": ("Motion (.mot)", (".mot",)),
    "video": ("Video", (".mp4", ".avi", ".mov", ".mkv")),
    "calib": ("Calibration (.toml)", (".toml",)),
    "mocap": ("Markers (.c3d)", (".c3d",)),
}
FLAGS = {
    "color_parts": "Color skeleton parts",
    "color_markers": "Color markers by parent part",
    "joints": "Show joints",
    "no-sync": "Use video FPS (no sync)",
    "keep-session": "Keep session cache",
    "no-symlink": "Copy Geometry (no symlink)",
    "smooth": "Smooth motion",
}


def build_arguments(paths, flags, fps=0, cutoff=6.0):
    """Validate setup and produce shell-free CLI arguments."""
    if not paths.get("osim", "").strip():
        raise ValueError(
            "Select an OpenSim model first. Motion and other inputs are optional."
        )
    args = []
    for key in FILE_FIELDS:
        value = paths.get(key, "").strip()
        if value:
            path = Path(value).expanduser()
            if not path.is_file():
                raise ValueError(f"File does not exist: {path}")
            args.extend((f"--{key}", str(path.resolve())))
    if fps < 0 or fps > 240:
        raise ValueError("FPS must be 0 (automatic) or between 1 and 240.")
    if fps:
        args.extend(("--fps", str(fps)))
    if not math.isfinite(cutoff) or (flags.get("smooth") and cutoff <= 0):
        raise ValueError("Smoothing cutoff must be positive.")
    args.extend(("--cutoff", str(cutoff)))
    args.extend(f"--{key}" for key in FLAGS if flags.get(key))
    return args


class LogBuffer(logging.Handler):
    """Bounded application logs for the setup panel."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = deque(maxlen=2000)

    def emit(self, record):
        self.lines.append(self.format(record))


class MainWindow(Viewer):
    """Render setup and the loaded scene in a single OpenGL window."""

    def __init__(self, **kwargs):
        super().__init__(title="OpenSim Viewer", **kwargs)
        self.paths = dict.fromkeys(FILE_FIELDS, "")
        self.flags = dict.fromkeys(FLAGS, False)
        self.fps = 0
        self.cutoff = 6.0
        self.show_setup = True
        self.status = "Select a model; all other inputs are optional."
        self.pending = None
        self.sessions = ExitStack()
        self.browser_field = None
        self.browser_dir = str(Path.home())
        self.logs = LogBuffer()
        self.logs.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        self._logger = logging.getLogger("osim_viewer")
        self._old_level = self._logger.level
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(self.logs)
        logging.getLogger("osim-viewer").addHandler(self.logs)
        self.gui_controls["setup"] = self.gui_setup

    def gui_setup(self):
        """Draw persistent setup access, input options, browser and logs."""
        imgui.set_next_window_position(420, 30, condition=imgui.FIRST_USE_EVER)
        imgui.begin("OpenSim inputs", flags=imgui.WINDOW_ALWAYS_AUTO_RESIZE)
        if imgui.button("Hide setup" if self.show_setup else "Open / change model"):
            self.show_setup = not self.show_setup
        if self.show_setup:
            for key, (label, _) in FILE_FIELDS.items():
                _, self.paths[key] = imgui.input_text(label, self.paths[key], 4096)
                imgui.same_line()
                if imgui.button(f"Browse##{key}"):
                    self.browser_field = key
                    candidate = Path(self.paths[key]).expanduser()
                    if candidate.is_file():
                        self.browser_dir = str(candidate.parent)
            _, self.fps = imgui.input_int("FPS (0 = automatic)", self.fps)
            for key, label in FLAGS.items():
                _, self.flags[key] = imgui.checkbox(label, self.flags[key])
            if self.flags["smooth"]:
                _, self.cutoff = imgui.input_float("Cutoff (Hz)", self.cutoff)
            if self.paths["video"] and not self.paths["calib"]:
                imgui.text_wrapped(
                    "Video overlay needs calibration; without it, only the model is shown."
                )
            if imgui.button("Load in viewer"):
                try:
                    self.pending = build_arguments(
                        self.paths, self.flags, self.fps, self.cutoff
                    )
                    self.status = "Loading... (large recordings may take a while)"
                except ValueError as exc:
                    self.status = str(exc)
            imgui.text_wrapped(self.status)
            if imgui.collapsing_header("Session logs")[0]:
                imgui.begin_child("logs", width=550, height=150)
                for line in tuple(self.logs.lines):
                    imgui.text_unformatted(line)
                imgui.end_child()
        imgui.end()
        if self.browser_field:
            self.gui_browser()

    def gui_browser(self):
        """Browse the local filesystem without a second UI toolkit."""
        imgui.set_next_window_size(600, 450, condition=imgui.FIRST_USE_EVER)
        imgui.begin("Select input file")
        _, self.browser_dir = imgui.input_text("Directory", self.browser_dir, 4096)
        directory = Path(self.browser_dir).expanduser()
        if imgui.button("Parent"):
            directory = directory.parent
            self.browser_dir = str(directory)
        imgui.same_line()
        if imgui.button("Cancel"):
            self.browser_field = None
        imgui.begin_child("files", height=330)
        if self.browser_field:
            try:
                entries = sorted(
                    directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
                )
                for entry in entries:
                    is_dir = entry.is_dir()
                    if (
                        not is_dir
                        and entry.suffix.lower()
                        not in FILE_FIELDS[self.browser_field][1]
                    ):
                        continue
                    if imgui.selectable(("[Dir] " if is_dir else "") + entry.name)[0]:
                        if is_dir:
                            self.browser_dir = str(entry)
                        else:
                            self.paths[self.browser_field] = str(entry.resolve())
                            self.browser_field = None
                        break
            except OSError as exc:
                imgui.text_wrapped(str(exc))
        imgui.end_child()
        imgui.end()

    def render(self, time, frame_time, **kwargs):
        """Load outside the ImGui frame; GL work stays on the window thread."""
        if self.pending is not None:
            args, self.pending = self.pending, None
            self.reset()
            self.sessions.close()
            try:
                run_session(args, viewer=self, sessions=self.sessions)
                self._init_scene()
                self.export_animation_range[-1] = self.scene.n_frames - 1
                self._last_frame_rendered_at = time
                self.status = "Loaded. Open setup to load another recording."
                self.show_setup = False
            except Exception as exc:
                self._logger.exception("Unable to load recording")
                self.reset()
                self.sessions.close()
                self._init_scene()
                self.status = f"Unable to load: {exc}"
        super().render(time, frame_time, **kwargs)

    def on_close(self):
        """Release graphics before removing extracted video frames."""
        try:
            super().on_close()
        finally:
            if hasattr(self, "sessions"):
                if self.scene is not None:
                    self.scene.release()
                    self.scene = None
                self.sessions.close()
                self._logger.removeHandler(self.logs)
                self._logger.setLevel(self._old_level)
                logging.getLogger("osim-viewer").removeHandler(self.logs)


def main() -> int:
    """Open the integrated setup view without a subprocess or Qt runtime."""
    MainWindow().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
