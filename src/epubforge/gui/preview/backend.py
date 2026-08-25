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

from dataclasses import dataclass, field
from enum import Enum

from chodzkos_gui_kit.palette import Palette
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from epubforge.core import Epub
from epubforge.gui.preview.reader import (
    ComparisonMode,
    PublicationLayout,
    ReaderProfile,
    UserStyleSettings,
)
from epubforge.gui.preview.session import PreviewGeneration, PreviewSession


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
    SIMULATOR_LIMIT = "simulator_limit"  # ograniczenie profilu/layoutu czytnika
    QUALITY = "quality"  # ostrzeżenie jakości, bez arbitralnego auto-fixu


@dataclass(frozen=True)
class DiagnosticEvent:
    """Pojedyncze zdarzenie diagnostyczne (bez sekretów i ścieżek użytkownika)."""

    category: DiagnosticCategory
    message: str
    source_url: str | None = None
    internal_path: str | None = None
    problem_kind: str | None = None
    requester: str | None = None


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
    generation: PreviewGeneration | None = None
    changed_resource: str | None = None
    css_only: bool = False
    publication_layout: PublicationLayout = field(default_factory=PublicationLayout)


@dataclass(frozen=True)
class PreviewState:
    """Zapamiętany stan podglądu do odtworzenia po ponownym renderze.

    Prompt 3/4 rozszerzą go o aktywny fragment i zaznaczony węzeł DOM.
    """

    scroll_ratio: float = 0.0
    active_fragment: str | None = None
    node_id: str | None = None
    original_id: str | None = None
    dom_path: str | None = None
    text_fragment: str | None = None


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
    #: Żądanie przejścia do elementu źródłowego (:class:`SourceLocation`).
    source_requested = Signal(object)
    #: Żądanie otwarcia bieżącego pliku w narzędziu zewnętrznym (klucz narzędzia).
    open_external = Signal(str)
    #: Żądanie przejścia na lekki backend po trwałej awarii renderera.
    fallback_requested = Signal(str)
    #: Raport rzeczywistego elementu i kaskady zwrócony przez Chromium.
    element_inspected = Signal(object)
    #: Wynik walidacji/instalacji tymczasowej warstwy CSS.
    css_preview_result = Signal(object)
    #: Stan strony podglądu, aktywnych nadpisań i fontu.
    reader_state_changed = Signal(object)
    #: Lista ostrzeżeń jakości wyliczona z aktywnego layoutu Chromium.
    quality_diagnostics = Signal(object)
    #: Licznik zasobów aktywnej migawki (nie jest cache HTTP Chromium).
    cache_changed = Signal(object)
    #: Dokument ukończył render i można bezpiecznie pytać o jego DOM.
    document_ready = Signal(str)

    kind: BackendKind

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia bieżącą sesję publikacji (tożsamość, origin — Prompt 2)."""
        raise NotImplementedError

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Renderuje nieruchomy snapshot treści.

        Nazwa celowo nie brzmi ``render`` — ``QWidget.render`` to zajęta metoda
        rysująca widget na ``QPaintDevice`` (inny kontrakt).
        """
        raise NotImplementedError

    def capture_state(self) -> PreviewState:
        """Zwraca bieżący stan podglądu (scroll, później zaznaczenie)."""
        raise NotImplementedError

    def restore_state(self, state: PreviewState) -> None:
        """Odtwarza zapamiętany stan podglądu po ponownym renderze."""
        raise NotImplementedError

    def focus_node(self, node_id: str) -> None:
        """Wyróżnia element technicznym identyfikatorem, jeśli backend to obsługuje."""
        raise NotImplementedError

    def inspect_element(self, node_id: str | None = None) -> None:
        """Pobiera dane elementu; fallback może jawnie zgłosić brak możliwości."""
        self.element_inspected.emit(
            {"available": False, "limitations": ["Computed style wymaga WebEngine."]}
        )

    def preview_css_rule(
        self, selector: str, rule_text: str, *, current_element: bool = False
    ) -> None:
        """Instaluje zwalidowaną warstwę preview bez zmiany źródła."""
        self.css_preview_result.emit(
            {"ok": False, "error": "Podgląd CSS na żywo wymaga WebEngine."}
        )

    def clear_css_preview(self) -> None:
        """Usuwa techniczną warstwę preview, jeśli backend ją obsługuje."""

    def highlight_matches(self, selector: str) -> None:
        """Podświetla elementy dopasowane przez Chromium, jeśli dostępne."""

    def set_reader_simulation(
        self,
        profile: ReaderProfile,
        user_style: UserStyleSettings,
        comparison: ComparisonMode,
    ) -> None:
        """Ustawia neutralny profil; fallback zachowuje treść bez emulacji layoutu."""
        self.reader_state_changed.emit(
            {
                "available": False,
                "limitations": ["Kontrolowany layout stron wymaga WebEngine."],
            }
        )

    def navigate_preview_page(self, delta: int) -> None:
        """Przechodzi o stronę podglądu, jeśli backend obsługuje CSS columns."""

    def jump_to_current_element(self) -> None:
        """Przewija aktywny element do bieżącej strony podglądu."""

    def run_quality_diagnostics(
        self, *, min_font_px: float = 12.0, min_line_height: float = 1.1, accessibility: bool = True
    ) -> None:
        """Uruchamia diagnostykę rzeczywistego layoutu lub zgłasza ograniczenie."""
        self.quality_diagnostics.emit([])

    def export_viewport(self, path: str) -> bool:
        """Zapisuje sam viewport bez panelu inspektora, jeśli backend to wspiera."""
        return False

    def clear_preview_cache(self) -> None:
        """Czyści cache symulatora; cache HTTP WebEngine pozostaje wyłączony."""
        self.cache_changed.emit({"entries": 0, "bytes": 0})

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje chrome backendu (NIE treść książki) na daną paletę."""
        raise NotImplementedError

    def dispose(self) -> None:
        """Zwalnia zasoby backendu (widgety, procesy renderera)."""
        raise NotImplementedError

    def retained_resource_providers(self) -> tuple[object, ...]:
        """Zwraca providery generacji, które backend nadal silnie utrzymuje."""
        return ()
