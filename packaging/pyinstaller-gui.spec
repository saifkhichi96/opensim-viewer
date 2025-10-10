# pyinstaller-gui.spec
# Build: pyinstaller -y packaging/pyinstaller-gui.spec
import sys
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('aitv_osim_app')

a = Analysis(
    ['-m', 'aitv_osim_app.gui'],
    pathex=[],
    binaries=[],
    datas=[('assets/Geometry', 'assets/Geometry')],
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
