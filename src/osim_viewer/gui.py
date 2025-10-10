from __future__ import annotations

import shlex
import shutil
import subprocess
import sys

from PyQt5 import QtCore, QtGui, QtWidgets


def _which_cli_name() -> str:
    # Prefer installed entrypoint
    exe = shutil.which("osim-viewer")
    if exe:
        return exe
    # Editable / in-source: use current python -m
    return sys.executable + " -m osim_viewer.cli"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenSim Viewer")
        self.resize(760, 520)
        self._build_ui()
        self.process: subprocess.Popen | None = None

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        layout = QtWidgets.QFormLayout(central)

        def file_row(label: str, filter_: str = "All Files (*)"):
            le = QtWidgets.QLineEdit()
            btn = QtWidgets.QPushButton("Browse…")
            btn.clicked.connect(lambda: self._browse(le, filter_))
            row = QtWidgets.QHBoxLayout()
            row.addWidget(le, 1)
            row.addWidget(btn)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            return container, le

        self.osim_w, self.osim_le = file_row("OSIM", "OpenSim (*.osim);;All Files (*)")
        self.mot_w, self.mot_le = file_row(
            "MOT", "OpenSim Motion (*.mot);;All Files (*)"
        )
        self.video_w, self.video_le = file_row(
            "Video", "Video Files (*.mp4 *.avi *.mov);;All Files (*)"
        )
        self.calib_w, self.calib_le = file_row(
            "Calibration (TOML)", "TOML (*.toml);;All Files (*)"
        )
        self.mocap_w, self.mocap_le = file_row(
            "Mocap (C3D)", "C3D (*.c3d);;All Files (*)"
        )

        self.fps_sb = QtWidgets.QSpinBox()
        self.fps_sb.setRange(1, 240)
        self.fps_sb.setSpecialValueText("default")
        self.fps_sb.setValue(0)

        self.color_parts_cb = QtWidgets.QCheckBox("Color skeleton parts")
        self.color_markers_cb = QtWidgets.QCheckBox("Color markers by parent part")
        self.joints_cb = QtWidgets.QCheckBox("Show joints")
        self.nosync_cb = QtWidgets.QCheckBox("Use video FPS (no sync)")
        self.keep_session_cb = QtWidgets.QCheckBox("Keep session cache")
        self.nosymlink_cb = QtWidgets.QCheckBox("Copy Geometry (no symlink)")

        self.log_te = QtWidgets.QPlainTextEdit()
        self.log_te.setReadOnly(True)
        self.log_te.setMaximumBlockCount(2000)

        self.run_btn = QtWidgets.QPushButton("Launch Viewer")
        self.run_btn.clicked.connect(self._run)

        # Assemble form
        layout.addRow("OSIM", self.osim_w)
        layout.addRow("MOT", self.mot_w)
        layout.addRow("Video", self.video_w)
        layout.addRow("Calibration", self.calib_w)
        layout.addRow("Mocap", self.mocap_w)
        layout.addRow("FPS", self.fps_sb)
        layout.addRow("", self.color_parts_cb)
        layout.addRow("", self.color_markers_cb)
        layout.addRow("", self.joints_cb)
        layout.addRow("", self.nosync_cb)
        layout.addRow("", self.keep_session_cb)
        layout.addRow("", self.nosymlink_cb)
        layout.addRow(self.run_btn)
        layout.addRow(self.log_te)
        self.setCentralWidget(central)

        # Light dark-ish theme
        app = QtWidgets.QApplication.instance()
        app.setStyle("Fusion")
        palette = app.palette()
        palette.setColor(palette.Window, QtGui.QColor(40, 40, 45))
        palette.setColor(palette.WindowText, QtCore.Qt.white)
        palette.setColor(palette.Base, QtGui.QColor(30, 30, 33))
        palette.setColor(palette.Text, QtCore.Qt.white)
        palette.setColor(palette.Button, QtGui.QColor(55, 55, 60))
        palette.setColor(palette.ButtonText, QtCore.Qt.white)
        app.setPalette(palette)

    def _browse(self, line: QtWidgets.QLineEdit, filter_: str) -> None:
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", "", filter_)
        if fn:
            line.setText(fn)

    def _append_log(self, text: str) -> None:
        self.log_te.appendPlainText(text.rstrip())

    def _run(self) -> None:
        if self.process:
            self._append_log("Process already running.")
            return

        args = []
        if self.osim_le.text():
            args += ["--osim", self.osim_le.text()]
        if self.mot_le.text():
            args += ["--mot", self.mot_le.text()]
        if self.video_le.text():
            args += ["--video", self.video_le.text()]
        if self.calib_le.text():
            args += ["--calib", self.calib_le.text()]
        if self.mocap_le.text():
            args += ["--mocap", self.mocap_le.text()]

        fps = self.fps_sb.value()
        if fps > 0:
            args += ["--fps", str(fps)]
        if self.color_parts_cb.isChecked():
            args.append("--color_parts")
        if self.color_markers_cb.isChecked():
            args.append("--color_markers")
        if self.joints_cb.isChecked():
            args.append("--joints")
        if self.nosync_cb.isChecked():
            args.append("--no-sync")
        if self.keep_session_cb.isChecked():
            args.append("--keep-session")
        if self.nosymlink_cb.isChecked():
            args.append("--no-symlink")

        cli = _which_cli_name()
        cmd = f"{cli} {' '.join(shlex.quote(a) for a in args)}"
        self._append_log(f"Running: {cmd}")
        # Use shell=True only if cli is string with space (python -m ...)
        shell = " -m " in cli
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=shell,
            universal_newlines=True,
        )

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._pump_output)
        self._timer.start(50)

    def _pump_output(self) -> None:
        if not self.process:
            return
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if line:
            self._append_log(line)
        if self.process.poll() is not None:
            # flush remaining
            remaining = self.process.stdout.read()
            if remaining:
                self._append_log(remaining)
            rc = self.process.returncode
            self._append_log(f"Process exited with code {rc}")
            self._timer.stop()
            self.process = None


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
