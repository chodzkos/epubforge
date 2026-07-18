"""Widget podglądu książki wybierający backend + wspólny pasek narzędzi (Prompt 1).

``BookPreview`` spina oba tory renderowania za jednym paskiem:

* selektor **Auto / Dokładny / Szybki**,
* status aktywnego backendu,
* komunikat o fallbacku (z ofertą przejścia na szybki podgląd przy wymuszeniu).

Wybór backendu jest trwały przez istniejący ``ConfigStore`` (adapter
:class:`~epubforge.gui.preview.settings.PreviewSettings`). Brak lub awaria
WebEngine zawsze kończy się cichym przejściem na lekki backend — GUI działa dalej.

Chrome (pasek, statusy) korzysta z palety motywu; kolory strony książki są
niezależne od motywu aplikacji (dane profilu czytnika — Prompt 6).
"""

from __future__ import annotations

import logging

from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt.theme import current_palette
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub, Tool
from epubforge.gui.preview.availability import probe_webengine
from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
)
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.text_backend import TextDocumentPreviewBackend
from epubforge.gui.preview.webengine_backend import (
    WebEngineInitError,
    WebEnginePreviewBackend,
)
from epubforge.gui.widgets.html_preview import HtmlPreview
from epubforge.i18n import _

logger = logging.getLogger(__name__)

# Pozycje selektora backendu (indeks → wartość ustawienia).
_BACKEND_ORDER: tuple[str, ...] = ("auto", "webengine", "text")


