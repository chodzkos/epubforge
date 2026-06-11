# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — wariant ONEDIR (folder dist/epubforge/ do instalatora), PySide6."""

import importlib
import os

from PyInstaller.utils.hooks import collect_data_files

for required_module in (
    "PySide6.QtWidgets",
    "qdarktheme",
    "lxml.etree",
    "pyphen",
    "tinycss2",
):
    importlib.import_module(required_module)

spec_dir = os.path.abspath(SPECPATH)
assets_dir = os.path.abspath(os.path.join(spec_dir, "..", "src", "epubforge", "gui", "assets"))

_assets_icon = os.path.join(assets_dir, "icon.ico")
icon_path = _assets_icon if os.path.exists(_assets_icon) else os.path.join(spec_dir, "icon.ico")

# qdarktheme dostarcza zasoby (svg/json) ładowane w runtime — trzeba je dopiąć.
qdarktheme_data = collect_data_files("qdarktheme")

# Ciężkie moduły Qt, których aplikacja nie używa — wykluczamy, by build nie spuchł.
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
        (assets_dir, "epubforge/gui/assets"),
        *qdarktheme_data,
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "qdarktheme",
        "lxml",
        "lxml.etree",
        "pyphen",
        "tinycss2",
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

# ONEDIR: EXE bez binariów + COLLECT do folderu dist/epubforge/.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="epubforge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="epubforge",
)
