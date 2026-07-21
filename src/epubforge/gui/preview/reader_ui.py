from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from chodzkos_gui_kit.palette import Palette
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.gui.preview.backend import (
    BackendKind,
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
)
from epubforge.gui.preview.dom_mapping import SourceLocation
from epubforge.gui.preview.quality import QualityIssue
from epubforge.gui.preview.reader import (
    READER_PROFILES,
    ComparisonMode,
    FlowMode,
    ReaderProfile,
    custom_profile_from_mapping,
    profile_by_key,
    user_style_from_mapping,
)
from epubforge.gui.preview.reader_settings_ui import ReaderSettingsUiMixin
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.webengine_backend import WebEngineInitError, WebEnginePreviewBackend
from epubforge.gui.widgets.horizontal_strip import HorizontalStrip
from epubforge.i18n import _

_QUALITY_ROLE = 0x0100


class ReaderUiMixin(ReaderSettingsUiMixin):
    _settings: PreviewSettings
    _palette: Palette
    _active: PreviewBackend
    _last_snapshot: PreviewSnapshot | None
    _session: PreviewSession | None
    _body_layout: QHBoxLayout
    _render_snapshot_into: Callable[[PreviewBackend, PreviewSnapshot], None]
    source_location_for_node: Callable[[str], SourceLocation | None]
    diagnostics: Any
    source_requested: Any

    def _init_reader_ui_state(self) -> None:
        saved = self._settings.profile
        self._reader_profile = (
            custom_profile_from_mapping(self._settings.custom_viewport)
            if saved == "custom"
            else profile_by_key(saved)
        )
        self._user_style = user_style_from_mapping(
            self._settings.user_style, self._reader_profile.user_style
        )
        self._comparison = ComparisonMode(self._settings.comparison)
        self._comparison_backend: PreviewBackend | None = None
        self._quality_issues: tuple[QualityIssue, ...] = ()

    def _build_reader_ui(self, layout: QVBoxLayout) -> None:
        bar = HorizontalStrip()
        bar.row.addWidget(QLabel(_("Profil czytnika:")))
        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip(
            _("Wybierz neutralny profil viewportu; nazwy nie udają silnika konkretnego urządzenia")
        )
        for key, profile in READER_PROFILES.items():
            self.profile_combo.addItem(_(profile.label), key)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        bar.row.addWidget(self.profile_combo)
        self.flow_combo = QComboBox()
        self.flow_combo.setToolTip(
            _("Wybierz przewijanie albo kontrolowane strony podglądu oparte na CSS columns")
        )
        self.flow_combo.addItem(_("Przewijanie"), FlowMode.SCROLL.value)
        self.flow_combo.addItem(_("Strony podglądu"), FlowMode.PAGES.value)
        self.flow_combo.currentIndexChanged.connect(self._on_flow_selected)
        bar.row.addWidget(self.flow_combo)
        self.previous_page_button = self._button(
            _("Poprzednia"),
            _("Przejdź do poprzedniej strony podglądu w trybie stron"),
            lambda: self._active.navigate_preview_page(-1),
        )
        self.next_page_button = self._button(
            _("Następna"),
            _("Przejdź do następnej strony podglądu w trybie stron"),
            lambda: self._active.navigate_preview_page(1),
        )
        self.current_element_button = self._button(
            _("Do elementu"),
            _("Przejdź do strony podglądu zawierającej aktualnie zaznaczony element"),
            lambda: self._active.jump_to_current_element(),
        )
        for button in (
            self.previous_page_button,
            self.next_page_button,
            self.current_element_button,
        ):
            bar.row.addWidget(button)
        self.page_label = QLabel(_("strona podglądu —"))
        self.page_label.setToolTip(
            _("Numer technicznej strony podglądu; nie jest to numer strony książki")
        )
        bar.row.addWidget(self.page_label)
        self.reader_settings_button = self._button(
            _("Ustawienia użytkownika"),
            _("Pokaż lub ukryj oddzielną, odwracalną warstwę ustawień czytelnika"),
        )
        self.reader_settings_button.setCheckable(True)
        self.reader_settings_button.toggled.connect(self._toggle_reader_settings)
        bar.row.addWidget(self.reader_settings_button)
        self.diagnostics_button = self._button(
            _("Diagnostyka"),
            _("Pokaż lub ukryj diagnostykę jakości aktywnego layoutu i zasobów"),
        )
        self.diagnostics_button.setCheckable(True)
        self.diagnostics_button.toggled.connect(self._toggle_diagnostics)
        self.screenshot_button = self._button(
            _("Screenshot"),
            _("Eksportuj obraz samego viewportu bez nakładki inspektora"),
            self._export_screenshot,
        )
        bar.row.addWidget(self.diagnostics_button)
        bar.row.addWidget(self.screenshot_button)
        bar.row.addStretch(1)
        bar.finish()
        self.reader_toolbar = bar
        layout.addWidget(bar)

        self.reader_settings_panel = self._build_reader_settings_panel()
        self.reader_settings_panel.setVisible(False)
        layout.addWidget(self.reader_settings_panel)
        self.diagnostics_tree = QTreeWidget()
        self.diagnostics_tree.setHeaderLabels([_("Kategoria"), _("Problem"), _("Wartość")])
        self.diagnostics_tree.setToolTip(
            _("Dwuklik problemu przenosi do elementu i źródła, gdy lokalizacja jest dostępna")
        )
        self.diagnostics_tree.itemActivated.connect(self._open_quality_issue)
        self.diagnostics_tree.setVisible(False)
        layout.addWidget(self.diagnostics_tree)
        self._sync_reader_controls()

    def _on_reader_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        page, pages = state.get("page"), state.get("pages")
        self.page_label.setText(
            _("strona podglądu {page}/{pages}").format(page=page, pages=pages)
            if isinstance(page, int) and isinstance(pages, int)
            else _("strona podglądu —")
        )
        font = state.get("font")
        if isinstance(font, dict):
            self.font_usage_label.setText(
                _("Font elementu: {family} · {size} · line-height {line} · {status}").format(
                    family=font.get("family", "—"),
                    size=font.get("size", "—"),
                    line=font.get("line_height", "—"),
                    status=font.get("status", "—"),
                )
            )
        limits = state.get("limitations", ())
        if isinstance(limits, list):
            self.reader_limitations_label.setText(" ".join(map(str, limits)))
        columns = bool(state.get("columns_enabled", False))
        self.previous_page_button.setEnabled(columns)
        self.next_page_button.setEnabled(columns)

    def _toggle_diagnostics(self, visible: bool) -> None:
        """Drugi klik chowa panel; obliczenie jest wykonywane tylko przy otwarciu."""
        self.diagnostics_tree.setVisible(visible)
        if visible:
            self._run_diagnostics()

    def _run_diagnostics(self) -> None:
        """Uruchamia diagnostykę bez zmieniania stanu przycisku panelu."""
        self._active.run_quality_diagnostics()

    def _on_quality_diagnostics(self, issues: object) -> None:
        self._quality_issues = (
            tuple(item for item in issues if isinstance(item, QualityIssue))
            if isinstance(issues, (tuple, list))
            else ()
        )
        self.diagnostics_tree.clear()
        for issue in self._quality_issues:
            item = QTreeWidgetItem([issue.category, issue.message, issue.value or ""])
            item.setData(0, _QUALITY_ROLE, issue)
            self.diagnostics_tree.addTopLevelItem(item)
        if not self._quality_issues:
            self.diagnostics_tree.addTopLevelItem(
                QTreeWidgetItem([_("Informacja"), _("Nie wykryto problemów jakości."), ""])
            )

    def _open_quality_issue(self, item: QTreeWidgetItem, _column: int) -> None:
        issue = item.data(0, _QUALITY_ROLE)
        if isinstance(issue, QualityIssue) and issue.node_id:
            self._active.focus_node(issue.node_id)
            location = self.source_location_for_node(issue.node_id)
            if location is not None:
                self.source_requested.emit(location)

    def _export_screenshot(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            cast(QWidget, self), _("Eksport viewportu"), "epubforge-viewport.png", _("PNG (*.png)")
        )
        if path and not self._active.export_viewport(path):
            self.diagnostics.emit(
                DiagnosticEvent(
                    DiagnosticCategory.SIMULATOR_LIMIT,
                    _("Eksport screenshotu wymaga dokładnego podglądu WebEngine."),
                    problem_kind="screenshot_unavailable",
                )
            )

    def _on_cache_changed(self, state: object) -> None:
        if isinstance(state, dict):
            self.cache_label.setText(
                _("Cache: {entries} wpisów / {bytes} B (HTTP {http})").format(
                    entries=state.get("entries", 0),
                    bytes=state.get("bytes", 0),
                    http=state.get("http_cache", "wyłączony"),
                )
            )

    def _secondary_profile(self) -> ReaderProfile:
        key = str(self.compare_profile_combo.currentData() or "phone-portrait")
        return (
            custom_profile_from_mapping(self._settings.custom_viewport)
            if key == "custom"
            else profile_by_key(key)
        )

    def _toggle_profile_comparison(self, enabled: bool) -> None:
        if not enabled:
            self._dispose_comparison_backend()
            self.comparison_status_label.clear()
            return
        if self._active.kind is not BackendKind.WEBENGINE or self._last_snapshot is None:
            self.compare_profiles_button.blockSignals(True)
            self.compare_profiles_button.setChecked(False)
            self.compare_profiles_button.blockSignals(False)
            self.comparison_status_label.setText(_("Porównanie wymaga dokładnego podglądu."))
            return
        try:
            backend: PreviewBackend = WebEnginePreviewBackend(theme=self._palette)
        except WebEngineInitError as exc:
            self.compare_profiles_button.setChecked(False)
            self.comparison_status_label.setText(str(exc))
            return
        backend.diagnostics.connect(self.diagnostics)
        backend.source_requested.connect(self.source_requested)
        backend.set_session(self._session)
        second = self._secondary_profile()
        backend.set_reader_simulation(second, self._user_style, self._comparison)
        self._comparison_backend = backend
        self._body_layout.addWidget(backend)
        backend.show()
        self._render_snapshot_into(backend, self._last_snapshot)
        self.comparison_status_label.setText(
            _("Porównanie: {first} | {second}").format(
                first=self._reader_profile.label, second=second.label
            )
        )

    def _on_compare_profile_selected(self, _index: int) -> None:
        if self._comparison_backend is not None:
            self._comparison_backend.set_reader_simulation(
                self._secondary_profile(), self._user_style, self._comparison
            )
            self.comparison_status_label.setText(
                _("Porównanie: {first} | {second}").format(
                    first=self._reader_profile.label, second=self._secondary_profile().label
                )
            )

    def _dispose_comparison_backend(self) -> None:
        backend = self._comparison_backend
        if backend is not None:
            self._body_layout.removeWidget(backend)
            backend.set_session(None)
            backend.dispose()
            backend.deleteLater()
            self._comparison_backend = None
