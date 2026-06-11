# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — wariant ONEDIR (folder dist/epubforge/ do instalatora)."""

import os

import tkinterdnd2

spec_dir = os.path.abspath(SPECPATH)
assets_dir = os.path.abspath(os.path.join(spec_dir, "..", "src", "epubforge", "gui", "assets"))

# tkinterdnd2 — natywne binaria tkdnd; bez tego .exe wywala się "can't find package tkdnd".
tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")

_assets_icon = os.path.join(assets_dir, "icon.ico")
icon_path = _assets_icon if os.path.exists(_assets_icon) else os.path.join(spec_dir, "icon.ico")

a = Analysis(
    [os.path.join(spec_dir, "..", "src", "epubforge", "gui", "app.py")],
    pathex=[os.path.join(spec_dir, "..", "src")],
    binaries=[],
    datas=[
        (tkdnd_dir, "tkinterdnd2/tkdnd"),
        (assets_dir, "epubforge/gui/assets"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "lxml",
        "lxml.etree",
        "pyphen",
        "tinycss2",
        "tkinterdnd2",
        "darkdetect",
        "PIL.Image",
        "PIL.ImageTk",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "scipy", "PIL.tests", "unittest", "test"],
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
