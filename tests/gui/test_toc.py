"""Testy GUI zakładki spisu treści (TocTab) — bez symulacji prawdziwego D&D."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core import ResourceLimitError
from epubforge.gui.tabs import toc as toc_module
from epubforge.gui.tabs.toc import TocTab
from epubforge.toc import MAX_TOC_ENTRIES, TocEntry

pytestmark = pytest.mark.gui


def _loaded(qtbot: QtBot, toc_epub: Path) -> TocTab:
    """Tworzy tab i wczytuje fixture EPUB."""
    tab = TocTab()
    qtbot.addWidget(tab)
    tab.load_epub(toc_epub)
    return tab


def test_load_populates_tree(qtbot: QtBot, toc_epub: Path) -> None:
    """Wczytanie pokazuje wpisy z nav (w tym martwy z tooltipem)."""
    tab = _loaded(qtbot, toc_epub)
    assert tab.tree.topLevelItemCount() == 2
    titles = {tab.tree.topLevelItem(i).text(0) for i in range(2)}
    assert "Rozdział pierwszy" in titles
    assert "Martwy wpis" in titles
    # Martwy wpis ma tooltip z powodem (kolumna celu).
    dead = next(
        tab.tree.topLevelItem(i)
        for i in range(2)
        if tab.tree.topLevelItem(i).text(0) == "Martwy wpis"
    )
    assert dead.toolTip(1) != ""


def test_generate_replaces_tree(
    qtbot: QtBot, toc_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generuj (po potwierdzeniu) zastępuje drzewo wpisami z nagłówków."""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab = _loaded(qtbot, toc_epub)
    tab.level_spin.setValue(3)
    tab._generate()
    assert tab.tree.topLevelItemCount() == 2
    first = tab.tree.topLevelItem(0)
    assert first.text(0) == "Rozdział pierwszy"
    assert first.childCount() == 2  # dwa h2


def test_title_edit_updates_model(qtbot: QtBot, toc_epub: Path) -> None:
    """Zmiana tekstu w kolumnie tytułu (itemChanged) trafia do modelu i brudzi stan."""
    from PySide6.QtCore import Qt

    tab = _loaded(qtbot, toc_epub)
    item = tab.tree.topLevelItem(0)
    entry = tab._items[item.data(0, Qt.ItemDataRole.UserRole)]
    item.setText(0, "Zmieniony tytuł")
    assert entry.title == "Zmieniony tytuł"
    assert tab.has_unsaved_changes() is True


def test_handle_move_into(qtbot: QtBot, toc_epub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wydzielony handler przeniesienia (src, dst, tryb) działa na modelu."""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab = _loaded(qtbot, toc_epub)
    tab._generate()  # dwa korzenie: Rozdział pierwszy, Rozdział drugi
    first, second = tab._entries[0], tab._entries[1]
    tab._handle_move(second, first, "into")
    assert tab.tree.topLevelItemCount() == 1
    assert tab._entries[0].children[-1] is second


def test_save_clears_dirty(qtbot: QtBot, toc_epub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Zapis do EPUB czyści wskaźnik niezapisanych zmian."""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    tab = _loaded(qtbot, toc_epub)
    tab._generate()
    assert tab.has_unsaved_changes() is True
    tab._save()
    assert tab.has_unsaved_changes() is False


def test_load_shows_safe_message_for_toc_resource_limit(
    qtbot: QtBot, toc_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limit TOC nie ucieka ze slotu i nie zostawia otwartego modelu do edycji."""
    tab = _loaded(qtbot, toc_epub)
    monkeypatch.setattr(
        toc_module,
        "read_toc",
        lambda _epub: (_ for _ in ()).throw(ResourceLimitError("surowy szczegół")),
    )

    tab.load_epub(toc_epub)

    assert tab._epub is None
    assert tab._epub_path is None
    assert tab._entries == []
    assert "zbyt duży lub zbyt głęboki" in tab.status_label.text()
    assert "surowy szczegół" not in tab.status_label.text()


def test_generate_shows_safe_message_for_toc_resource_limit(
    qtbot: QtBot, toc_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limit generatora pozostaje kontrolowanym stanem zakładki."""
    tab = _loaded(qtbot, toc_epub)
    monkeypatch.setattr(tab, "_confirm", lambda _question: True)
    monkeypatch.setattr(
        toc_module,
        "generate_toc",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ResourceLimitError("surowy szczegół")),
    )

    tab._generate()

    assert "zbyt duży lub zbyt głęboki" in tab.status_label.text()
    assert "surowy szczegół" not in tab.status_label.text()


def test_add_at_entry_limit_rolls_back_without_dirty_state(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dodanie wpisu 20 001 nie mutuje modelu ani nie przebudowuje widgetów."""
    tab = TocTab()
    qtbot.addWidget(tab)
    tab._entries = [TocEntry(str(index)) for index in range(MAX_TOC_ENTRIES)]
    monkeypatch.setattr(tab, "_rebuild_tree", lambda: pytest.fail("nie wolno przebudować"))

    tab._add_entry()

    assert len(tab._entries) == MAX_TOC_ENTRIES
    assert tab.has_unsaved_changes() is False
    assert "zbyt duży lub zbyt głęboki" in tab.status_label.text()


def test_reorder_handles_preexisting_oversized_model(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niespójny model programowy nie wypuszcza ResourceLimitError ze slotu."""
    tab = TocTab()
    qtbot.addWidget(tab)
    tab._entries = [TocEntry(str(index)) for index in range(MAX_TOC_ENTRIES + 1)]
    monkeypatch.setattr(tab, "_selected_entry", lambda: tab._entries[0])

    tab._reorder("up")

    assert tab.has_unsaved_changes() is False
    assert "zbyt duży lub zbyt głęboki" in tab.status_label.text()
