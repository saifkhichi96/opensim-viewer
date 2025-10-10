# pyinstaller-gui.spec
# Build: pyinstaller -y packaging/pyinstaller-gui.spec
from importlib.util import find_spec
import pathlib
import sys
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('osim_viewer')
spec = find_spec("osim_viewer.gui")
script_path = pathlib.Path(spec.origin)

a = Analysis(
    [str(script_path)],
    pathex=[],
    binaries=[],
    datas=[('../assets/Geometry', 'assets/Geometry')],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='aitv-osim-gui',
    console=False,  # GUI app
    disable_windowed_traceback=False,
)
