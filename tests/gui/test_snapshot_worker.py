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
from epubforge.gui.preview.backend import BackendKind, PreviewSnapshot
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.cache import CacheLimits
from epubforge.gui.preview.controller import SnapshotResult
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


def test_aggregate_limit_plus_one_rejects_before_snapshot_request(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Suma effective odpada przed kopiami requestu i bez mutacji EPUB-a."""
    epub = Epub(sample_epub)
    epub.open()
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 8, raising=False)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 1 << 40, raising=False)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("aggregate limit musi odrzucić przed SnapshotRequest"),
    )
    before = epub.pending_changes()

    preview.render_document(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"OEBPS/styles/a.css": b"a" * 8},
        media_types={"OEBPS/styles/a.css": "text/css"},
    )

    assert preview._snapshot_worker is None
    assert preview._pending_snapshot is None
    assert preview._last_snapshot is None
    assert epub.pending_changes() == before
    assert "9 B" in preview.fallback_label.text()
    assert "8 B" in preview.fallback_label.text()
    preview.dispose()
    epub.close()


def test_exact_aggregate_limit_creates_snapshot_request(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Dokładnie limit jest dozwolony i używa zamrożonego pending."""
    epub = Epub(sample_epub)
    epub.open()
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(PreviewSession.create(epub))
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 8)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 1 << 40)
    captured: list[SnapshotRequest] = []
    monkeypatch.setattr(preview, "_start_snapshot_worker", captured.append)

    preview.render_document(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"OEBPS/styles/a.css": b"a" * 7},
        media_types={"OEBPS/styles/a.css": "text/css"},
    )

    assert len(captured) == 1
    assert captured[0].pending == epub.pending_changes()
    preview._snapshot_worker = None
    preview.dispose()
    epub.close()


def test_resident_budget_counts_retained_provider_cache_and_main_reserve(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Resident reject obejmuje stary provider, cache i kopię dokumentu."""
    epub = Epub(sample_epub)
    epub.open()
    limits = CacheLimits(documents=2, css=0, images=0, fonts=0, other=0)
    session = PreviewSession.create(epub, cache_limits=limits)
    session.advance(epub, "OEBPS/text/chapter1.xhtml", {"old.css": b"old"})
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 1)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 8)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 6)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("resident limit musi odrzucić przed requestem"),
    )

    preview.render_document("x", epub, "OEBPS/text/chapter1.xhtml")

    assert "8 B" in preview.fallback_label.text()
    assert "6 B" in preview.fallback_label.text()
    assert session.resource_provider is not None
    preview.dispose()
    epub.close()


def test_aggregate_reject_invalidates_stale_result_and_smaller_retry_works(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Reject wygrywa ze starym wynikiem, a późniejsza mała generacja startuje."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 8)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 1 << 40)
    captured: list[SnapshotRequest] = []
    monkeypatch.setattr(preview, "_start_snapshot_worker", captured.append)

    preview._snapshot_serial = 4
    stale = SnapshotRequest(
        serial=4,
        epub=epub,
        session=session,
        current_path="OEBPS/text/chapter1.xhtml",
        current_text="stale",
        dirty={},
        media_types={},
        pending=PendingChanges({}, frozenset()),
    )
    preview.render_document(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"too-large.css": b"a" * 8},
    )
    diagnostic = preview.fallback_label.text()
    preview._snapshot_ready(
        stale,
        SnapshotResult(PreviewSnapshot("stale", epub, stale.current_path, generation_id=4)),
    )

    assert preview._last_snapshot is None
    assert preview.fallback_label.text() == diagnostic
    preview.render_document(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"small.css": b"a"},
    )
    assert len(captured) == 1
    preview._snapshot_worker = None
    preview.dispose()
    epub.close()


def test_worker_rechecks_resident_budget_before_controller_copies(
    monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Queued request uwzględnia provider utworzony przez wcześniejszy worker."""
    epub = Epub(sample_epub)
    epub.open()
    limits = CacheLimits(documents=2, css=0, images=0, fonts=0, other=0)
    session = PreviewSession.create(epub, cache_limits=limits)
    session.advance(epub, "OEBPS/text/chapter1.xhtml", {"old.css": b"old"})
    controller = cast(Any, object())
    request = SnapshotRequest(
        serial=1,
        epub=epub,
        session=session,
        current_path="OEBPS/text/chapter1.xhtml",
        current_text="x",
        dirty={},
        media_types={},
        pending=PendingChanges({}, frozenset()),
    )
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 1)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 8)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 6)

    result = snapshot_worker.build_snapshot_job(
        cast(Any, None),
        cast(Any, None),
        lambda: False,
        controller,
        request,
    )

    assert isinstance(result, SnapshotResult)
    assert result.snapshot is None
    assert result.diagnostic is not None
    assert "8 B" in result.diagnostic.message
    session.close()
    epub.close()


