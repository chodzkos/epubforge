from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
from typing import Any, cast

from chodzkos_gui_kit.palette import Palette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
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
    UserStyleSettings,
    custom_profile_from_mapping,
    profile_by_key,
    user_style_from_mapping,
)
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.webengine_backend import WebEngineInitError, WebEnginePreviewBackend
from epubforge.i18n import _

_QUALITY_ROLE = 0x0100


class ReaderUiMixin:
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
        bar = QHBoxLayout()
        bar.addWidget(QLabel(_("Profil czytnika:")))
        self.profile_combo = QComboBox()
        for key, profile in READER_PROFILES.items():
            self.profile_combo.addItem(_(profile.label), key)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        bar.addWidget(self.profile_combo)
        self.flow_combo = QComboBox()
        self.flow_combo.addItem(_("Przewijanie"), FlowMode.SCROLL.value)
        self.flow_combo.addItem(_("Strony podglądu"), FlowMode.PAGES.value)
        self.flow_combo.currentIndexChanged.connect(self._on_flow_selected)
        bar.addWidget(self.flow_combo)
        self.previous_page_button = self._button(
            _("Poprzednia"), lambda: self._active.navigate_preview_page(-1)
        )
        self.next_page_button = self._button(
            _("Następna"), lambda: self._active.navigate_preview_page(1)
        )
        self.current_element_button = self._button(
            _("Do elementu"), lambda: self._active.jump_to_current_element()
        )
        for button in (
            self.previous_page_button,
            self.next_page_button,
            self.current_element_button,
        ):
            bar.addWidget(button)
        self.page_label = QLabel(_("strona podglądu —"))
        bar.addWidget(self.page_label)
        self.reader_settings_button = self._button(_("Ustawienia użytkownika"), lambda: None)
        self.reader_settings_button.setCheckable(True)
        self.reader_settings_button.toggled.connect(self._toggle_reader_settings)
        bar.addWidget(self.reader_settings_button)
        self.diagnostics_button = self._button(_("Diagnostyka"), self._run_diagnostics)
        self.screenshot_button = self._button(_("Screenshot"), self._export_screenshot)
        bar.addWidget(self.diagnostics_button)
        bar.addWidget(self.screenshot_button)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.reader_settings_panel = self._build_reader_settings_panel()
        self.reader_settings_panel.setVisible(False)
        layout.addWidget(self.reader_settings_panel)
        self.diagnostics_tree = QTreeWidget()
        self.diagnostics_tree.setHeaderLabels([_("Kategoria"), _("Problem"), _("Wartość")])
        self.diagnostics_tree.itemActivated.connect(self._open_quality_issue)
        self.diagnostics_tree.setVisible(False)
        layout.addWidget(self.diagnostics_tree)
        self._sync_reader_controls()

    def _build_reader_settings_panel(self) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 4)
        self.user_style_enabled = QCheckBox(_("Aktywna warstwa użytkownika"))
        grid.addWidget(self.user_style_enabled, 0, 0, 1, 2)
        self.font_size_spin = self._double_spin(8, 72, 1, " px")
        self.line_height_spin = self._double_spin(0.8, 3.0, 0.1)
        self.margin_spin = self._double_spin(0, 160, 1, " px")
        for column, (label, widget) in enumerate(
            (
                (_("Rozmiar tekstu"), self.font_size_spin),
                ("Line-height", self.line_height_spin),
                (_("Marginesy"), self.margin_spin),
            ),
            start=2,
        ):
            grid.addWidget(QLabel(label), 0, column * 2 - 2)
            grid.addWidget(widget, 0, column * 2 - 1)
        self.font_family_edit = QLineEdit()
        self.font_family_edit.editingFinished.connect(self._on_user_controls_changed)
        grid.addWidget(QLabel(_("Font / fallback")), 1, 0)
        grid.addWidget(self.font_family_edit, 1, 1, 1, 2)
        self.force_font_check = QCheckBox(_("Wymuś font"))
        self.disable_fonts_check = QCheckBox(_("Wyłącz fonty osadzone"))
        self.disable_publisher_check = QCheckBox(_("Wyłącz CSS wydawcy"))
        for column, check in enumerate(
            (self.force_font_check, self.disable_fonts_check, self.disable_publisher_check), start=3
        ):
            check.toggled.connect(self._on_user_controls_changed)
            grid.addWidget(check, 1, column)
        self.comparison_combo = QComboBox()
        self.comparison_combo.addItem(_("CSS wydawcy"), ComparisonMode.PUBLISHER.value)
        self.comparison_combo.addItem(
            _("CSS wydawcy + ustawienia użytkownika"), ComparisonMode.PUBLISHER_USER.value
        )
        self.comparison_combo.addItem(_("Tekst bez stylów wydawcy"), ComparisonMode.UNSTYLED.value)
        self.comparison_combo.currentIndexChanged.connect(self._on_comparison_selected)
        grid.addWidget(self.comparison_combo, 1, 6, 1, 2)
        self.page_color_edit, self.text_color_edit = QLineEdit(), QLineEdit()
        for edit in (self.page_color_edit, self.text_color_edit):
            edit.setMaximumWidth(90)
            edit.editingFinished.connect(self._on_user_controls_changed)
        grid.addWidget(QLabel(_("Kolor strony")), 2, 0)
        grid.addWidget(self.page_color_edit, 2, 1)
        grid.addWidget(QLabel(_("Kolor tekstu")), 2, 2)
        grid.addWidget(self.text_color_edit, 2, 3)
        self.viewport_width_spin, self.viewport_height_spin = QSpinBox(), QSpinBox()
        for spin in (self.viewport_width_spin, self.viewport_height_spin):
            spin.setRange(240, 3840)
            spin.valueChanged.connect(self._on_custom_viewport_changed)
        grid.addWidget(QLabel(_("Własny viewport")), 2, 4)
        grid.addWidget(self.viewport_width_spin, 2, 5)
        grid.addWidget(QLabel("x"), 2, 6)
        grid.addWidget(self.viewport_height_spin, 2, 7)
        self.cache_label = QLabel(_("Cache: 0 wpisów / 0 B (HTTP wyłączony)"))
        grid.addWidget(self.cache_label, 3, 0, 1, 5)
        self.clear_cache_button = self._button(
            _("Wyczyść cache"), lambda: self._active.clear_preview_cache()
        )
        grid.addWidget(self.clear_cache_button, 3, 5)
        self.reader_limitations_label = QLabel()
        self.reader_limitations_label.setWordWrap(True)
        grid.addWidget(self.reader_limitations_label, 3, 6, 1, 2)
        self.font_usage_label = QLabel(_("Font elementu: —"))
        self.font_usage_label.setWordWrap(True)
        grid.addWidget(self.font_usage_label, 4, 0, 1, 8)
        self.compare_profile_combo = QComboBox()
        for key, profile in READER_PROFILES.items():
            self.compare_profile_combo.addItem(_(profile.label), key)
        self.compare_profile_combo.setCurrentIndex(
            max(0, self.compare_profile_combo.findData("phone-portrait"))
        )
        self.compare_profile_combo.currentIndexChanged.connect(self._on_compare_profile_selected)
        grid.addWidget(QLabel(_("Drugi profil")), 5, 0)
        grid.addWidget(self.compare_profile_combo, 5, 1, 1, 2)
        self.compare_profiles_button = self._button(_("Porównaj obok siebie"), lambda: None)
        self.compare_profiles_button.setCheckable(True)
        self.compare_profiles_button.toggled.connect(self._toggle_profile_comparison)
        grid.addWidget(self.compare_profiles_button, 5, 3, 1, 2)
        self.comparison_status_label = QLabel()
        grid.addWidget(self.comparison_status_label, 5, 5, 1, 3)
        self.user_style_enabled.toggled.connect(self._on_user_controls_changed)
        return panel

    @staticmethod
    def _button(text: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(slot)
        return button

    def _double_spin(
        self, low: float, high: float, step: float, suffix: str = ""
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.valueChanged.connect(self._on_user_controls_changed)
        return spin

    def _sync_reader_controls(self) -> None:
        widgets = (
            self.profile_combo,
            self.flow_combo,
            self.user_style_enabled,
            self.font_size_spin,
            self.line_height_spin,
            self.margin_spin,
            self.font_family_edit,
            self.force_font_check,
            self.disable_fonts_check,
            self.disable_publisher_check,
            self.comparison_combo,
            self.page_color_edit,
            self.text_color_edit,
            self.viewport_width_spin,
            self.viewport_height_spin,
        )
        for widget in widgets:
            widget.blockSignals(True)
        user = self._user_style
        self.profile_combo.setCurrentIndex(
            max(0, self.profile_combo.findData(self._reader_profile.key))
        )
        self.flow_combo.setCurrentIndex(
            max(0, self.flow_combo.findData(self._reader_profile.flow.value))
        )
        self.user_style_enabled.setChecked(user.enabled)
        self.font_size_spin.setValue(user.font_size_px)
        self.line_height_spin.setValue(user.line_height)
        self.margin_spin.setValue(user.margin_px)
        self.font_family_edit.setText(user.font_family)
        self.force_font_check.setChecked(user.force_font)
        self.disable_fonts_check.setChecked(user.disable_embedded_fonts)
        self.disable_publisher_check.setChecked(user.disable_publisher_styles)
        self.comparison_combo.setCurrentIndex(
            max(0, self.comparison_combo.findData(self._comparison.value))
        )
        self.page_color_edit.setText(user.page_color)
        self.text_color_edit.setText(user.text_color)
        self.viewport_width_spin.setValue(self._reader_profile.width)
        self.viewport_height_spin.setValue(self._reader_profile.height)
        for widget in widgets:
            widget.blockSignals(False)
        custom = self._reader_profile.key == "custom"
        self.viewport_width_spin.setEnabled(custom)
        self.viewport_height_spin.setEnabled(custom)

    def _toggle_reader_settings(self, visible: bool) -> None:
        self.reader_settings_panel.setVisible(visible)

    def _on_profile_selected(self, _index: int) -> None:
        key = str(self.profile_combo.currentData() or "tablet-portrait")
        self._reader_profile = (
            custom_profile_from_mapping(self._settings.custom_viewport)
            if key == "custom"
            else profile_by_key(key)
        )
        self._user_style = self._reader_profile.user_style
        self._settings.profile, self._settings.user_style = key, asdict(self._user_style)
        self._sync_reader_controls()
        self._apply_reader_settings()

    def _on_flow_selected(self, _index: int) -> None:
        try:
            flow = FlowMode(str(self.flow_combo.currentData()))
        except ValueError:
            flow = FlowMode.SCROLL
        self._reader_profile = replace(self._reader_profile, flow=flow)
        self._persist_custom_profile()
        self._apply_reader_settings()

    def _on_custom_viewport_changed(self, _value: int) -> None:
        if self._reader_profile.key == "custom":
            self._reader_profile = replace(
                self._reader_profile,
                width=self.viewport_width_spin.value(),
                height=self.viewport_height_spin.value(),
            ).normalized()
            self._persist_custom_profile()
            self._apply_reader_settings()

    def _persist_custom_profile(self) -> None:
        if self._reader_profile.key == "custom":
            profile = self._reader_profile
            values = {
                key: getattr(profile, key)
                for key in (
                    "width",
                    "height",
                    "device_pixel_ratio",
                    "page_margin",
                    "font_size_px",
                    "line_height",
                    "page_color",
                    "text_color",
                )
            }
            values["flow"] = profile.flow.value
            self._settings.custom_viewport = values

    def _on_user_controls_changed(self, _value: object = None) -> None:
        self._user_style = UserStyleSettings(
            enabled=self.user_style_enabled.isChecked(),
            font_size_px=self.font_size_spin.value(),
            line_height=self.line_height_spin.value(),
            margin_px=self.margin_spin.value(),
            font_family=self.font_family_edit.text(),
            force_font=self.force_font_check.isChecked(),
            page_color=self.page_color_edit.text(),
            text_color=self.text_color_edit.text(),
            disable_publisher_styles=self.disable_publisher_check.isChecked(),
            disable_embedded_fonts=self.disable_fonts_check.isChecked(),
        ).normalized()
        self._settings.user_style = asdict(self._user_style)
        self._apply_reader_settings()

    def _on_comparison_selected(self, _index: int) -> None:
        try:
            self._comparison = ComparisonMode(str(self.comparison_combo.currentData()))
        except ValueError:
            self._comparison = ComparisonMode.PUBLISHER_USER
        self._settings.comparison = self._comparison.value
        self._apply_reader_settings()

    def _apply_reader_settings(self) -> None:
        if hasattr(self, "_active") and self._active.kind is BackendKind.WEBENGINE:
            self._active.set_reader_simulation(
                self._reader_profile, self._user_style, self._comparison
            )
        if self._comparison_backend is not None:
            self._comparison_backend.set_reader_simulation(
                self._secondary_profile(), self._user_style, self._comparison
            )

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

    def _run_diagnostics(self) -> None:
        self.diagnostics_tree.setVisible(True)
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
