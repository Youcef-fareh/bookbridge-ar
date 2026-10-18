# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

ROOT = Path(SPECPATH)

excludes = [
    # Standard library unused modules
    'tkinter', '_tkinter', 'turtle', 'test', 'unittest', 'idlelib', 'pydoc_data',
    # PySide6 unused modules
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic',
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtQuick3D', 'PySide6.QtQuick3DRuntimeRender', 'PySide6.QtQuick3DParticles', 'PySide6.QtQuick3DXr',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
    'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus',
    'PySide6.QtSpatialAudio', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtLocation',
    'PySide6.QtScxml', 'PySide6.QtRemoteObjects',
    'PySide6.QtBluetooth', 'PySide6.QtNfc',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner', 'PySide6.QtUiTools',
    'PySide6.QtTest', 'PySide6.QtHelp', 'PySide6.QtSql',
    'PySide6.QtQuickTest',
]

a = Analysis(
    [str(ROOT / 'bookbridge' / 'app.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'README.md'), '.'),
        (str(ROOT / 'bookbridge.html'), '.'),
        (str(ROOT / 'sample_data'), 'sample_data'),
    ],
    hiddenimports=[
        'bookbridge',
        'bookbridge.ui',
        'bookbridge.ui.main_window',
        'bookbridge.ui.web_bridge',
        'bookbridge.ui.async_worker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

# Exclude unnecessary Qt6 binaries to minimize footprint
unwanted_dll_patterns = [
    'qt63d', 'qt6quick3d', 'qt6charts', 'qt6datavisualization', 'qt6graphs',
    'qt6sensors', 'qt6serialport', 'qt6serialbus', 'qt6spatialaudio',
    'qt6multimedia', 'qt6location', 'qt6scxml', 'qt6remoteobjects',
    'qt6bluetooth', 'qt6nfc', 'qt6pdf', 'qt6quickdialogs', 'qt6quickcontrols2',
    'qt6shadertools', 'qtvkb',
]

def keep_binary(bin_entry):
    name = bin_entry[0].lower()
    for pat in unwanted_dll_patterns:
        if pat in name:
            return False
    return True

a.binaries = [b for b in a.binaries if keep_binary(b)]

# Exclude debug packages, devtools, and unneeded locales
def keep_data(data_entry):
    dest = data_entry[0].lower().replace('\\', '/')
    if 'qtwebengine_devtools_resources' in dest:
        return False
    if '.debug.pak' in dest or '.debug.bin' in dest:
        return False
    # Only keep en-US, en-GB, and Arabic locales for QtWebEngine
    if 'qtwebengine_locales' in dest:
        if not (dest.endswith('/en-us.pak') or dest.endswith('/ar.pak') or dest.endswith('/en-gb.pak') or
                dest.endswith('\\en-us.pak') or dest.endswith('\\ar.pak') or dest.endswith('\\en-gb.pak')):
            return False
    # Remove unneeded Qt translation files (.qm)
    if 'translations' in dest and dest.endswith('.qm'):
        if not ('_ar' in dest or '_en' in dest):
            return False
    return True

a.datas = [d for d in a.datas if keep_data(d)]

pyz = PYZ(a.pure, optimize=1)

icon_file = ROOT / 'icon.ico'
icon_path = str(icon_file) if icon_file.exists() else None

manifest_file = ROOT / 'installer' / 'BookBridge.manifest'
manifest_path = str(manifest_file) if manifest_file.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BookBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    manifest=manifest_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BookBridge',
)
