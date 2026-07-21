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
from collections.abc import Mapping
from dataclasses import replace

from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt.theme import current_palette
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from epubforge.core import Epub, Tool
from epubforge.gui.preview.availability import probe_webengine
from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
    PreviewStatus,
)
from epubforge.gui.preview.controller import PreviewController
from epubforge.gui.preview.dom_mapping import SourceLocation, nearest_node_for_line, source_location
from epubforge.gui.preview.preinit import preview_scheme_registered
from epubforge.gui.preview.reader_ui import ReaderUiMixin
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


class BookPreview(ReaderUiMixin, QWidget):
    """Pasek wyboru backendu + aktywny tor podglądu (lekki albo dokładny).

    Sygnały:
        open_external: żądanie otwarcia bieżącego pliku w narzędziu (klucz).
        diagnostics: zdarzenie diagnostyczne z backendu (:class:`DiagnosticEvent`).
    """

    open_external = Signal(str)
    diagnostics = Signal(object)
    source_requested = Signal(object)
    element_inspected = Signal(object)
    css_preview_result = Signal(object)
    backend_changed = Signal(object)

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
        self._controller = PreviewController()
        self._status = PreviewStatus.READY
        self._render_count = 0
        self._last_snapshot: PreviewSnapshot | None = None
        self._session: PreviewSession | None = None
        self._webengine_backend: PreviewBackend | None = None
        self._init_reader_ui_state()

        self._build_ui()
        self.diagnostics.connect(self._show_diagnostic)

        # Lekki backend istnieje zawsze (fallback). Dokładny tworzymy leniwie.
        self._text_backend = TextDocumentPreviewBackend(tools=self._tools, theme=self._palette)
        self._text_backend.open_external.connect(self.open_external)
        self._text_backend.source_requested.connect(self.source_requested)
        self._text_backend.diagnostics.connect(self.diagnostics)
        self._text_backend.status_changed.connect(self._on_status_changed)
        self._text_backend.element_inspected.connect(self.element_inspected)
        self._text_backend.css_preview_result.connect(self.css_preview_result)
        self._text_backend.reader_state_changed.connect(self._on_reader_state)
        self._text_backend.quality_diagnostics.connect(self._on_quality_diagnostics)
        self._text_backend.cache_changed.connect(self._on_cache_changed)
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

        self.reload_button = QPushButton(_("Przeładuj dokładnie"))
        self.reload_button.setToolTip(_("Wymuś pełne przeładowanie bieżącego dokumentu"))
        self.reload_button.clicked.connect(self._reload_exact)
        bar.addWidget(self.reload_button)

        bar.addStretch(0)
        layout.addLayout(bar)

        self._build_reader_ui(layout)

        self._body = QWidget()
        self._body.setObjectName("previewBody")
        self._body_layout = QHBoxLayout(self._body)
        self._body_layout.setContentsMargins(12, 12, 12, 12)
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

    @property
    def generation_id(self) -> int:
        """Numer generacji używany w stabilnej tożsamości reguły inspektora."""
        return self._generation

    @property
    def current_document(self) -> str | None:
        """Dokument ostatniego poprawnie zbudowanego snapshotu podglądu."""
        return self._last_snapshot.internal_path if self._last_snapshot is not None else None

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
        """Ustawia wybrany backend; Auto preferuje WebEngine i bezpiecznie fallbackuje."""
        if persist:
            self._settings.backend = kind
        self.fallback_label.setVisible(False)
        self.use_fast_button.setVisible(False)

        if kind == "text":
            self._set_active(self._text_backend)
            return
        backend, reason = self._ensure_webengine()
        if backend is not None:
            self._set_active(backend)
            return
        # WebEngine niedostępny/awaria przy jawnym wyborze → lekki backend + oferta.
        self._set_active(self._text_backend)
        self._show_fallback(forced=kind == "webengine", reason=reason)

    def _ensure_webengine(self) -> tuple[PreviewBackend | None, str]:
        """Zwraca (dokładny backend, "") albo (None, powód) — bez wywracania GUI."""
        if self._webengine_backend is not None:
            return self._webengine_backend, ""
        if not preview_scheme_registered():
            return None, "schemat podglądu nie został zarejestrowany przed QApplication"
        probe = probe_webengine()
        if not probe.available:
            return None, probe.reason
        try:
            backend: PreviewBackend = WebEnginePreviewBackend(theme=self._palette)
        except WebEngineInitError as exc:
            return None, str(exc)
        backend.open_external.connect(self.open_external)
        backend.source_requested.connect(self.source_requested)
        backend.diagnostics.connect(self.diagnostics)
        backend.status_changed.connect(self._on_status_changed)
        backend.fallback_requested.connect(self._on_renderer_fallback)
        backend.element_inspected.connect(self.element_inspected)
        backend.css_preview_result.connect(self.css_preview_result)
        backend.reader_state_changed.connect(self._on_reader_state)
        backend.quality_diagnostics.connect(self._on_quality_diagnostics)
        backend.cache_changed.connect(self._on_cache_changed)
        backend.set_reader_simulation(self._reader_profile, self._user_style, self._comparison)
        self._webengine_backend = backend
        return backend, ""

    def _show_diagnostic(self, event: DiagnosticEvent) -> None:
        """Pokazuje bezpieczne pola ostatniej diagnostyki zasobu."""
        category = {
            DiagnosticCategory.BOOK_ERROR: _("Błąd książki"),
            DiagnosticCategory.SECURITY: _("Blokada bezpieczeństwa"),
            DiagnosticCategory.PREVIEW_LIMIT: _("Ograniczenie podglądu"),
            DiagnosticCategory.SIMULATOR_LIMIT: _("Ograniczenie symulatora"),
            DiagnosticCategory.QUALITY: _("Ostrzeżenie jakości"),
        }[event.category]
        details = [event.message, _("Kategoria: {category}").format(category=category)]
        if event.problem_kind:
            details.append(_("Rodzaj: {kind}").format(kind=event.problem_kind))
        if event.source_url:
            details.append(_("URL: {url}").format(url=event.source_url))
        if event.internal_path:
            details.append(_("Zasób: {path}").format(path=event.internal_path))
        if event.requester:
            details.append(_("Żądający: {path}").format(path=event.requester))
        self.fallback_label.setText("\n".join(details))
        self.fallback_label.setVisible(True)

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
        if backend.kind is not BackendKind.WEBENGINE and self._comparison_backend is not None:
            self.compare_profiles_button.setChecked(False)
        self._body_layout.removeWidget(self._active)
        self._active.hide()
        if self._body_layout.indexOf(backend) == -1:
            self._body_layout.addWidget(backend)
        self._active = backend
        backend.show()
        if backend.kind is BackendKind.WEBENGINE:
            backend.set_reader_simulation(self._reader_profile, self._user_style, self._comparison)
        self.backend_changed.emit(backend.kind)
        self._update_status()
        if self._last_snapshot is not None:
            backend.set_session(self._session)
            self._render_snapshot_into(backend, self._last_snapshot)

    def _update_status(self) -> None:
        """Aktualizuje backend i stan bieżącego renderu."""
        name = _("Dokładny") if self._active.kind is BackendKind.WEBENGINE else _("Szybki")
        state = {
            PreviewStatus.READY: _("Aktualny"),
            PreviewStatus.RENDERING: _("Renderowanie"),
            PreviewStatus.LAST_GOOD: _("Ostatnia poprawna wersja"),
            PreviewStatus.FALLBACK: _("Fallback"),
            PreviewStatus.ERROR: _("Błąd"),
        }[self._status]
        self.status_label.setText(_("{backend} · {status}").format(backend=name, status=state))

    def _on_status_changed(self, status: PreviewStatus) -> None:
        """Odbiera stan wyłącznie od aktywnego backendu."""
        if self.sender() is self._active:
            self._status = status
            self._update_status()

    def _on_renderer_fallback(self, reason: str) -> None:
        """Przechodzi na lekki backend po ponownej awarii renderera."""
        self._set_active(self._text_backend)
        self._status = PreviewStatus.FALLBACK
        self._update_status()
        self._show_fallback(forced=False, reason=reason)

    def _reload_exact(self) -> None:
        """Wymusza pełny reload ostatniego snapshotu."""
        if self._last_snapshot is None:
            return
        snapshot = replace(self._last_snapshot, css_only=False)
        self._last_snapshot = snapshot
        self._render_snapshot_into(self._active, snapshot)

    # ── Renderowanie / sesja ────────────────────────────────────────────────--

    def render_document(
        self,
        xhtml: str,
        epub: Epub | None,
        internal_path: str | None,
        *,
        dirty: Mapping[str, str | bytes] | None = None,
        media_types: Mapping[str, str] | None = None,
    ) -> None:
        """Buduje snapshot bieżącego edytora, dirty i bufora Epub."""
        if epub is None or internal_path is None or self._session is None:
            self._generation += 1
            snapshot = PreviewSnapshot(xhtml, epub, internal_path, self._generation)
            self._last_snapshot = snapshot
            target = self._text_backend if epub is None else self._active
            self._render_snapshot_into(target, snapshot)
            if self._comparison_backend is not None and target is self._active:
                self._render_snapshot_into(self._comparison_backend, snapshot)
            return
        result = self._controller.build(
            epub=epub,
            session=self._session,
            current_path=internal_path,
            current_text=xhtml,
            dirty=dirty or {},
            media_types=media_types or {},
        )
        if result.snapshot is None:
            self._status = PreviewStatus.LAST_GOOD
            self._update_status()
            if result.diagnostic is not None:
                self.diagnostics.emit(result.diagnostic)
                self.fallback_label.setText(result.diagnostic.message)
                self.fallback_label.setVisible(True)
            return
        snapshot = result.snapshot
        self._generation = snapshot.generation_id
        self._last_snapshot = snapshot
        self.fallback_label.setVisible(False)
        self._active.set_session(self._session)
        self._render_snapshot_into(self._active, snapshot)
        if self._comparison_backend is not None:
            self._comparison_backend.set_session(self._session)
            self._render_snapshot_into(self._comparison_backend, snapshot)

    def _render_snapshot_into(self, backend: PreviewBackend, snapshot: PreviewSnapshot) -> None:
        """Jedno miejsce liczenia renderów (motyw nie może go zwiększać)."""
        self._render_count += 1
        backend.render_snapshot(snapshot)

    def focus_source_line(self, internal_path: str, line: int) -> None:
        """Mapuje linię kursora na najgłębszy element aktualnej generacji."""
        snapshot = self._last_snapshot
        generation = snapshot.generation if snapshot is not None else None
        if generation is None:
            return
        node = nearest_node_for_line(generation.source_map, internal_path, line)
        if node is None:
            return
        if self._session is not None:
            self._session.select(internal_path, node.node_id)
        self._active.focus_node(node.node_id)
        if self._comparison_backend is not None:
            self._comparison_backend.focus_node(node.node_id)

    def inspect_element(self, node_id: str | None = None) -> None:
        """Deleguje inspekcję do aktywnego backendu bez ujawniania WebEngine widgetowi."""
        self._active.inspect_element(node_id)

    def preview_css_rule(
        self, selector: str, rule_text: str, *, current_element: bool = False
    ) -> None:
        """Deleguje bezźródłową warstwę preview do aktywnego backendu."""
        self._active.preview_css_rule(selector, rule_text, current_element=current_element)

    def clear_css_preview(self) -> None:
        """Usuwa warstwę preview z aktywnego renderera."""
        self._active.clear_css_preview()

    def highlight_matches(self, selector: str) -> None:
        """Podświetla dopasowania przez aktywny silnik renderujący."""
        self._active.highlight_matches(selector)

    def source_location_for_node(self, node_id: str) -> SourceLocation | None:
        """Rozwiązuje techniczny node wyłącznie w mapie aktualnej generacji."""
        snapshot = self._last_snapshot
        generation = snapshot.generation if snapshot is not None else None
        node = generation.source_map.get(node_id) if generation is not None else None
        return source_location(node) if node is not None else None

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia bieżącą sesję i przekazuje ją do aktywnego backendu."""
        previous = self._session
        if previous is not None and previous is not session:
            previous.close()
        self._session = session
        if previous is not session:
            self._controller.clear()
        self._text_backend.set_session(session)
        if self._webengine_backend is not None:
            self._webengine_backend.set_session(session)
        if self._comparison_backend is not None:
            self._comparison_backend.set_session(session)

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
        self._body.setStyleSheet(f"QWidget#previewBody {{ background: {self._palette.bg2}; }}")

    # ── Cykl życia ─────────────────────────────────────────────────────────────

    def dispose(self) -> None:
        """Unieważnia sesję i zwalnia oba backendy podglądu."""
        if self._session is not None:
            self._session.close()
            self._session = None
        self._text_backend.set_session(None)
        self._text_backend.dispose()
        self._dispose_comparison_backend()
        if self._webengine_backend is not None:
            self._webengine_backend.dispose()


def _backend_label(value: str) -> str:
    """Lokalizowana etykieta pozycji selektora backendu."""
    return {
        "auto": _("Auto"),
        "webengine": _("Dokładny"),
        "text": _("Szybki"),
    }.get(value, value)
