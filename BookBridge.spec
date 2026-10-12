# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\projects\\New folder\\gemin\\bookbridge\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('README.md', '.'), ('bookbridge.html', '.'), ('sample_data', 'sample_data')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BookBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\projects\\New folder\\gemin\\icon.ico'],
    manifest='C:\\projects\\New folder\\gemin\\installer\\BookBridge.manifest',
)
