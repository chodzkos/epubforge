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

from epubforge.core import Epub, PendingChanges
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
        pending=PendingChanges({}, frozenset()),
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


def test_main_preview_rejects_limit_plus_one_before_snapshot_pipeline(
    qtbot: QtBot,
    monkeypatch: MonkeyPatch,
    sample_epub: Path,
) -> None:
    """XHTML limit+1 nie jest kopiowany do requestu ani wysyłany do DOM/WebEngine."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    settings = PreviewSettings()
    settings.backend = "text"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    preview.set_session(session)
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 64)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("oversized XHTML nie może wejść do pipeline DOM"),
    )

    source = "<p>" + "x" * 58 + "</p>"  # dokładnie limit + 1 bajt UTF-8
    preview.render_document(source, epub, "OEBPS/text/chapter1.xhtml")

    assert preview._snapshot_worker is None
    assert preview._last_snapshot is None
    assert not preview.fallback_label.isHidden()
    assert "zbyt duży" in preview.fallback_label.text().lower()
    assert source not in preview.fallback_label.text()
    preview.dispose()
    epub.close()


def test_css_preview_rejects_limit_plus_one_before_snapshot_pipeline(
    qtbot: QtBot,
    monkeypatch: MonkeyPatch,
    sample_epub: Path,
) -> None:
    """CSS limit+1 odpada przed kopiowaniem requestu i parserem tinycss2."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    settings = PreviewSettings()
    settings.backend = "text"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    preview.set_session(session)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_CSS_BYTES", 64)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("oversized CSS nie może wejść do pipeline preview"),
    )

    preview.render_document(
        "x" * 65,
        epub,
        "OEBPS/styles/large.css",
        media_types={"OEBPS/styles/large.css": "text/css"},
    )

    assert preview._snapshot_worker is None
    assert "zbyt duży" in preview.fallback_label.text().lower()
    preview.dispose()
    epub.close()


def test_oversized_request_cancels_active_and_pending_snapshot(
    qtbot: QtBot,
    monkeypatch: MonkeyPatch,
    sample_epub: Path,
) -> None:
    """Odrzucenie nowej treści unieważnia starszy worker i kolejkę latest-wins."""

    class ActiveWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    epub = Epub(sample_epub)
    epub.open()
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 64)
    worker = ActiveWorker()
    preview._snapshot_serial = 7
    preview._snapshot_worker = worker  # type: ignore[assignment]
    preview._pending_snapshot = cast(Any, object())

    preview.render_document("x" * 65, epub, "OEBPS/text/chapter1.xhtml")

    assert preview._snapshot_serial == 8
    assert worker.cancelled
    assert preview._pending_snapshot is None
    preview._snapshot_worker = None
    preview.dispose()
    epub.close()


@pytest.mark.parametrize(
    ("dirty_path", "media_type", "limit_name"),
    [
        ("OEBPS/styles/dirty.css", "text/css", "MAX_PREVIEW_CSS_BYTES"),
        ("OEBPS/text/dirty.xhtml", "application/xhtml+xml", "MAX_MAIN_PREVIEW_BYTES"),
    ],
)
def test_dirty_text_overlay_rejects_before_snapshot_request(
    qtbot: QtBot,
    monkeypatch: MonkeyPatch,
    sample_epub: Path,
    dirty_path: str,
    media_type: str,
    limit_name: str,
) -> None:
    """Nieaktywny CSS/XHTML limit+1 nie jest kopiowany przez dict(dirty)."""
    epub = Epub(sample_epub)
    epub.open()
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    monkeypatch.setattr(snapshot_worker, limit_name, 64)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("oversized dirty overlay nie może utworzyć requestu"),
    )

    preview.render_document(
        "<html><body>small</body></html>",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={dirty_path: "x" * 65},
        media_types={dirty_path: media_type},
    )

    assert preview._snapshot_worker is None
    assert "zbyt duży" in preview.fallback_label.text().lower()
    preview.dispose()
    epub.close()


def test_pending_css_rejects_before_snapshot_request(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Pending CSS jest budżetowany przez rozmiar bez kopiowania bytes do requestu."""
    epub = Epub(sample_epub)
    epub.open()
    pending_path = "OEBPS/styles/pending.css"
    epub.write_file(pending_path, b"x" * 65)
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_CSS_BYTES", 64)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("oversized pending CSS nie może utworzyć requestu"),
    )

    preview.render_document(
        "<html><body>small</body></html>",
        epub,
        "OEBPS/text/chapter1.xhtml",
        media_types={pending_path: "text/css"},
    )

    assert preview._snapshot_worker is None
    assert "zbyt duży" in preview.fallback_label.text().lower()
    preview.dispose()
    epub.close()


def test_snapshot_request_freezes_pending_before_validation_race(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Pending dodany po zamrożeniu nie może wejść do requestu tej generacji."""
    epub = Epub(sample_epub)
    epub.open()
    late_path = "OEBPS/styles/late.css"
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    captured: list[SnapshotRequest] = []

    def mutate_after_snapshot(**_kwargs: object) -> None:
        epub.write_file(late_path, b"x" * 65)
        return None

    monkeypatch.setattr(snapshot_worker, "find_preview_text_violation", mutate_after_snapshot)
    monkeypatch.setattr(preview, "_start_snapshot_worker", captured.append)
    preview.render_document(
        "<html><body>small</body></html>",
        epub,
        "OEBPS/text/chapter1.xhtml",
        media_types={late_path: "text/css"},
    )

    assert len(captured) == 1
    assert late_path not in captured[0].pending.modified
    preview._snapshot_worker = None
    preview.dispose()
    epub.close()
