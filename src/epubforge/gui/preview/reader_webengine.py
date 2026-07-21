"""WebEngine-owa realizacja profili, stron, diagnostyki i screenshotów."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QScrollArea

from epubforge.gui.preview.backend import PreviewSnapshot, PreviewState
from epubforge.gui.preview.quality import QUALITY_SCRIPT, parse_quality_report
from epubforge.gui.preview.reader import (
    ComparisonMode,
    PublicationLayout,
    ReaderProfile,
    UserStyleSettings,
    build_reader_layers,
    default_profile,
    reader_payload,
)
from epubforge.gui.preview.webengine_state import (
    APP_WORLD,
    CAPTURE_SCRIPT,
    READER_STATE_SCRIPT,
    state_from_js,
)
from epubforge.i18n import _


class ReaderWebEngineMixin:
    """Metody symulatora dla hosta posiadającego bezpieczną stronę WebEngine."""

    _page: Any
    _view: Any
    _profile: Any
    _viewport_frame: QScrollArea
    _last_snapshot: PreviewSnapshot | None
    _last_state: PreviewState
    _expected_generation: int
    reader_state_changed: Any
    quality_diagnostics: Any
    cache_changed: Any
    restore_state: Callable[[PreviewState], None]

    def _init_reader_engine(self) -> None:
        self._reader_profile = default_profile()
        self._user_style = self._reader_profile.user_style
        self._comparison = ComparisonMode.PUBLISHER_USER
        self._publication_layout = PublicationLayout()
        self._reader_simulation_enabled = False

    def set_reader_simulation(
        self,
        profile: ReaderProfile,
        user_style: UserStyleSettings,
        comparison: ComparisonMode,
    ) -> None:
        self._reader_simulation_enabled = True
        self._reader_profile = profile.normalized()
        self._user_style = user_style.normalized()
        self._comparison = comparison
        self._resize_viewport()
        if self._last_snapshot is None:
            self._emit_reader_state()
            return
        expected = self._expected_generation

        def captured(value: Any) -> None:
            if expected == self._expected_generation:
                self._last_state = state_from_js(value, self._last_state)
                self._apply_reader_layers()

        self._page.runJavaScript(CAPTURE_SCRIPT, APP_WORLD, captured)

    def navigate_preview_page(self, delta: int) -> None:
        if self._publication_layout.fixed_layout or self._reader_profile.flow.value != "pages":
            self.reader_state_changed.emit(
                {"limitation": _("Nawigacja stron podglądu dotyczy tylko reflowable pages.")}
            )
            return
        rtl = self._publication_layout.page_progression == "rtl" or (
            self._publication_layout.page_progression == "default"
            and self._publication_layout.document_direction == "rtl"
        )
        script = f"""
        (() => {{
          const sign = {(-1 if rtl else 1)};
          const max = Math.max(0, document.documentElement.scrollWidth - innerWidth);
          let target = scrollX + ({int(delta)} * innerWidth * sign);
          target = Math.max(-max, Math.min(max, target));
          scrollTo({{left: target, top: 0, behavior: 'auto'}});
          return true;
        }})()
        """
        self._page.runJavaScript(script, APP_WORLD, lambda _value: self._emit_reader_state())

    def jump_to_current_element(self) -> None:
        self._page.runJavaScript(
            "document.querySelector('[data-epubforge-active-node]')?.scrollIntoView({block:'center',inline:'center'})",
            APP_WORLD,
            lambda _value: self._emit_reader_state(),
        )

    def run_quality_diagnostics(
        self, *, min_font_px: float = 12.0, min_line_height: float = 1.1, accessibility: bool = True
    ) -> None:
        expected = self._expected_generation
        script = f"JSON.stringify({QUALITY_SCRIPT}({float(min_font_px)},{float(min_line_height)},{str(bool(accessibility)).lower()}))"

        def diagnosed(value: Any) -> None:
            if expected != self._expected_generation:
                return
            try:
                report = _decode_json_object(value)
            except (TypeError, ValueError):
                report = {"issues": []}
            self.quality_diagnostics.emit(parse_quality_report(report))

        self._page.runJavaScript(script, APP_WORLD, diagnosed)

    def export_viewport(self, path: str) -> bool:
        if not path:
            return False
        hide = """
        (() => {
          const ids = ['epubforge-dom-selection-style','epubforge-css-match-style'];
          window.__epubforgeScreenshotStyles = ids.map(id => {
            const node = document.getElementById(id);
            if (!node) return null;
            const disabled = node.disabled;
            node.disabled = true;
            return {id, disabled};
          }).filter(Boolean);
        })()
        """
        restore = """
        (window.__epubforgeScreenshotStyles || []).forEach(item => {
          const node = document.getElementById(item.id);
          if (node) node.disabled = item.disabled;
        });
        delete window.__epubforgeScreenshotStyles;
        """

        def capture(_value: Any) -> None:
            def save_and_restore() -> None:
                self._view.grab().save(path, "PNG")
                self._page.runJavaScript(restore, APP_WORLD)

            QTimer.singleShot(0, save_and_restore)

        self._page.runJavaScript(hide, APP_WORLD, capture)
        return True

    def clear_preview_cache(self) -> None:
        self._profile.clearHttpCache()
        self.cache_changed.emit({"entries": 0, "bytes": 0, "http_cache": "disabled"})

    def _resize_viewport(self) -> None:
        profile = self._reader_profile.normalized()
        self._view.setFixedSize(profile.width, profile.height)
        self._viewport_frame.setToolTip(
            _("Viewport {width}x{height} CSS px · DPR {dpr} (symulacyjne)").format(
                width=profile.width, height=profile.height, dpr=f"{profile.device_pixel_ratio:g}"
            )
        )

    def _apply_reader_layers(self) -> None:
        if not self._reader_simulation_enabled:
            self._emit_reader_state()
            return
        layers = build_reader_layers(
            self._reader_profile, self._publication_layout, self._user_style, self._comparison
        )
        script = f"""
        (() => {{
          const ensure = id => {{
            let node = document.getElementById(id);
            if (!node) {{ node = document.createElement('style'); node.id = id; document.head.appendChild(node); }}
            return node;
          }};
          ensure('epubforge-reader-simulator-layer').textContent = {json.dumps(layers.simulator_css)};
          ensure('epubforge-reader-user-layer').textContent = {json.dumps(layers.user_css)};
          const disabled = {str(layers.publisher_disabled).lower()};
          for (const sheet of Array.from(document.styleSheets)) {{
            const owner = sheet.ownerNode;
            if (!owner || (owner.id && owner.id.startsWith('epubforge-'))) continue;
            owner.disabled = disabled;
          }}
          document.documentElement.dataset.epubforgeLayout = {json.dumps(self._publication_layout.layout.value)};
          document.documentElement.dataset.epubforgeFlow = {json.dumps("fixed" if self._publication_layout.fixed_layout else self._reader_profile.flow.value)};
          document.documentElement.dataset.epubforgeProgression = {json.dumps(self._publication_layout.page_progression)};
          return true;
        }})()
        """

        def applied(_value: Any) -> None:
            self.restore_state(self._last_state)
            self._emit_reader_state()

        self._page.runJavaScript(script, APP_WORLD, applied)

    def _emit_reader_state(self) -> None:
        expected = self._expected_generation

        def reported(value: Any) -> None:
            if expected == self._expected_generation:
                state = dict(value) if isinstance(value, dict) else {}
                state.update(self._reader_payload())
                self.reader_state_changed.emit(state)

        self._page.runJavaScript(READER_STATE_SCRIPT, APP_WORLD, reported)

    def _reader_payload(self) -> dict[str, Any]:
        payload = reader_payload(
            self._reader_profile,
            self._publication_layout,
            self._user_style,
            self._comparison,
        )
        payload["enabled"] = self._reader_simulation_enabled
        if not self._reader_simulation_enabled:
            payload.update(
                columns_enabled=False,
                publisher_disabled=False,
                overrides={},
                limitations=[],
            )
        return payload


def _decode_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise TypeError(type(value).__name__)
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("odpowiedź JSON nie jest obiektem")
    return decoded
