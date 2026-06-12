# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — wariant PORTABLE (jeden plik epubforge.exe), GUI na PySide6."""

import importlib
import os

for required_module in (
    "PySide6.QtWidgets",
    "lxml.etree",
    "pyphen",
    "tinycss2",
    "platformdirs",
):
    importlib.import_module(required_module)

# Katalog tego spec-a (SPECPATH wstrzykiwany przez PyInstaller).
spec_dir = os.path.abspath(SPECPATH)
assets_dir = os.path.abspath(os.path.join(spec_dir, "..", "src", "epubforge", "gui", "assets"))

# Ikona: użyj prawdziwej z assets, gdy dostarczona; inaczej placeholder z build/.
_assets_icon = os.path.join(assets_dir, "icon.ico")
icon_path = _assets_icon if os.path.exists(_assets_icon) else os.path.join(spec_dir, "icon.ico")

# Ciężkie moduły Qt, których aplikacja nie używa — wykluczamy, by .exe nie spuchł.
_QT_EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtDesigner",
    "PySide6.QtTest",
]

a = Analysis(
    [os.path.join(spec_dir, "..", "src", "epubforge", "gui", "app.py")],
    pathex=[os.path.join(spec_dir, "..", "src")],
    binaries=[],
    datas=[
        (assets_dir, "epubforge/gui/assets"),  # logo/ikona dla okna About
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "lxml",
        "lxml.etree",
        "pyphen",
        "tinycss2",
        "platformdirs",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "scipy",
        "unittest",
        "test",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        *_QT_EXCLUDES,
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="epubforge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX uszkadza DLL-e Qt (GUI_STANDARD §9) — wyłączone
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI — bez okna konsoli
    icon=icon_path,
)
