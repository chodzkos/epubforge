"""Regresje propagacji i zamykania sesji przez BookPreview."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

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
