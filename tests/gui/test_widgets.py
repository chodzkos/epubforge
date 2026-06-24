"""Smoke testy widgetów GUI (PySide6) i workera w wątku."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from chodzkos_gui_kit.palette import DARK, LIGHT
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from epubforge.gui.widgets import (
    FileList,
    LogView,
    PathEntry,
    Section,
    file_list_count_label,
)
from epubforge.gui.workers import Worker, level_for_line

pytestmark = pytest.mark.gui


def test_path_entry_get_set_and_signal(qtbot: QtBot, tmp_path: Path) -> None:
    """PathEntry zwraca/ustawia ścieżkę i emituje path_changed przy zmianie."""
    entry = PathEntry(mode="file")
    qtbot.addWidget(entry)

    changed: list[str] = []
    entry.path_changed.connect(changed.append)
    entry.set(str(tmp_path / "book.epub"))

    assert entry.get().endswith("book.epub")
    assert changed and changed[-1].endswith("book.epub")


def test_file_list_filters_and_emits(qtbot: QtBot, tmp_path: Path) -> None:
    """FileList przyjmuje tylko pasujące rozszerzenia i emituje files_changed."""
    file_list = FileList(extensions={".epub"}, count_label=file_list_count_label)
    qtbot.addWidget(file_list)

    emitted: list[list[Path]] = []
    file_list.files_changed.connect(emitted.append)
    file_list.add_files([tmp_path / "book.epub", tmp_path / "skip.txt"])

    assert file_list.files() == [tmp_path / "book.epub"]
    assert emitted[-1] == [tmp_path / "book.epub"]
    assert "1 plik" in file_list.count_label.text()

    file_list.clear()
    assert file_list.files() == []


def test_file_list_drop_adds_files(qtbot: QtBot, tmp_path: Path) -> None:
    """Natywny drop URL-i plików dodaje pasujące pozycje do listy."""
    file_list = FileList(extensions={".epub"})
    qtbot.addWidget(file_list)

    book = tmp_path / "dropped.epub"
    book.write_bytes(b"epub")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(book))])
    event = QDropEvent(
        QPoint(0, 0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    file_list.dropEvent(event)

    assert file_list.files() == [book]


def test_section_holds_widgets(qtbot: QtBot) -> None:
    """Section udostępnia layout treści i przyjmuje widgety."""
    section = Section("Opcje")
    qtbot.addWidget(section)
    label = QLabel("treść")
    section.add_widget(label)

    assert section.title() == "Opcje"
    assert section.content_layout().indexOf(label) >= 0


def test_log_view_appends_and_themes(qtbot: QtBot) -> None:
    """LogView dopisuje linie, czyści się i zmienia motyw kolorowania."""
    log = LogView()
    qtbot.addWidget(log)

    log.append_line("gotowe", "ok")
    log.append_line("uwaga", "warn")
    assert "gotowe" in log.toPlainText()
    assert "uwaga" in log.toPlainText()

    log.set_theme(LIGHT)
    assert log._color_for("ok") == LIGHT.accent
    log.set_theme(DARK)
    assert log._color_for("err") == DARK.red

    log.clear()
    assert log.toPlainText() == ""


def test_level_for_line_classifies() -> None:
    """Heurystyka poziomu logu rozpoznaje błędy, ostrzeżenia i sukces."""
    assert level_for_line("ERROR: coś") == "err"
    assert level_for_line("Warning: uwaga") == "warn"
    assert level_for_line("Success") == "ok"
    assert level_for_line("zwykła linia") == "info"


def test_worker_emits_done_with_result(qtbot: QtBot) -> None:
    """Worker uruchamia callable w wątku i emituje done z wynikiem."""

    def job(
        emit_line: Callable[[str, str], None], emit_progress: Callable[[int, int], None], x: int
    ) -> int:
        emit_line("praca", "info")
        emit_progress(1, 1)
        return x * 2

    worker = Worker(job, 21)
    results: list[object] = []
    worker.done.connect(results.append)
    with qtbot.waitSignal(worker.done, timeout=3000):
        worker.start()
    worker.wait()

    assert results == [42]


def test_worker_emits_failed_on_exception(qtbot: QtBot) -> None:
    """Wyjątek w callable trafia do sygnału failed (nie wywala aplikacji)."""

    def boom(
        emit_line: Callable[[str, str], None], emit_progress: Callable[[int, int], None]
    ) -> None:
        raise RuntimeError("pęknięcie")

    worker = Worker(boom)
    errors: list[str] = []
    worker.failed.connect(errors.append)
    with qtbot.waitSignal(worker.failed, timeout=3000):
        worker.start()
    worker.wait()

    assert errors and "pęknięcie" in errors[0]
