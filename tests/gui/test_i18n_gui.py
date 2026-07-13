"""Test i18n na poziomie GUI (wymaga PySide6) — reszta testów i18n jest bazowa.

Sam mechanizm gettext testujemy bez Qt w ``tests/test_i18n.py``; tu sprawdzamy
tylko, że ``MainWindow`` buduje zakładki w języku z configu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from chodzkos_gui_kit.qt.theme import ThemeManager
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.core.config import ConfigStore
from epubforge.gui.app import MainWindow

pytestmark = pytest.mark.gui


def test_main_window_uses_english_language_from_config(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """MainWindow z configiem language=en buduje zakładki po angielsku."""
    config_path = tmp_path / "config.json"
    store = ConfigStore("epubforge", path=config_path)
    store.update({"language": "en"})  # seed in-memory (update omija __setitem__)
    tools = {
        "pandoc": Tool("pandoc", None, available=False),
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
    }
    manager = ThemeManager(qapp, store)
    window = MainWindow(config_path, store, tools, manager)
    qtbot.addWidget(window)

    titles = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert titles == [
        "Metadata",
        "Converter",
        "Fixer",
        "Kindle Export",
        "Editor",
        "Validation",
        "Table of contents",
        "Statistics",
    ]
