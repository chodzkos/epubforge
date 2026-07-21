"""Dokładny backend podglądu z pełnymi zasobami i odpornym rendererem."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import replace
from typing import Any, cast

from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt.theme import current_palette
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
    PreviewState,
    PreviewStatus,
)
from epubforge.gui.preview.css_bridge import INSPECT_SCRIPT
from epubforge.gui.preview.dom_mapping import NODE_ATTRIBUTE, source_location
from epubforge.gui.preview.reader_webengine import ReaderWebEngineMixin
from epubforge.gui.preview.rewrite import safe_source_url
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.webengine_state import (
    APP_WORLD as _APP_WORLD,
)
from epubforge.gui.preview.webengine_state import (
    CAPTURE_SCRIPT as _CAPTURE_SCRIPT,
)
from epubforge.gui.preview.webengine_state import (
    state_from_js as _state_from_js,
)
from epubforge.i18n import _

logger = logging.getLogger(__name__)
_ACTIVE_ATTRIBUTE = "data-epubforge-active-node"


def _decode_json_object(value: Any) -> dict[str, Any]:
    """Dekoduje stabilny transport obiektów JS niezależnie od konwersji QVariant."""
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    if not isinstance(value, str):
        raise TypeError(f"oczekiwano JSON string, otrzymano {type(value).__name__}")
    decoded: Any = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("odpowiedź JSON nie jest obiektem")
    return cast(dict[str, Any], decoded)


class WebEngineInitError(RuntimeError):
    """Sygnalizuje, że backend WebEngine nie mógł się zainicjalizować."""


class WebEnginePreviewBackend(ReaderWebEngineMixin, PreviewBackend):
    """QWebEngineView z wersjonowanymi zasobami i bezpiecznym fallbackiem."""

    def __init__(self, parent: QWidget | None = None, *, theme: Palette | None = None) -> None:
        super().__init__(parent)
        self.kind = BackendKind.WEBENGINE
        self._session: PreviewSession | None = None
        self._palette = theme if theme is not None else current_palette()
        self._last_snapshot: PreviewSnapshot | None = None
        self._last_state = PreviewState()
        self._expected_generation = 0
        self._renderer_recovery_used = False
        self._bridge_token = secrets.token_hex(16)
        self._init_reader_engine()
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
            self._page = SecurePreviewPage(
                self._profile, self._registry, self, bridge_token=self._bridge_token
            )
            harden_page_settings(self._page.settings())
            self._page.loadFinished.connect(self._on_load_finished)
            self._page.renderProcessTerminated.connect(self._on_renderer_terminated)
            self._page.external_navigation.connect(self._on_external_navigation)
            self._handler.diagnostics.connect(self.diagnostics)
            self._page.dom_node_activated.connect(self._on_dom_node_activated)
            self._view = QWebEngineView(self)
            self._view.setPage(self._page)
        except Exception as exc:
            raise WebEngineInitError(f"Bezpieczny profil QWebEngineView: {exc}") from exc
        self._viewport_frame = QScrollArea(self)
        self._viewport_frame.setWidgetResizable(False)
        self._viewport_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewport_frame.setWidget(self._view)
        layout.addWidget(self._viewport_frame)
        self._resize_viewport()

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia sesję i czyści cache po zamknięciu lub zmianie książki."""
        changed = session is not self._session
        self._session = session
        if changed:
            self._renderer_recovery_used = False
            self._last_snapshot = None
            self._last_state = PreviewState()
        if session is None or session.closed:
            self._registry.clear()
            self._view.setUrl(QUrl("about:blank"))

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Aktywuje gotową generację; CSS podmienia bez przeładowania dokumentu."""
        generation = snapshot.generation
        if self._session is None or self._session.closed or generation is None:
            self._emit_error(_("Brak aktywnej sesji publikacji dla dokładnego podglądu."))
            return
        self._registry.activate(generation)
        self._expected_generation = generation.generation_id
        self._publication_layout = snapshot.publication_layout
        self.status_changed.emit(PreviewStatus.RENDERING)
        if snapshot.css_only and self._last_snapshot is not None and snapshot.changed_resource:
            self._update_stylesheet(snapshot)
        else:
            self._capture_then_load(snapshot)

    def capture_state(self) -> PreviewState:
        """Zwraca ostatni asynchronicznie zapamiętany stan DOM i scrolla."""
        return self._last_state

    def restore_state(self, state: PreviewState) -> None:
        """Odtwarza node/id/ścieżkę/tekst/fragment/scroll w ustalonej kolejności."""
        self._last_state = state
        payload = json.dumps(state.__dict__)
        script = f"""
        (() => {{
          const s = {payload};
          let n = s.node_id && document.querySelector('[data-epubforge-node-id="' + CSS.escape(s.node_id) + '"]');
          if (!n && s.original_id) n = document.getElementById(s.original_id);
          if (!n && s.dom_path) {{ try {{ n = document.querySelector(s.dom_path); }} catch (_) {{}} }}
          if (!n && s.text_fragment) n = Array.from(document.querySelectorAll('body *')).find(e => (e.textContent || '').includes(s.text_fragment));
          if (!n && s.active_fragment) n = document.getElementById(s.active_fragment);
          if (n) n.scrollIntoView({{block: 'center'}});
          else {{
            const max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
            scrollTo(0, max * Math.max(0, Math.min(1, s.scroll_ratio || 0)));
          }}
        }})()
        """
        self._page.runJavaScript(script, _APP_WORLD)

    def focus_node(self, node_id: str) -> None:
        """Przewija podgląd do elementu wskazanego przez kursor edytora."""
        snapshot = self._last_snapshot
        generation = snapshot.generation if snapshot is not None else None
        if generation is None or node_id not in generation.source_map:
            return
        if self._session is not None:
            self._session.select(generation.current_document, node_id)
        self._last_state = replace(self._last_state, node_id=node_id)
        script = f"""
        (() => {{
          const n = document.querySelector('[{NODE_ATTRIBUTE}="' + CSS.escape({json.dumps(node_id)}) + '"]');
          if (!n) return false;
          document.querySelectorAll('[{_ACTIVE_ATTRIBUTE}]').forEach(e => e.removeAttribute('{_ACTIVE_ATTRIBUTE}'));
          n.setAttribute('{_ACTIVE_ATTRIBUTE}', '');
          n.scrollIntoView({{block: 'center', behavior: 'auto'}});
          return true;
        }})()
        """
        self._page.runJavaScript(script, _APP_WORLD)

    def inspect_element(self, node_id: str | None = None) -> None:
        """Zwraca CSSOM, computed style i box model aktualnej generacji."""
        expected = self._expected_generation
        script = f"JSON.stringify({INSPECT_SCRIPT}({json.dumps(node_id)}))"

        def inspected(value: Any) -> None:
            if expected != self._expected_generation:
                return
            try:
                payload = _decode_json_object(value)
            except (TypeError, ValueError) as exc:
                logger.warning("Niepoprawny raport JSON inspektora WebEngine: %s", exc)
                payload = {"available": False, "error": f"WebEngine JSON: {exc}"}
            payload["reader_simulation"] = self._reader_payload()
            self.element_inspected.emit(payload)

        self._page.runJavaScript(script, _APP_WORLD, inspected)

    def preview_css_rule(
        self, selector: str, rule_text: str, *, current_element: bool = False
    ) -> None:
        """Waliduje regułę w CSSOM i dopiero potem podmienia ostatnią dobrą warstwę."""
        expected = self._expected_generation
        script = f"""
        JSON.stringify((() => {{
          const originalSelector = {json.dumps(selector)};
          const input = {json.dumps(rule_text)};
          const selected = document.querySelector('[{_ACTIVE_ATTRIBUTE}]');
          const open = input.indexOf('{{'), close = input.lastIndexOf('}}');
          if (open < 0 || close <= open) return {{ok:false, error:'Niepełna reguła CSS.'}};
          const selector = {str(current_element).lower()}
            ? (selected ? '[{NODE_ATTRIBUTE}="' + selected.getAttribute('{NODE_ATTRIBUTE}') + '"]' : '')
            : originalSelector;
          if (!selector) return {{ok:false, error:'Nie zaznaczono bieżącego elementu.'}};
          const candidate = selector + ' {{' + input.slice(open + 1, close) + '}}';
          const probe = document.createElement('style');
          probe.setAttribute('data-epubforge-preview-probe', '');
          document.head.appendChild(probe);
          try {{ probe.sheet.insertRule(candidate, 0); }}
          catch (error) {{ probe.remove(); return {{ok:false, error:String(error)}}; }}
          probe.remove();
          let layer = document.getElementById('epubforge-css-preview-layer');
          if (!layer) {{ layer = document.createElement('style'); layer.id = 'epubforge-css-preview-layer'; document.head.appendChild(layer); }}
          layer.textContent = candidate;
          let matches = 0;
          try {{ matches = document.querySelectorAll(selector).length; }} catch (_) {{}}
          return {{ok:true, matches, selector, order_warning:true, current_element:{str(current_element).lower()}}};
        }})())
        """

        def previewed(value: Any) -> None:
            if expected != self._expected_generation:
                return
            try:
                payload = _decode_json_object(value)
            except (TypeError, ValueError) as exc:
                logger.warning("Niepoprawny wynik JSON podglądu CSS WebEngine: %s", exc)
                payload = {"ok": False, "error": f"WebEngine JSON: {exc}"}
            self.css_preview_result.emit(payload)
            if payload.get("ok"):
                self.inspect_element()

        self._page.runJavaScript(script, _APP_WORLD, previewed)

    def clear_css_preview(self) -> None:
        """Usuwa warstwę edycji tymczasowej bez dotykania źródła EPUB."""
        self._page.runJavaScript(
            "document.getElementById('epubforge-css-preview-layer')?.remove()", _APP_WORLD
        )

    def highlight_matches(self, selector: str) -> None:
        """Podświetla wszystkie dopasowania selektora w kopii renderowanej."""
        accent = json.dumps(self._palette.accent)
        script = f"""
        (() => {{
          document.querySelectorAll('[data-epubforge-css-match]').forEach(e => e.removeAttribute('data-epubforge-css-match'));
          let style = document.getElementById('epubforge-css-match-style');
          if (!style) {{ style = document.createElement('style'); style.id = 'epubforge-css-match-style'; document.head.appendChild(style); }}
          style.textContent = '[data-epubforge-css-match] {{ outline: 2px dashed ' + {accent} + ' !important; }}';
          try {{ const nodes = document.querySelectorAll({json.dumps(selector)}); nodes.forEach(e => e.setAttribute('data-epubforge-css-match','')); return nodes.length; }}
          catch (_) {{ return 0; }}
        }})()
        """
        self._page.runJavaScript(script, _APP_WORLD)

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje wyłącznie neutralne otoczenie, bez reloadu książki."""
        self._palette = palette
        self.setStyleSheet(f"WebEnginePreviewBackend {{ background-color: {palette.bg}; }}")
        self._install_dom_bridge()

    def dispose(self) -> None:
        """Unieważnia origin i zwalnia prywatny profil oraz renderer."""
        self._registry.clear()
        self._profile.removeUrlSchemeHandler(self._handler)
        self._view.stop()
        self._page.deleteLater()
        self._view.deleteLater()
        self._profile.deleteLater()

    def _capture_then_load(self, snapshot: PreviewSnapshot) -> None:
        """Zapisuje stan starej strony, a następnie ładuje nową generację."""
        if self._last_snapshot is None:
            self._load_snapshot(snapshot)
            return
        expected = snapshot.generation_id

        def captured(value: Any) -> None:
            if expected == self._expected_generation:
                self._last_state = _state_from_js(value, self._last_state)
                self._load_snapshot(snapshot)

        self._page.runJavaScript(_CAPTURE_SCRIPT, _APP_WORLD, captured)

    def _load_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Ładuje dokument tylko, jeśli snapshot nadal jest najnowszy."""
        generation = snapshot.generation
        if generation is None or generation.generation_id != self._expected_generation:
            return
        self._last_snapshot = snapshot
        self._view.setUrl(QUrl(generation.document_url))

    def _update_stylesheet(self, snapshot: PreviewSnapshot) -> None:
        """Zapamiętuje stan i podmienia jeden arkusz bez reloadu DOM."""
        generation, path = snapshot.generation, snapshot.changed_resource
        if generation is None or path is None:
            self._fallback_full_reload(snapshot, "brak danych arkusza")
            return
        expected = generation.generation_id

        def captured(value: Any) -> None:
            if expected != self._expected_generation:
                return
            self._last_state = _state_from_js(value, self._last_state)
            self._swap_stylesheet(snapshot)

        self._page.runJavaScript(_CAPTURE_SCRIPT, _APP_WORLD, captured)

    def _swap_stylesheet(self, snapshot: PreviewSnapshot) -> None:
        """Podmienia wersjonowany href po zapisaniu scrolla i zaznaczenia."""
        generation, path = snapshot.generation, snapshot.changed_resource
        if generation is None or path is None:
            self._fallback_full_reload(snapshot, "brak danych arkusza")
            return
        script = f"""
        (() => {{
          const path = {json.dumps(path)};
          const href = {json.dumps(generation.resource_url(path))};
          const link = Array.from(document.querySelectorAll('link[rel~="stylesheet"]')).find(item => item.dataset.epubforgePath === path);
          if (!link) return false;
          link.href = href;
          return true;
        }})()
        """
        expected = generation.generation_id

        def updated(success: Any) -> None:
            if expected != self._expected_generation:
                return
            if success:
                self._last_snapshot = snapshot
                self._apply_reader_layers()
                self.status_changed.emit(PreviewStatus.READY)
                if snapshot.internal_path is not None:
                    self.document_ready.emit(snapshot.internal_path)
            else:
                self._fallback_full_reload(snapshot, "nie znaleziono linku arkusza")

        self._page.runJavaScript(script, _APP_WORLD, updated)

    def _fallback_full_reload(self, snapshot: PreviewSnapshot, reason: str) -> None:
        """Wykonuje kontrolowany reload po nieudanej aktualizacji częściowej."""
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.PREVIEW_LIMIT,
                message=_("Częściowe odświeżenie CSS nie powiodło się; przeładowano dokument."),
                problem_kind="css_reload_fallback",
                internal_path=snapshot.changed_resource,
                requester=snapshot.internal_path,
            )
        )
        logger.info("Fallback pełnego reloadu CSS: %s", reason)
        self._capture_then_load(snapshot)

    def _install_dom_bridge(self) -> None:
        """Instaluje idempotentny listener kliknięć i styl technicznego wyboru."""
        token = json.dumps(self._bridge_token)
        accent = json.dumps(self._palette.accent)
        script = f"""
        (() => {{
          let style = document.getElementById('epubforge-dom-selection-style');
          if (!style) {{
            style = document.createElement('style');
            style.id = 'epubforge-dom-selection-style';
            document.head.appendChild(style);
          }}
          style.textContent = '[{_ACTIVE_ATTRIBUTE}] {{ outline: 2px solid ' + {accent} + ' !important; outline-offset: 2px !important; }}';
          if (!window.__epubforgeNodeBridge) {{
            document.addEventListener('click', event => {{
              const target = event.target instanceof Element ? event.target : null;
              const node = target && target.closest('[{NODE_ATTRIBUTE}]');
              if (!node) return;
              const nodeId = node.getAttribute('{NODE_ATTRIBUTE}');
              if (!nodeId) return;
              document.querySelectorAll('[{_ACTIVE_ATTRIBUTE}]').forEach(e => e.removeAttribute('{_ACTIVE_ATTRIBUTE}'));
              node.setAttribute('{_ACTIVE_ATTRIBUTE}', '');
              console.info('epubforge-node:' + {token} + ':' + nodeId);
            }}, true);
            window.__epubforgeNodeBridge = true;
          }}
          return true;
        }})()
        """
        self._page.runJavaScript(script, _APP_WORLD)

    def _on_load_finished(self, success: bool) -> None:
        """Ignoruje spóźniony wynik i odtwarza stan po aktualnej generacji."""
        snapshot = self._last_snapshot
        if snapshot is None or snapshot.generation_id != self._expected_generation:
            return
        if success:
            self._install_dom_bridge()
            if self._reader_simulation_enabled:
                self._apply_reader_layers()
            else:
                self.restore_state(self._last_state)
                self._emit_reader_state()
            if self._last_state.node_id:
                self.inspect_element(self._last_state.node_id)
            self.status_changed.emit(PreviewStatus.READY)
            if snapshot.internal_path is not None:
                self.document_ready.emit(snapshot.internal_path)
            stats = self._session.cache_stats() if self._session is not None else None
            self.cache_changed.emit(
                {
                    "entries": stats.entries if stats is not None else 0,
                    "bytes": stats.bytes if stats is not None else 0,
                    "by_kind": stats.by_kind if stats is not None else {},
                    "http_cache": "disabled",
                }
            )
        else:
            self.status_changed.emit(PreviewStatus.LAST_GOOD)
            self.diagnostics.emit(
                DiagnosticEvent(
                    category=DiagnosticCategory.BOOK_ERROR,
                    message=_(
                        "Nie udało się wyrenderować nowej wersji; zachowano ostatnią poprawną."
                    ),
                    problem_kind="render_failed",
                    internal_path=snapshot.internal_path,
                    requester=snapshot.internal_path,
                )
            )

    def _on_renderer_terminated(self, status: object, exit_code: int) -> None:
        """Odtwarza renderer raz, po kolejnej awarii żąda lekkiego fallbacku."""
        self.status_changed.emit(PreviewStatus.ERROR)
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.PREVIEW_LIMIT,
                message=_("Proces renderera podglądu został zakończony."),
                problem_kind="renderer_terminated",
            )
        )
        logger.warning("Renderer WebEngine zakończony: %s (%d)", status, exit_code)
        if not self._renderer_recovery_used and self._last_snapshot is not None:
            self._renderer_recovery_used = True
            QTimer.singleShot(0, lambda: self._load_snapshot(self._last_snapshot))  # type: ignore[arg-type]
        else:
            self.status_changed.emit(PreviewStatus.FALLBACK)
            self.fallback_requested.emit(_("Renderer podglądu uległ ponownej awarii."))

    def _emit_error(self, message: str) -> None:
        """Emituje bezpieczny błąd przygotowania podglądu."""
        self.status_changed.emit(PreviewStatus.ERROR)
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.BOOK_ERROR, message=message, problem_kind="brak_sesji"
            )
        )

    def _on_dom_node_activated(self, node_id: str) -> None:
        """Rozwiązuje identyfikator wyłącznie w mapie aktualnej generacji."""
        snapshot = self._last_snapshot
        generation = snapshot.generation if snapshot is not None else None
        if generation is None:
            return
        node = generation.source_map.get(node_id)
        if node is None:
            return
        if self._session is not None:
            self._session.select(node.internal_path, node_id)
        self._last_state = replace(self._last_state, node_id=node_id)
        self.inspect_element(node_id)
        self.source_requested.emit(source_location(node))

    def _on_external_navigation(self, url: str) -> None:
        """Rejestruje blokadę linku bez automatycznego otwierania przeglądarki."""
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.SECURITY,
                message=_("Zablokowano nawigację poza publikację."),
                problem_kind="zewnetrzna_nawigacja",
                source_url=safe_source_url(url),
            )
        )
