"""Kontrakt wspólnej konfiguracji pełnego artefaktu PyInstaller."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _common():
    spec = importlib.util.spec_from_file_location(
        "epubforge_spec_common_test", ROOT / "build" / "_spec_common.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_build_includes_webengine_but_keeps_unused_qt_excluded() -> None:
    common = _common()
    required = {
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
    }
    assert common.WEBENGINE_BUILD is True
    assert required <= set(common.REQUIRED_MODULES)
    assert required <= set(common.HIDDEN_IMPORTS)
    assert required.isdisjoint(common.EXCLUDES)
    assert {
        "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
    } <= set(common.EXCLUDES)


def test_both_specs_share_configuration_and_disable_upx() -> None:
    for name in ("epubforge-portable.spec", "epubforge-dir.spec"):
        text = (ROOT / "build" / name).read_text(encoding="utf-8")
        assert "common.datas(spec_dir)" in text
        assert "hiddenimports=common.HIDDEN_IMPORTS" in text
        assert "excludes=common.EXCLUDES" in text
        assert "upx=False" in text


def test_gui_extra_is_real_full_qt_dependency_without_fake_preview_extra() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "gui = [" in pyproject
    assert '"PySide6>=6.8,<7"' in pyproject
    assert "preview = [" not in pyproject
