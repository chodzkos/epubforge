"""Dokładny backend podglądu (Qt WebEngine) — fundament (Prompt 1).

Na tym etapie backend pokazuje **bezpieczną stronę testową**: właściwe ładowanie
zasobów publikacji (własny schemat ``epub-preview``, sesja, sanitizacja, CSP)
wprowadzą Prompt 2 i 3. Tu chodzi o kontrakt, cykl życia widgetu i ścieżkę błędu.

Import ``QtWebEngineWidgets`` następuje **leniwie w konstruktorze**, nie na
poziomie modułu — dzięki temu sam import pakietu ``epubforge.gui.preview`` nie
wciąga Qt WebEngine, a lekki fallback pozostaje wolny od tej zależności.
"""

from __future__ import annotations

import logging

from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt.theme import current_palette
from PySide6.QtWidgets import QVBoxLayout, QWidget

from epubforge.gui.preview.backend import (
    BackendKind,
    PreviewBackend,
    PreviewSnapshot,
    PreviewState,
    PreviewStatus,
)
from epubforge.gui.preview.session import PreviewSession
from epubforge.i18n import _

logger = logging.getLogger(__name__)

# Minimalna, statyczna strona testowa — bez zasobów sieciowych i skryptów.
_TEST_PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
    "style-src 'unsafe-inline';\">"
    "<style>html,body{{height:100%;margin:0}}"
    "body{{display:flex;align-items:center;justify-content:center;"
    "font-family:sans-serif;color:#1a1a1a;background:#ffffff}}"
    "div{{max-width:32ch;text-align:center;line-height:1.5}}</style></head>"
    "<body><div>{message}</div></body></html>"
)


class WebEngineInitError(RuntimeError):
    """Sygnalizuje, że backend WebEngine nie mógł się zainicjalizować."""


class WebEnginePreviewBackend(PreviewBackend):
    """Backend ``QWebEngineView`` — dokładny podgląd (na tym etapie strona testowa).

    Raises:
        WebEngineInitError: gdy modułu WebEngine nie da się zaimportować albo
            widoku nie da się utworzyć (np. brak bibliotek systemowych). Wołający
            (``BookPreview``) łapie ten wyjątek i przechodzi na lekki backend.
    """

    def __init__(self, parent: QWidget | None = None, *, theme: Palette | None = None) -> None:
        super().__init__(parent)
        self.kind = BackendKind.WEBENGINE
        self._session: PreviewSession | None = None
        self._palette = theme if theme is not None else current_palette()

        # Leniwy, kontrolowany import — awaria kończy się WebEngineInitError,
        # nie wywróceniem aplikacji.
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # import Chromium bywa dowolnie awaryjny
            raise WebEngineInitError(f"Import QtWebEngineWidgets: {exc}") from exc

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            self._view = QWebEngineView(self)
        except Exception as exc:  # inicjalizacja widoku/Chromium
            raise WebEngineInitError(f"QWebEngineView: {exc}") from exc
        layout.addWidget(self._view)
        self._show_test_page()

    def _show_test_page(self) -> None:
        """Ładuje statyczną stronę testową (placeholder do czasu Prompt 3)."""
        message = _(
            "Dokładny podgląd (WebEngine) jest gotowy. Renderowanie treści książki "
            "zostanie włączone w kolejnym etapie."
        )
        self._view.setHtml(_TEST_PAGE.format(message=message))

    def set_session(self, session: PreviewSession | None) -> None:
        """Zapamiętuje sesję (origin i zasoby wprowadzi Prompt 2)."""
        self._session = session

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Na tym etapie utrzymuje stronę testową (realny render — Prompt 3)."""
        self.status_changed.emit(PreviewStatus.READY)

    def capture_state(self) -> PreviewState:
        """Brak synchronicznego dostępu do scrolla strony — stan domyślny."""
        return PreviewState()

    def restore_state(self, state: PreviewState) -> None:
        """Odtwarzanie stanu strony wprowadzi Prompt 3 (skrypt aplikacji)."""
        return None

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje CHROME wokół strony; NIE przeładowuje treści książki.

        Kolory strony książki są danymi profilu czytnika (Prompt 6), a nie palety
        aplikacji — dlatego zmiana motywu nie dotyka ``QWebEngineView.setHtml``.
        """
        self._palette = palette
        self.setStyleSheet(f"QWidget {{ background-color: {palette.bg}; }}")

    def dispose(self) -> None:
        """Zwalnia widok WebEngine (osobny proces renderera)."""
        self._view.deleteLater()
