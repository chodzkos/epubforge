"""Smoke test GUI zakładki statystyk (StatsTab)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.core import Epub
from epubforge.gui.tabs import stats as stats_mod
from epubforge.gui.tabs.stats import StatsTab
from epubforge.stats import compute_stats

pytestmark = pytest.mark.gui

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.epub"


def _tab_with_stats(qtbot: QtBot) -> StatsTab:
    """Zwraca StatsTab z policzonymi statystykami fixture."""
    tab = StatsTab()
    qtbot.addWidget(tab)
    with Epub(_FIXTURE) as epub:
        tab._on_done(compute_stats(epub))
    return tab


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


def test_open_report_writes_random_temp_file_not_fixed_path(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Podgląd raportu trafia do pliku o losowej nazwie (nie stałej, podatnej)."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    opened: list[str] = []
    monkeypatch.setattr(stats_mod.webbrowser, "open", lambda uri: opened.append(uri) or True)

    tab = _tab_with_stats(qtbot)
    tab._open_report()

    reports = list(tmp_path.glob("epubforge-stats-*.html"))
    assert len(reports) == 1
    # Stała, przewidywalna ścieżka (wektor symlink/podmiany) NIE powstaje.
    assert not (tmp_path / "epubforge-stats.html").exists()
    # Przeglądarka dostała file:// URI właśnie tego pliku, a plik ma treść raportu.
    assert opened == [reports[0].as_uri()]
    assert reports[0].read_text(encoding="utf-8").strip() != ""


def test_open_report_cleans_previous_reports(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kolejny podgląd sprząta wcześniejszy plik — brak akumulacji w /tmp."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(stats_mod.webbrowser, "open", lambda uri: True)

    stale = tmp_path / "epubforge-stats-OLD.html"
    stale.write_text("stale", encoding="utf-8")

    tab = _tab_with_stats(qtbot)
    tab._open_report()

    reports = list(tmp_path.glob("epubforge-stats-*.html"))
    assert stale not in reports  # stary podgląd usunięty PRZED utworzeniem nowego
    assert len(reports) == 1  # został tylko bieżący
