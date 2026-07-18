"""Dokładny backend podglądu z izolowaną sesją i profilem Qt WebEngine."""

from __future__ import annotations

import logging

from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt.theme import current_palette
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QVBoxLayout, QWidget

from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
    PreviewState,
    PreviewStatus,
)
from epubforge.gui.preview.session import PreviewSession
from epubforge.i18n import _

logger = logging.getLogger(__name__)


class WebEngineInitError(RuntimeError):
    """Sygnalizuje, że backend WebEngine nie mógł się zainicjalizować."""


class WebEnginePreviewBackend(PreviewBackend):
    """QWebEngineView z prywatnym profilem, handlerem i blokadą nawigacji."""

    def __init__(self, parent: QWidget | None = None, *, theme: Palette | None = None) -> None:
        super().__init__(parent)
        self.kind = BackendKind.WEBENGINE
        self._session: PreviewSession | None = None
        self._palette = theme if theme is not None else current_palette()
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            from epubforge.gui.preview.webengine_security import (
                SecurePreviewPage,
                create_secure_profile,
                harden_page_settings,
            )
        except Exception as exc:
            raise WebEngineInitError(f"Import QtWebEngine: {exc}") from exc

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            self._profile, self._registry, self._handler, self._interceptor = create_secure_profile(
                self
            )
            self._page = SecurePreviewPage(self._profile, self._registry, self)
            harden_page_settings(self._page.settings())
            self._page.loadFinished.connect(self._on_load_finished)
            self._page.external_navigation.connect(self._on_external_navigation)
            self._view = QWebEngineView(self)
            self._view.setPage(self._page)
        except Exception as exc:
            raise WebEngineInitError(f"Bezpieczny profil QWebEngineView: {exc}") from exc
        layout.addWidget(self._view)

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia sesję; brak sesji natychmiast unieważnia rejestr URL-i."""
        self._session = session
        if session is None or session.closed:
            self._registry.clear()
            self._view.setUrl(QUrl("about:blank"))

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Buduje nieruchomą generację i ładuje jej URL z własnego schematu."""
        session = self._session
        if (
            session is None
            or session.closed
            or snapshot.epub is None
            or snapshot.internal_path is None
        ):
            self.status_changed.emit(PreviewStatus.ERROR)
            self.diagnostics.emit(
                DiagnosticEvent(
                    category=DiagnosticCategory.BOOK_ERROR,
                    message=_("Brak aktywnej sesji publikacji dla dokładnego podglądu."),
                )
            )
            return
        try:
            generation = session.advance(
                snapshot.epub,
                snapshot.internal_path,
                {snapshot.internal_path: snapshot.xhtml},
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.status_changed.emit(PreviewStatus.ERROR)
            self.diagnostics.emit(
                DiagnosticEvent(
                    category=DiagnosticCategory.BOOK_ERROR,
                    message=_("Nie udało się przygotować migawki podglądu."),
                    internal_path=snapshot.internal_path,
                )
            )
            logger.info("Błąd migawki podglądu: %s", exc)
            return
        self._registry.activate(generation)
        self.status_changed.emit(PreviewStatus.RENDERING)
        self._view.setUrl(QUrl(generation.document_url))

    def capture_state(self) -> PreviewState:
        """Zwraca stan domyślny; odczyt scrolla przez ApplicationWorld doda Prompt 3."""
        return PreviewState()

    def restore_state(self, state: PreviewState) -> None:
        """Odtworzenie scrolla zostaje świadomie odłożone do Promptu 3."""
        return None

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje chrome bez przeładowania treści publikacji."""
        self._palette = palette
        self.setStyleSheet(f"QWidget {{ background-color: {palette.bg}; }}")

    def dispose(self) -> None:
        """Unieważnia origin i zwalnia prywatny profil oraz renderer."""
        self._registry.clear()
        self._profile.removeUrlSchemeHandler(self._handler)
        self._view.stop()
        self._page.deleteLater()
        self._view.deleteLater()
        self._profile.deleteLater()

    def _on_load_finished(self, success: bool) -> None:
        """Raportuje wynik bieżącej generacji bez obsługi spóźnionych treści."""
        self.status_changed.emit(PreviewStatus.READY if success else PreviewStatus.ERROR)

    def _on_external_navigation(self, url: str) -> None:
        """Rejestruje blokadę linku; nigdy nie otwiera przeglądarki automatycznie."""
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.SECURITY,
                message=_("Zablokowano nawigację poza publikację."),
                source_url=url,
            )
        )
