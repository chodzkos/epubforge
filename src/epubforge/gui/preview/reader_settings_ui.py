"""Panel ustawień użytkownika i profilu symulatora czytnika."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from epubforge.gui.preview.backend import BackendKind, PreviewBackend
from epubforge.gui.preview.reader import (
    READER_PROFILES,
    ComparisonMode,
    FlowMode,
    ReaderProfile,
    UserStyleSettings,
    custom_profile_from_mapping,
    profile_by_key,
)
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.widgets.horizontal_strip import make_horizontal_panel
from epubforge.i18n import _


class ReaderSettingsUiMixin:
    """Buduje szeroki panel i synchronizuje jego odwracalne ustawienia."""

    _settings: PreviewSettings
    _active: PreviewBackend
    _reader_profile: ReaderProfile
    _user_style: UserStyleSettings
    _comparison: ComparisonMode
    _comparison_backend: PreviewBackend | None
    profile_combo: QComboBox
    flow_combo: QComboBox
    reader_settings_panel: QWidget

    def _build_reader_settings_panel(self) -> QWidget:
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 4)
        self.user_style_enabled = QCheckBox(_("Aktywna warstwa użytkownika"))
        self.user_style_enabled.setToolTip(
            _("Włącz lub wyłącz wszystkie odwracalne nadpisania użytkownika")
        )
        grid.addWidget(self.user_style_enabled, 0, 0, 1, 2)
        self.font_size_spin = self._double_spin(
            8, 72, 1, _("Bazowy rozmiar tekstu warstwy użytkownika"), " px"
        )
        self.line_height_spin = self._double_spin(
            0.8, 3.0, 0.1, _("Wysokość linii warstwy użytkownika")
        )
        self.margin_spin = self._double_spin(
            0, 160, 1, _("Margines strony narzucony przez użytkownika"), " px"
        )
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
        self._add_font_controls(grid)
        self._add_color_viewport_controls(grid)
        self._add_cache_compare_controls(grid)
        self.user_style_enabled.toggled.connect(self._on_user_controls_changed)
        return make_horizontal_panel(panel)

    def _add_font_controls(self, grid: QGridLayout) -> None:
        """Dodaje font, przełączniki wydawcy i wariant porównania CSS."""
        self.font_family_edit = QLineEdit()
        self.font_family_edit.setToolTip(
            _("Rodzina fontu lub uporządkowana lista fallbacków oddzielona przecinkami")
        )
        self.font_family_edit.editingFinished.connect(self._on_user_controls_changed)
        grid.addWidget(QLabel(_("Font / fallback")), 1, 0)
        grid.addWidget(self.font_family_edit, 1, 1, 1, 2)
        self.force_font_check = QCheckBox(_("Wymuś font"))
        self.disable_fonts_check = QCheckBox(_("Wyłącz fonty osadzone"))
        self.disable_publisher_check = QCheckBox(_("Wyłącz CSS wydawcy"))
        self.force_font_check.setToolTip(_("Nadaj wybranemu fontowi priorytet nad CSS wydawcy"))
        self.disable_fonts_check.setToolTip(_("Nie używaj fontów dołączonych do publikacji"))
        self.disable_publisher_check.setToolTip(
            _("Wyłącz style wydawcy w kopii renderowanej; nie zmienia to źródła EPUB")
        )
        for column, check in enumerate(
            (self.force_font_check, self.disable_fonts_check, self.disable_publisher_check), start=3
        ):
            check.toggled.connect(self._on_user_controls_changed)
            grid.addWidget(check, 1, column)
        self.comparison_combo = QComboBox()
        self.comparison_combo.setToolTip(
            _("Porównaj CSS wydawcy, CSS z ustawieniami użytkownika albo tekst bez stylów")
        )
        self.comparison_combo.addItem(_("CSS wydawcy"), ComparisonMode.PUBLISHER.value)
        self.comparison_combo.addItem(
            _("CSS wydawcy + ustawienia użytkownika"), ComparisonMode.PUBLISHER_USER.value
        )
        self.comparison_combo.addItem(_("Tekst bez stylów wydawcy"), ComparisonMode.UNSTYLED.value)
        self.comparison_combo.currentIndexChanged.connect(self._on_comparison_selected)
        grid.addWidget(self.comparison_combo, 1, 6, 1, 2)

    def _add_color_viewport_controls(self, grid: QGridLayout) -> None:
        """Dodaje kolory warstwy i wymiary własnego viewportu."""
        self.page_color_edit, self.text_color_edit = QLineEdit(), QLineEdit()
        for edit, tooltip in (
            (self.page_color_edit, _("Kolor strony w warstwie symulatora, np. #ffffff")),
            (self.text_color_edit, _("Kolor tekstu w warstwie symulatora, np. #1a1a1a")),
        ):
            edit.setMaximumWidth(90)
            edit.setToolTip(tooltip)
            edit.editingFinished.connect(self._on_user_controls_changed)
        grid.addWidget(QLabel(_("Kolor strony")), 2, 0)
        grid.addWidget(self.page_color_edit, 2, 1)
        grid.addWidget(QLabel(_("Kolor tekstu")), 2, 2)
        grid.addWidget(self.text_color_edit, 2, 3)
        self.viewport_width_spin, self.viewport_height_spin = QSpinBox(), QSpinBox()
        for spin, tooltip in (
            (self.viewport_width_spin, _("Szerokość własnego viewportu w CSS px")),
            (self.viewport_height_spin, _("Wysokość własnego viewportu w CSS px")),
        ):
            spin.setRange(240, 3840)
            spin.setToolTip(tooltip)
            spin.valueChanged.connect(self._on_custom_viewport_changed)
        grid.addWidget(QLabel(_("Własny viewport")), 2, 4)
        grid.addWidget(self.viewport_width_spin, 2, 5)
        grid.addWidget(QLabel("x"), 2, 6)
        grid.addWidget(self.viewport_height_spin, 2, 7)

    def _add_cache_compare_controls(self, grid: QGridLayout) -> None:
        """Dodaje licznik cache, font rzeczywisty i drugi profil."""
        self.cache_label = QLabel(_("Cache: 0 wpisów / 0 B (HTTP wyłączony)"))
        grid.addWidget(self.cache_label, 3, 0, 1, 5)
        self.clear_cache_button = self._button(
            _("Wyczyść cache"),
            _("Usuń pamięciowy cache dokumentów, CSS, obrazów i fontów bieżącej sesji"),
            lambda: self._active.clear_preview_cache(),
        )
        grid.addWidget(self.clear_cache_button, 3, 5)
        self.reader_limitations_label = QLabel()
        self.reader_limitations_label.setWordWrap(True)
        grid.addWidget(self.reader_limitations_label, 3, 6, 1, 2)
        self.font_usage_label = QLabel(_("Font elementu: —"))
        self.font_usage_label.setWordWrap(True)
        grid.addWidget(self.font_usage_label, 4, 0, 1, 8)
        self.compare_profile_combo = QComboBox()
        self.compare_profile_combo.setToolTip(_("Wybierz drugi neutralny profil do porównania"))
        for key, profile in READER_PROFILES.items():
            self.compare_profile_combo.addItem(_(profile.label), key)
        index = self.compare_profile_combo.findData("phone-portrait")
        self.compare_profile_combo.setCurrentIndex(max(0, index))
        self.compare_profile_combo.currentIndexChanged.connect(self._on_compare_profile_selected)
        grid.addWidget(QLabel(_("Drugi profil")), 5, 0)
        grid.addWidget(self.compare_profile_combo, 5, 1, 1, 2)
        self.compare_profiles_button = self._button(
            _("Porównaj obok siebie"),
            _("Pokaż lub ukryj drugi viewport; funkcja wymaga dokładnego podglądu"),
        )
        self.compare_profiles_button.setCheckable(True)
        self.compare_profiles_button.toggled.connect(self._toggle_profile_comparison)
        grid.addWidget(self.compare_profiles_button, 5, 3, 1, 2)
        self.comparison_status_label = QLabel()
        grid.addWidget(self.comparison_status_label, 5, 5, 1, 3)

    @staticmethod
    def _button(text: str, tooltip: str, slot: Callable[[], None] | None = None) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def _double_spin(
        self, low: float, high: float, step: float, tooltip: str, suffix: str = ""
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setToolTip(tooltip)
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
        if self._reader_profile.key != "custom":
            return
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

    def _secondary_profile(self) -> ReaderProfile:
        raise NotImplementedError

    def _toggle_profile_comparison(self, enabled: bool) -> None:
        raise NotImplementedError

    def _on_compare_profile_selected(self, index: int) -> None:
        raise NotImplementedError