class _RetainedSnapshotBackend:
    """Backend, który podczas async transition nadal trzyma poprzedni snapshot."""

    def __init__(self) -> None:
        self.kind = BackendKind.WEBENGINE
        self._last_snapshot: PreviewSnapshot | None = None

    def set_session(self, _session: PreviewSession | None) -> None:
        return None

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        self._last_snapshot = snapshot

    def dispose(self) -> None:
        self._last_snapshot = None

    def retained_resource_providers(self) -> tuple[object, ...]:
        snapshot = self._last_snapshot
        if snapshot is None or snapshot.generation is None:
            return ()
        return (snapshot.generation.resource_provider,)


def test_retained_backend_provider_is_counted_during_async_transition(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Provider A w backendzie + B w sesji + C w requestcie muszą być razem."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, cache_limits=CacheLimits(0, 0, 0, 0, 0))
    previous = session.advance(epub, "OEBPS/text/chapter1.xhtml", {"old.css": b"aaaa"})
    current = session.advance(epub, "OEBPS/text/chapter1.xhtml", {"cur.css": b"bbbb"})
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    preview._last_snapshot = PreviewSnapshot(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=current.generation_id,
        generation=current,
    )
    backend = _RetainedSnapshotBackend()
    backend._last_snapshot = PreviewSnapshot(
        "old",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=previous.generation_id,
        generation=previous,
    )
    preview._active = backend  # type: ignore[assignment]
    preview._webengine_backend = backend  # type: ignore[assignment]
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 64)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 16)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 74)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("retained backend A musi wejść do resident cap"),
    )

    preview.render_document(
        "c",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"next.css": b"cccc"},
    )

    assert "78 B" in preview.fallback_label.text()
    assert "74 B" in preview.fallback_label.text()
    preview._webengine_backend = None
    preview.dispose()
    epub.close()


def test_comparison_backend_retained_provider_is_counted(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Drugi provider comparison backendu nie może ominąć resident cap."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, cache_limits=CacheLimits(0, 0, 0, 0, 0))
    previous = session.advance(epub, "OEBPS/text/chapter1.xhtml", {"cmp.css": b"zzzz"})
    current = session.advance(epub, "OEBPS/text/chapter1.xhtml", {"now.css": b"yyyy"})
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    preview._last_snapshot = PreviewSnapshot(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=current.generation_id,
        generation=current,
    )
    comparison = _RetainedSnapshotBackend()
    comparison._last_snapshot = PreviewSnapshot(
        "cmp",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=previous.generation_id,
        generation=previous,
    )
    preview._comparison_backend = comparison  # type: ignore[assignment]
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 64)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 16)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 74)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("comparison provider musi wejść do resident cap"),
    )

    preview.render_document(
        "c",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"next.css": b"xxxx"},
    )

    assert "78 B" in preview.fallback_label.text()
    preview._comparison_backend = None
    preview.dispose()
    epub.close()


