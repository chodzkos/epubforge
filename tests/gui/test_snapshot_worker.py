"""Regresje przygotowania snapshotu poza wątkiem GUI."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from pytest import MonkeyPatch
from pytestqt.qtbot import QtBot

from epubforge.core import Epub
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings

pytestmark = pytest.mark.gui


def test_snapshot_parsing_does_not_block_gui_and_latest_request_wins(
    qtbot: QtBot,
    monkeypatch: MonkeyPatch,
    sample_epub: Path,
) -> None:
    """Worker nie jest wątkiem QApplication, a render_document wraca natychmiast."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    settings = PreviewSettings()
    settings.backend = "text"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    preview.set_session(session)
    original = preview._controller.build
    worker_threads: list[QThread] = []

    def slow_build(**kwargs: object):
        worker_threads.append(QThread.currentThread())
        time.sleep(0.12)
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(preview._controller, "build", slow_build)
    internal = "OEBPS/text/chapter1.xhtml"
    source = epub.read_file(internal).decode()
    started = time.perf_counter()
    preview.render_document(source.replace("Rozdział 1", "PIERWSZY"), epub, internal)
    elapsed = time.perf_counter() - started
    preview.render_document(source.replace("Rozdział 1", "OSTATNI"), epub, internal)

    assert elapsed < 0.05
    qtbot.waitUntil(
        lambda: preview._last_snapshot is not None and "OSTATNI" in preview._last_snapshot.xhtml,
        timeout=4_000,
    )
    assert worker_threads
    assert all(thread is not QApplication.instance().thread() for thread in worker_threads)
    preview.dispose()
    epub.close()
