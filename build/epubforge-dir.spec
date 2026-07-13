# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — wariant ONEDIR (folder dist/epubforge/ do instalatora), PySide6.

Lista zasobów, hiddenimports i wykluczeń pochodzi z `build/_spec_common.py`
(jedno źródło dla onefile i onedir — patrz audyt F-03).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(SPECPATH))
import _spec_common as common

common.check_required_modules()
spec_dir = os.path.abspath(SPECPATH)

a = Analysis(
    [common.entry_script(spec_dir)],
    pathex=[common.src_pathex(spec_dir)],
    binaries=[],
    datas=common.datas(spec_dir),
    hiddenimports=common.HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=common.EXCLUDES,
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
    upx=False,  # UPX uszkadza DLL-e Qt (GUI_STANDARD §9) — wyłączone
    console=False,
    icon=common.icon_path(spec_dir),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # UPX uszkadza DLL-e Qt (GUI_STANDARD §9) — wyłączone
    upx_exclude=[],
    name="epubforge",
)
