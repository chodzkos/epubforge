"""Wspólne fixtures testów GUI (PySide6 / pytest-qt).

Wymusza platformę ``offscreen`` (brak displaya w CI) jeszcze zanim pytest-qt
utworzy ``QApplication`` — ustawienie zmiennej środowiskowej na poziomie importu
modułu wykonuje się w fazie zbierania testów, przed pierwszym użyciem fixture.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from epubforge.core import Tool


@pytest.fixture
def tools() -> dict[str, Tool]:
    """Zestaw wykrytych narzędzi: część dostępna, część nie (do testów stanu UI)."""
    return {
        "pandoc": Tool("pandoc", None, available=False),
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
        "calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True),
        "calibre_editor": Tool("calibre_editor", None, available=False),
        "sigil": Tool("sigil", Path("/bin/sigil"), available=True),
        "kindle_previewer": Tool("kindle_previewer", None, available=False),
    }


@pytest.fixture
def fake_worker() -> type:
    """Zwraca atrapę ``Worker`` rejestrującą wywołania bez startowania wątku.

    Pozwala testować, że zakładka poprawnie składa argumenty workera i podpina
    sygnały, nie uruchamiając realnego ``QThread`` (logikę workerów testujemy
    osobno, wołając funkcje robocze wprost).
    """

    class _Signal:
        def connect(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class FakeWorker:
        captured: ClassVar[list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]]] = []

        def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
            FakeWorker.captured.append((fn, args, kwargs))
            self.line = _Signal()
            self.progress = _Signal()
            self.done = _Signal()
            self.failed = _Signal()

        def start(self) -> None:
            return None

    return FakeWorker