class BookPreview(QWidget):
    """Pasek wyboru backendu + aktywny tor podglądu (lekki albo dokładny).

    Sygnały:
        open_external: żądanie otwarcia bieżącego pliku w narzędziu (klucz).
        diagnostics: zdarzenie diagnostyczne z backendu (:class:`DiagnosticEvent`).
    """

    open_external = Signal(str)
    diagnostics = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        theme: Palette | None = None,
        settings: PreviewSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._tools = tools or {}
        self._palette = theme if theme is not None else current_palette()
        self._settings = settings if settings is not None else PreviewSettings()
        self._generation = 0
        self._render_count = 0
        self._last_snapshot: PreviewSnapshot | None = None
        self._session: PreviewSession | None = None
        self._webengine_backend: PreviewBackend | None = None

        self._build_ui()

        # Lekki backend istnieje zawsze (fallback). Dokładny tworzymy leniwie.
        self._text_backend = TextDocumentPreviewBackend(tools=self._tools, theme=self._palette)
        self._text_backend.open_external.connect(self.open_external)
        self._text_backend.diagnostics.connect(self.diagnostics)
        self._body_layout.addWidget(self._text_backend)
        self._active: PreviewBackend = self._text_backend

        self._sync_combo_from_settings()
        self._apply_backend(self._settings.backend, persist=False)
        self._style_chrome()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        label = QLabel(_("Podgląd:"))
        bar.addWidget(label)

        self.backend_combo = QComboBox()
        self.backend_combo.setToolTip(
            _("Tor podglądu: Auto (dokładny, gdy dostępny), Dokładny (WebEngine), Szybki (Qt)")
        )
        for value in _BACKEND_ORDER:
            self.backend_combo.addItem(_backend_label(value), value)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_selected)
        bar.addWidget(self.backend_combo)

        self.status_label = QLabel()
        self.status_label.setToolTip(_("Aktualnie używany tor renderowania podglądu"))
        bar.addWidget(self.status_label)

        self.fallback_label = QLabel()
        self.fallback_label.setWordWrap(True)
        self.fallback_label.setVisible(False)
        bar.addWidget(self.fallback_label, stretch=1)

        self.use_fast_button = QPushButton(_("Użyj szybkiego"))
        self.use_fast_button.setToolTip(_("Przełącz podgląd na szybki tor (Qt)"))
        self.use_fast_button.clicked.connect(self._on_use_fast_clicked)
        self.use_fast_button.setVisible(False)
        bar.addWidget(self.use_fast_button)

        bar.addStretch(0)
        layout.addLayout(bar)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._body, stretch=1)

    # ── Kompatybilność / dostęp ────────────────────────────────────────────────

    @property
    def html_preview(self) -> HtmlPreview:
        """Zwraca podgląd ``QTextBrowser`` lekkiego backendu (kompat z istniejącym API)."""
        return self._text_backend.html_preview

    @property
    def active_kind(self) -> BackendKind:
        """Rodzaj aktualnie aktywnego backendu."""
        return self._active.kind

    @property
    def render_count(self) -> int:
        """Liczba wykonanych renderów (do testów: motyw nie może jej zwiększać)."""
        return self._render_count

    # ── Wybór backendu ─────────────────────────────────────────────────────────

    def _sync_combo_from_settings(self) -> None:
        """Ustawia selektor na zapamiętaną wartość bez emisji zmiany-persist."""
        index = _BACKEND_ORDER.index(self._settings.backend)
        self.backend_combo.blockSignals(True)
        self.backend_combo.setCurrentIndex(index)
        self.backend_combo.blockSignals(False)

    def _on_backend_selected(self, index: int) -> None:
        """Zmiana selektora przez użytkownika — stosuje i zapisuje wybór."""
        if 0 <= index < len(_BACKEND_ORDER):
            self._apply_backend(_BACKEND_ORDER[index], persist=True)

    def _on_use_fast_clicked(self) -> None:
        """Przechodzi na szybki tor po nieudanym wymuszeniu dokładnego."""
        self.backend_combo.setCurrentIndex(_BACKEND_ORDER.index("text"))

    def _apply_backend(self, kind: str, *, persist: bool) -> None:
        """Ustawia aktywny backend wg wyboru, z bezpiecznym fallbackiem.

        Uwaga (Prompt 1): tryb ``auto`` rozstrzyga się na lekki backend, bo
        dokładny (WebEngine) nie renderuje jeszcze treści publikacji — pokazuje
        tylko bezpieczną stronę testową, więc automatyczne przełączenie
        pogorszyłoby podgląd. Prompt 3 przełączy ``auto`` na WebEngine, gdy będzie
        renderować realną treść. Dokładny tor pozostaje dostępny jawnie.
        """
        if persist:
            self._settings.backend = kind
        self.fallback_label.setVisible(False)
        self.use_fast_button.setVisible(False)

        if kind in ("text", "auto"):
            self._set_active(self._text_backend)
            return
        backend, reason = self._ensure_webengine()
        if backend is not None:
            self._set_active(backend)
            return
        # WebEngine niedostępny/awaria przy jawnym wyborze → lekki backend + oferta.
        self._set_active(self._text_backend)
        self._show_fallback(forced=True, reason=reason)

    def _ensure_webengine(self) -> tuple[PreviewBackend | None, str]:
        """Zwraca (dokładny backend, "") albo (None, powód) — bez wywracania GUI."""
        if self._webengine_backend is not None:
            return self._webengine_backend, ""
        probe = probe_webengine()
        if not probe.available:
            return None, probe.reason
        try:
            backend: PreviewBackend = WebEnginePreviewBackend(theme=self._palette)
        except WebEngineInitError as exc:
            return None, str(exc)
        backend.open_external.connect(self.open_external)
        backend.diagnostics.connect(self.diagnostics)
        self._webengine_backend = backend
        return backend, ""

    def _show_fallback(self, *, forced: bool, reason: str) -> None:
        """Pokazuje czytelną diagnostykę fallbacku po nieudanym wyborze dokładnego."""
        self.fallback_label.setText(_("Nie udało się uruchomić dokładnego podglądu."))
        self.use_fast_button.setVisible(forced)
        self.fallback_label.setVisible(True)
        logger.info("Fallback podglądu na tor tekstowy: %s", reason or "brak WebEngine")
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.PREVIEW_LIMIT,
                message=_("Użyto szybkiego podglądu zamiast dokładnego."),
            )
        )

    def _set_active(self, backend: PreviewBackend) -> None:
        """Podmienia aktywny backend w ciele i re-renderuje ostatni snapshot."""
        if backend is self._active:
            self._update_status()
            return
        if self._active.kind is BackendKind.WEBENGINE:
            self._active.set_session(None)
        self._body_layout.removeWidget(self._active)
        self._active.hide()
        if self._body_layout.indexOf(backend) == -1:
            self._body_layout.addWidget(backend)
        self._active = backend
        backend.show()
        self._update_status()
        if self._last_snapshot is not None:
            backend.set_session(self._session)
            self._render_snapshot_into(backend, self._last_snapshot)

    def _update_status(self) -> None:
        """Aktualizuje etykietę statusu aktywnego backendu."""
        name = (
            _("Dokładny (WebEngine)")
            if self._active.kind is BackendKind.WEBENGINE
            else _("Szybki (Qt)")
        )
        self.status_label.setText(_("Backend: {name}").format(name=name))

    # ── Renderowanie / sesja ────────────────────────────────────────────────--

    def render_document(self, xhtml: str, epub: Epub | None, internal_path: str | None) -> None:
        """Buduje nowy snapshot (rosnąca generacja) i renderuje go w aktywnym backendzie.

        Nazwa nie brzmi ``render`` — ``QWidget.render`` to zajęta metoda rysująca.
        """
        self._generation += 1
        snapshot = PreviewSnapshot(
            xhtml=xhtml,
            epub=epub,
            internal_path=internal_path,
            generation_id=self._generation,
        )
        self._last_snapshot = snapshot
        self._active.set_session(self._session)
        self._render_snapshot_into(self._active, snapshot)

    def _render_snapshot_into(self, backend: PreviewBackend, snapshot: PreviewSnapshot) -> None:
        """Jedno miejsce liczenia renderów (motyw nie może go zwiększać)."""
        self._render_count += 1
        backend.render_snapshot(snapshot)

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia bieżącą sesję i przekazuje ją do aktywnego backendu."""
        previous = self._session
        if previous is not None and previous is not session:
            previous.close()
        self._session = session
        self._text_backend.set_session(session)
        if self._webengine_backend is not None:
            self._webengine_backend.set_session(session)

    # ── Motyw ──────────────────────────────────────────────────────────────────

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje chrome i backendy BEZ ponownego renderu treści książki."""
        self._palette = palette
        self._text_backend.set_theme(palette)
        if self._webengine_backend is not None:
            self._webengine_backend.set_theme(palette)
        self._style_chrome()

    def _style_chrome(self) -> None:
        """Koloruje komunikat fallbacku kolorem ostrzeżenia z palety (bez hardcodu)."""
        self.fallback_label.setStyleSheet(f"QLabel {{ color: {self._palette.amber}; }}")

    # ── Cykl życia ─────────────────────────────────────────────────────────────

    def dispose(self) -> None:
        """Unieważnia sesję i zwalnia oba backendy podglądu."""
        if self._session is not None:
            self._session.close()
            self._session = None
        self._text_backend.set_session(None)
        self._text_backend.dispose()
        if self._webengine_backend is not None:
            self._webengine_backend.dispose()


def _backend_label(value: str) -> str:
    """Lokalizowana etykieta pozycji selektora backendu."""
    return {
        "auto": _("Auto"),
        "webengine": _("Dokładny"),
        "text": _("Szybki"),
    }.get(value, value)
