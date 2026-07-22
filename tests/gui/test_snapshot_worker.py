"""Regresje przygotowania snapshotu poza wątkiem GUI."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QWidget
from pytest import MonkeyPatch
from pytestqt.qtbot import QtBot
from shiboken6 import delete, isValid

from epubforge.core import Epub
from epubforge.gui.preview import snapshot_worker
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.snapshot_worker import SnapshotRequest, SnapshotWorkerMixin

pytestmark = pytest.mark.gui


def test_snapshot_worker_does_not_call_deleted_preview(
    qtbot: QtBot, monkeypatch: MonkeyPatch
) -> None:
    """Zakończenie snapshotu po usunięciu podglądu nie dotyka widgetów Qt."""
    started = threading.Event()
    release = threading.Event()

    def delayed_job(
        _emit_line: Any,
        _emit_progress: Any,
        should_cancel: Any,
        _controller: Any,
        _request: Any,
    ) -> object:
        started.set()
        assert release.wait(timeout=3)
        return None if should_cancel() else object()

    class SnapshotHost(SnapshotWorkerMixin, QWidget):
        pass

    monkeypatch.setattr(snapshot_worker, "build_snapshot_job", delayed_job)
    host = SnapshotHost()
    host._init_snapshot_pipeline()
    session = cast(Any, object())
    host._session = session
    host._snapshot_serial = 1
    request = SnapshotRequest(
        serial=1,
        epub=cast(Any, None),
        session=session,
        current_path="OEBPS/text/chapter1.xhtml",
        current_text="<p>Treść</p>",
        dirty={},
        media_types={},
    )
    host._start_snapshot_worker(request)
    worker = host._snapshot_worker
    assert worker is not None
    assert started.wait(timeout=1)

    delete(host)
    assert not isValid(host)
    release.set()
    assert worker.wait(3000)

    # Przetwarza oczekujące sygnały done/finished. Pytest-qt zgłosi wyjątek,
    # gdy callback spróbuje użyć usuniętego widgetu podglądu.
    qtbot.wait(20)


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