def test_duplicate_backend_and_session_provider_is_counted_once(
    qtbot: QtBot, sample_epub: Path
) -> None:
    """Ten sam obiekt providera nie może być zliczony dwa razy."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, cache_limits=CacheLimits(0, 0, 0, 0, 0))
    generation = session.advance(epub, "OEBPS/text/chapter1.xhtml", {"same.css": b"same"})
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    preview._last_snapshot = PreviewSnapshot(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=generation.generation_id,
        generation=generation,
    )
    backend = _RetainedSnapshotBackend()
    backend._last_snapshot = preview._last_snapshot
    preview._active = backend  # type: ignore[assignment]
    preview._webengine_backend = backend  # type: ignore[assignment]

    providers = preview._retained_generation_providers()

    assert providers == (generation.resource_provider,)
    preview._webengine_backend = None
    preview.dispose()
    epub.close()


def test_dirty_str_request_counts_encoded_peak_before_advance(
    qtbot: QtBot, monkeypatch: MonkeyPatch, sample_epub: Path
) -> None:
    """Request ze str dirty odrzuca limit, zanim advance zakoduje drugą kopię."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, cache_limits=CacheLimits(0, 0, 0, 0, 0))
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    monkeypatch.setattr(snapshot_worker, "MAX_MAIN_PREVIEW_BYTES", 64)
    monkeypatch.setattr(snapshot_worker, "MAX_DIRTY_PENDING_BYTES", 16)
    monkeypatch.setattr(snapshot_worker, "MAX_PREVIEW_RESIDENT_BYTES", 69)
    original_advance = session.advance

    def fail_if_advance(*args: object, **kwargs: object) -> object:
        pytest.fail("str->bytes peak musi być odrzucony przed PreviewSession.advance")
        return original_advance(*args, **kwargs)

    monkeypatch.setattr(session, "advance", fail_if_advance)
    monkeypatch.setattr(
        preview,
        "_start_snapshot_worker",
        lambda _request: pytest.fail("str->bytes peak nie może utworzyć SnapshotRequest"),
    )

    preview.render_document(
        "x",
        epub,
        "OEBPS/text/chapter1.xhtml",
        dirty={"sheet.css": "aaaa"},
    )

    assert "74 B" in preview.fallback_label.text()
    assert "69 B" in preview.fallback_label.text()
    preview.dispose()
    epub.close()


def test_source_mismatch_invalidates_stale_worker_result(qtbot: QtBot, sample_epub: Path) -> None:
    """Odrzucenie źródła nie pokazuje wyniku starego workera jako świeżego."""
    from epubforge.gui.preview.backend import DiagnosticCategory, DiagnosticEvent

    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    preview = BookPreview(settings=PreviewSettings())
    qtbot.addWidget(preview)
    preview.set_session(session)
    preview._snapshot_serial = 5
    preview._snapshot_ready(
        SnapshotRequest(
            serial=5,
            epub=epub,
            session=session,
            current_path="OEBPS/text/chapter1.xhtml",
            current_text="nowy",
            dirty={},
            media_types={},
            pending=PendingChanges({}, frozenset()),
        ),
        SnapshotResult(
            None,
            DiagnosticEvent(
                category=DiagnosticCategory.PREVIEW_LIMIT,
                message=(
                    "Plik źródłowy zmienił się podczas przygotowywania podglądu. Odśwież podgląd."
                ),
                problem_kind="zrodlo_zmienione",
                internal_path="OEBPS/text/chapter1.xhtml",
            ),
        ),
    )
    diagnostic = preview.fallback_label.text()
    stale = SnapshotRequest(
        serial=4,
        epub=epub,
        session=session,
        current_path="OEBPS/text/chapter1.xhtml",
        current_text="stale",
        dirty={},
        media_types={},
        pending=PendingChanges({}, frozenset()),
    )
    preview._snapshot_ready(
        stale,
        SnapshotResult(PreviewSnapshot("stale", epub, stale.current_path, generation_id=4)),
    )

    assert preview._last_snapshot is None
    assert preview.fallback_label.text() == diagnostic
    preview._snapshot_worker = None
    preview.dispose()
    epub.close()
