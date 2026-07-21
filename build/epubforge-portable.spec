# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — pełny PORTABLE z Qt WebEngine (jeden plik Windows).

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
    # Runtime hook oznacza ten (jednoplikowy) build jako portable — core.config
    # trzyma wtedy config obok exe, bez sidecara. Tylko wariant portable (F-04).
    runtime_hooks=[os.path.join(spec_dir, "rthook_portable.py")],
    excludes=common.EXCLUDES,
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
    icon=common.icon_path(spec_dir),
)
