"""Smoke test GUI zakładki statystyk (StatsTab)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.core import Epub
from epubforge.gui.tabs.stats import StatsTab
from epubforge.stats import compute_stats

pytestmark = pytest.mark.gui

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.epub"


def test_stats_tab_fills_cards_from_report(qtbot: QtBot) -> None:
    """Po policzeniu (synchronicznie) karty i listy są wypełnione."""
    tab = StatsTab()
    qtbot.addWidget(tab)
    with Epub(_FIXTURE) as epub:
        stats = compute_stats(epub)
    tab._on_done(stats)

    assert tab._cards["words"].text() == "6"
    assert tab.chapters_tree.topLevelItemCount() == 1
    assert tab.top_list.count() == len(stats.top_words)
    assert tab.export_button.isEnabled() is True
