"""Testy scrollowalnych zakładek GUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.gui.tabs.converter import ConverterTab
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.tabs.fixer import FixerTab
from epubforge.gui.tabs.kfx import KfxTab
from epubforge.gui.tabs.metadata import MetadataTab
from epubforge.gui.tabs.stats import StatsTab
from epubforge.gui.tabs.toc import TocTab
from epubforge.gui.tabs.validator import ValidatorTab

pytestmark = pytest.mark.gui


def _tools() -> dict[str, Tool]:
    return {
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
        "calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True),
        "calibre_editor": Tool("calibre_editor", None, available=False),
        "epubcheck": Tool("epubcheck", Path("/opt/epubcheck.jar"), "5.1.0", True),
        "java": Tool("java", Path("/usr/bin/java"), "17", True),
        "kindle_previewer": Tool("kindle_previewer", None, available=False),
        "sigil": Tool("sigil", Path("/bin/sigil"), available=True),
    }


def _root_scroll_area(tab: QWidget) -> QScrollArea:
    layout = tab.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    scroll = item.widget()
    assert isinstance(scroll, QScrollArea)
    return scroll


def _assert_scroll_contract(tab: QWidget) -> None:
    scroll = _root_scroll_area(tab)
    assert scroll.widgetResizable() is True
    assert scroll.frameShape() == QFrame.Shape.NoFrame
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.acceptDrops() is False
    assert scroll.viewport().acceptDrops() is False
    assert scroll.widget() is not None


def test_fixer_tab_is_scrollable_at_minimum_window_size(qtbot: QtBot) -> None:
    """FixerTab w oknie 760x520 ma scroll area zamiast ściskać sekcje."""
    window = QWidget()
    layout = QVBoxLayout(window)
    tab = FixerTab(tools=_tools())
    layout.addWidget(tab)
    qtbot.addWidget(window)

    window.resize(760, 520)
    window.show()
    qtbot.waitExposed(window)

    _assert_scroll_contract(tab)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MetadataTab(tools=_tools()),
        lambda: ConverterTab(config={}),
        lambda: KfxTab(tools=_tools(), config={}),
        lambda: ValidatorTab(tools=_tools()),
        lambda: TocTab(config={}),
        lambda: StatsTab(config={}),
    ],
)
def test_vertical_tabs_are_wrapped_in_scroll_area(
    qtbot: QtBot,
    factory: Callable[[], QWidget],
) -> None:
    """Zakładki z pionowym układem sekcji używają wspólnego scroll helpera."""
    tab = factory()
    qtbot.addWidget(tab)
    _assert_scroll_contract(tab)


def test_editor_tab_keeps_own_splitter_without_root_scroll(qtbot: QtBot) -> None:
    """EditorTab ma własny splitter i scrolle, więc nie dostaje root QScrollArea."""
    tab = EditorTab(tools=_tools())
    qtbot.addWidget(tab)
    layout = tab.layout()
    assert layout is not None
    first = layout.itemAt(0)
    assert first is not None
    assert not isinstance(first.widget(), QScrollArea)
