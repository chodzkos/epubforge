"""Kontrakt backendu podglądu książki + typy danych (fundament Prompt 1).

Definiuje mały, typowany interfejs :class:`PreviewBackend`, który implementują dwa
tory renderowania:

* :class:`~epubforge.gui.preview.text_backend.TextDocumentPreviewBackend` — lekki
  fallback oparty o ``QTextBrowser`` (obecna logika podglądu);
* :class:`~epubforge.gui.preview.webengine_backend.WebEnginePreviewBackend` —
  dokładny podgląd Qt WebEngine (na tym etapie bezpieczna strona testowa).

Kontrakt CELOWO nie zawiera metod zależnych od ``QWebEngineView``, żeby lekki
fallback nigdy nie musiał importować Qt WebEngine (kryterium Prompt 1). Klasa
bazowa jest ``QWidget`` — to jedynie ``PySide6.QtWidgets``, nie WebEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from chodzkos_gui_kit.palette import Palette
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from epubforge.core import Epub
from epubforge.gui.preview.session import PreviewSession


class BackendKind(Enum):
    """Rodzaj toru renderowania podglądu."""

    TEXT = "text"
    WEBENGINE = "webengine"


class PreviewStatus(Enum):
    """Stan podglądu prezentowany na pasku (rozszerzany w kolejnych promptach)."""

    READY = "ready"  # Aktualny
    RENDERING = "rendering"  # Renderowanie
    LAST_GOOD = "last_good"  # Ostatnia poprawna wersja
    FALLBACK = "fallback"  # Fallback
    ERROR = "error"  # Błąd


class DiagnosticCategory(Enum):
    """Kategoria komunikatu diagnostycznego (Prompt 3 rozbuduje treść)."""

    BOOK_ERROR = "book_error"  # błąd publikacji
    SECURITY = "security"  # blokada bezpieczeństwa
    PREVIEW_LIMIT = "preview_limit"  # ograniczenie podglądu


@dataclass(frozen=True)
class DiagnosticEvent:
    """Pojedyncze zdarzenie diagnostyczne (bez sekretów i ścieżek użytkownika)."""

    category: DiagnosticCategory
    message: str
    source_url: str | None = None
    internal_path: str | None = None


@dataclass(frozen=True)
class PreviewSnapshot:
    """Nieruchomy zrzut treści do wyrenderowania.

    Na tym etapie niesie treść bieżącego dokumentu i odwołanie do publikacji;
    Prompt 3 zastąpi bezpośrednie odwołania pełnym ``resource_provider`` sesji.
    """

    xhtml: str
    epub: Epub | None
    internal_path: str | None
    generation_id: int = 0


@dataclass(frozen=True)
class PreviewState:
    """Zapamiętany stan podglądu do odtworzenia po ponownym renderze.

    Prompt 3/4 rozszerzą go o aktywny fragment i zaznaczony węzeł DOM.
    """

    scroll_ratio: float = 0.0


class PreviewBackend(QWidget):
    """Wspólny kontrakt obu torów podglądu (baza ``QWidget`` z sygnałami Qt).

    Podklasy ustawiają :attr:`kind` w ``__init__`` i implementują metody. Baza jest
    zwykłym ``QWidget`` (nie ``ABCMeta``), by uniknąć konfliktu metaklas z Qt —
    metody bazowe podnoszą :class:`NotImplementedError`.
    """

    #: Zmiana stanu podglądu (przekazuje :class:`PreviewStatus`).
    status_changed = Signal(object)
    #: Zdarzenie diagnostyczne (przekazuje :class:`DiagnosticEvent`).
    diagnostics = Signal(object)
    #: Żądanie otwarcia bieżącego pliku w narzędziu zewnętrznym (klucz narzędzia).
    open_external = Signal(str)

    kind: BackendKind

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia bieżącą sesję publikacji (tożsamość, origin — Prompt 2)."""
        raise NotImplementedError

    def render(self, snapshot: PreviewSnapshot) -> None:
        """Renderuje nieruchomy snapshot treści."""
        raise NotImplementedError

    def capture_state(self) -> PreviewState:
        """Zwraca bieżący stan podglądu (scroll, później zaznaczenie)."""
        raise NotImplementedError

    def restore_state(self, state: PreviewState) -> None:
        """Odtwarza zapamiętany stan podglądu po ponownym renderze."""
        raise NotImplementedError

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje chrome backendu (NIE treść książki) na daną paletę."""
        raise NotImplementedError

    def dispose(self) -> None:
        """Zwalnia zasoby backendu (widgety, procesy renderera)."""
        raise NotImplementedError
