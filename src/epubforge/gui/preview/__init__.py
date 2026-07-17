"""Podgląd książki w edytorze — wybór backendu, sesja i konfiguracja (Prompt 1).

Publiczne API warstwy podglądu. Import tego pakietu **nie** wciąga Qt WebEngine:
``webengine_backend`` importuje ``QtWebEngineWidgets`` dopiero w konstruktorze,
a ``preinit``/``availability`` sprawdzają dostępność bez ładowania modułu.
"""

from __future__ import annotations

from epubforge.gui.preview.availability import WebEngineProbe, probe_webengine
from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
    PreviewState,
    PreviewStatus,
)
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME, preinit_webengine
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.text_backend import TextDocumentPreviewBackend

__all__ = [
    "EPUB_PREVIEW_SCHEME",
    "BackendKind",
    "BookPreview",
    "DiagnosticCategory",
    "DiagnosticEvent",
    "PreviewBackend",
    "PreviewSession",
    "PreviewSettings",
    "PreviewSnapshot",
    "PreviewState",
    "PreviewStatus",
    "TextDocumentPreviewBackend",
    "WebEngineProbe",
    "preinit_webengine",
    "probe_webengine",
]
