# pyinstaller-gui.spec
# Build: pyinstaller -y packaging/pyinstaller-gui.spec
from importlib.util import find_spec
import pathlib
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('osim_viewer') + collect_submodules('moderngl_window.context.pyglet')
spec = find_spec("osim_viewer.gui")
script_path = pathlib.Path(spec.origin)

a = Analysis(
    [str(script_path)],
    pathex=[],
    binaries=[],
    datas=collect_data_files('osim_viewer') + [(str(pathlib.Path(SPECPATH).parent / 'assets' / 'Geometry'), 'assets/Geometry')],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='osim-viewer-gui',
    console=False,  # GUI app
    disable_windowed_traceback=False,
)
