"""Podgląd książki w edytorze — wybór backendu, sesja i konfiguracja (Prompt 1).

Publiczne API warstwy podglądu. **Import tego pakietu nie wciąga Qt** — moduły
zależne od PySide6 (`backend`, `book_preview`, `text_backend`) są ładowane leniwie
przez ``__getattr__`` (PEP 562). Dzięki temu czyste narzędzia (`settings`,
`session`, `availability`, `preinit`) oraz ich testy działają też bez PySide6, a
lekki fallback nigdy nie importuje Qt WebEngine (ten ładuje się dopiero w
konstruktorze ``WebEnginePreviewBackend``).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

# Czyste moduły (bez Qt) — bezpieczne do eager-importu, dają czytelne błędy.
from epubforge.gui.preview.availability import WebEngineProbe, probe_webengine
from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME, preinit_webengine
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings

# Nazwa → moduł, z którego ładujemy ją leniwie (import Qt dopiero przy użyciu).
_LAZY: dict[str, str] = {
    "BackendKind": "backend",
    "DiagnosticCategory": "backend",
    "DiagnosticEvent": "backend",
    "PreviewBackend": "backend",
    "PreviewSnapshot": "backend",
    "PreviewState": "backend",
    "PreviewStatus": "backend",
    "BookPreview": "book_preview",
    "TextDocumentPreviewBackend": "text_backend",
}

if TYPE_CHECKING:  # dla statycznej analizy widoczne wprost (import Qt tylko w typach)
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
    from epubforge.gui.preview.text_backend import TextDocumentPreviewBackend


def __getattr__(name: str) -> Any:
    """Leniwie ładuje nazwy zależne od Qt (PEP 562), by import pakietu był lekki."""
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, name)


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
