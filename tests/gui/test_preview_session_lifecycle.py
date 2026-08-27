"""Regresje propagacji i zamykania sesji przez BookPreview."""

from __future__ import annotations

import gc
import weakref
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from shiboken6 import isValid

from epubforge.core import Epub
from epubforge.gui.preview.backend import PreviewSnapshot
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.session import PreviewSession

pytestmark = pytest.mark.gui


class _SessionSink:
    """Dublet ukrytego backendu zapisujący przekazaną sesję."""

    def __init__(self) -> None:
        self.sessions: list[PreviewSession | None] = []

    def set_session(self, session: PreviewSession | None) -> None:
        """Rejestruje propagację bez tworzenia procesu Chromium."""
        self.sessions.append(session)


def test_new_session_reaches_hidden_backend_and_closes_previous(qtbot: QtBot) -> None:
    """Zmiana książki czyści również nieaktywny backend WebEngine."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    sink = _SessionSink()
    preview._webengine_backend = sink  # type: ignore[assignment]
    first = PreviewSession.create(source_path=Path("first.epub"))
    second = PreviewSession.create(source_path=Path("second.epub"))
    preview.set_session(first)
    preview.set_session(second)
    assert first.closed
    assert sink.sessions == [first, second]
    preview._webengine_backend = None
    preview.dispose()
    assert second.closed


def test_session_close_releases_fallback_document(qtbot: QtBot) -> None:
    """Zamknięcie książki usuwa aktywny dokument i jego cache zasobów fallbacku."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    session = PreviewSession.create(source_path=Path("book.epub"))
    preview.set_session(session)
    preview.html_preview.set_content("<html><body>retained</body></html>", None, None)
    document = preview.html_preview.view.document()

    preview.set_session(None)

    assert session.closed
    assert not isValid(document)
    assert preview.html_preview.view.toPlainText() == ""


def test_dispose_releases_last_generation_provider(qtbot: QtBot, sample_epub: Path) -> None:
    """Zamknięty widget nie utrzymuje overlayu ostatniej generacji."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(
        epub,
        "OEBPS/text/chapter1.xhtml",
        {"OEBPS/styles/large.css": b"large-buffer"},
    )
    provider = generation.resource_provider
    reference = weakref.ref(provider)
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.set_session(session)
    preview._last_snapshot = PreviewSnapshot(
        "<html/>",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=generation.generation_id,
        generation=generation,
    )

    preview.dispose()
    del provider
    del generation
    gc.collect()

    assert reference() is None
    epub.close()


def test_session_replacement_releases_previous_generation(qtbot: QtBot, sample_epub: Path) -> None:
    """Zmiana książki usuwa snapshot i provider poprzedniej publikacji."""
    epub = Epub(sample_epub)
    epub.open()
    first = PreviewSession.create(epub)
    generation = first.advance(
        epub,
        "OEBPS/text/chapter1.xhtml",
        {"OEBPS/styles/large.css": b"large-buffer"},
    )
    provider = generation.resource_provider
    reference = weakref.ref(provider)
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.set_session(first)
    preview._last_snapshot = PreviewSnapshot(
        "<html/>",
        epub,
        "OEBPS/text/chapter1.xhtml",
        generation_id=generation.generation_id,
        generation=generation,
    )

    preview.set_session(PreviewSession.create(source_path=Path("second.epub")))
    del provider
    del generation
    gc.collect()

    assert reference() is None
    preview.dispose()
    epub.close()
