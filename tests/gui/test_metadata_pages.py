"""Testy pola liczby stron i asynchronicznej estymacji w Metadanych."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.gui import metadata_pages
from epubforge.gui.metadata_pages import MetadataPages
from epubforge.stats import BookStats, StatsOptions

pytestmark = pytest.mark.gui


def _stats(pages: int) -> BookStats:
    """Buduje minimalny wynik statystyk dla testów komponentu."""
    return BookStats(title="Test", authors=[], words=pages * 250, chars=1, estimated_pages=pages)


def test_page_states_switch_cleanly_between_epub_versions(qtbot: QtBot, tmp_path: Path) -> None:
    """Przejście EPUB 3 → 2 → 3 nie przenosi wartości ani stanu poprzedniej książki."""
    pages = MetadataPages()
    qtbot.addWidget(pages)
    first = tmp_path / "first.epub"
    second = tmp_path / "second.epub"
    third = tmp_path / "third.epub"

    pages.set_document(first, supported=True, page_count=120)
    assert pages.value() == 120
    assert pages.page_count.isEnabled()
    assert pages.calculate_button.isEnabled()

    pages.set_document(second, supported=False, page_count=None)
    assert pages.value() is None
    assert not pages.page_count.isEnabled()
    assert not pages.calculate_button.isEnabled()
    assert not pages.epub2_notice.isHidden()

    pages.set_document(third, supported=True, page_count=None)
    assert pages.value() is None
    assert pages.page_count.isEnabled()
    assert pages.calculate_button.isEnabled()
    assert pages.epub2_notice.isHidden()


def test_calculate_uses_compute_stats_and_inserts_estimate(
    qtbot: QtBot, sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przycisk używa ``compute_stats(StatsOptions())`` i nie zapisuje pliku."""
    calls: list[StatsOptions] = []

    def fake_compute(_epub: Any, options: StatsOptions) -> BookStats:
        calls.append(options)
        return _stats(77)

    monkeypatch.setattr(metadata_pages, "compute_stats", fake_compute)
    pages = MetadataPages()
    qtbot.addWidget(pages)
    statuses: list[str] = []
    pages.status_changed.connect(statuses.append)
    pages.set_document(sample_epub, supported=True, page_count=None)

    pages.calculate_button.click()
    assert not pages.calculate_button.isEnabled()
    qtbot.waitUntil(lambda: pages._worker is None, timeout=3_000)

    assert len(calls) == 1
    assert calls[0].words_per_page == 250
    assert pages.value() == 77
    assert any("77" in status and "Zapisz" in status for status in statuses)


def test_calculate_error_updates_status_and_shows_dialog(
    qtbot: QtBot, sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Błąd Workera jest widoczny w statusie i dialogu."""
    errors: list[str] = []
    statuses: list[str] = []

    def fail_compute(_epub: Any, _options: StatsOptions) -> BookStats:
        raise RuntimeError("awaria statystyk")

    monkeypatch.setattr(metadata_pages, "compute_stats", fail_compute)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _parent, _title, message: errors.append(message)),
    )
    pages = MetadataPages()
    qtbot.addWidget(pages)
    pages.status_changed.connect(statuses.append)
    pages.set_document(sample_epub, supported=True, page_count=None)

    pages.calculate_button.click()
    qtbot.waitUntil(lambda: pages._worker is None, timeout=3_000)

    assert errors and "awaria statystyk" in errors[0]
    assert statuses and "awaria statystyk" in statuses[-1]
    assert pages.value() is None


def test_stale_calculation_does_not_update_new_document(
    qtbot: QtBot,
    sample_epub: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wynik rozpoczęty dla poprzedniej ścieżki jest odrzucany po zmianie wyboru."""
    started = threading.Event()
    release = threading.Event()

    def slow_compute(_epub: Any, _options: StatsOptions) -> BookStats:
        started.set()
        assert release.wait(timeout=3)
        return _stats(99)

    monkeypatch.setattr(metadata_pages, "compute_stats", slow_compute)
    pages = MetadataPages()
    qtbot.addWidget(pages)
    pages.set_document(sample_epub, supported=True, page_count=None)
    pages.calculate_button.click()
    assert started.wait(timeout=1)

    next_book = tmp_path / "next.epub"
    pages.set_document(next_book, supported=True, page_count=44)
    release.set()
    qtbot.waitUntil(lambda: pages._worker is None, timeout=3_000)

    assert pages.value() == 44
    assert pages.calculate_button.isEnabled()
