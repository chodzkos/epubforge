"""Główne okno aplikacji EpubForge (PySide6) i entry point GUI."""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QByteArray, QEvent, QTimer
from PySide6.QtGui import QActionGroup, QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from epubforge import __version__
from epubforge.core import ConfigStore, Tool, default_config_path, detect_with_cache, load_config
from epubforge.gui.tabs import ConverterTab, FixerTab, KfxTab, MetadataTab
from epubforge.gui.theme import ThemeManager, ThemeName, ThemeSetting, system_scheme
from epubforge.gui.widgets import AboutPanel, LogView
from epubforge.gui.window_theme import sync_titlebar

logger = logging.getLogger(__name__)

# Opóźnienie debounce zapisu configu (GUI_STANDARD §8): zbieramy zmiany i piszemy
# raz po ~1 s bezczynności, zamiast przy każdym naciśnięciu klawisza.
_FLUSH_DEBOUNCE_MS = 1000

# Etykiety trybów motywu w przycisku górnego paska.
_THEME_LABELS: dict[ThemeSetting, str] = {"auto": "Auto", "light": "Jasny", "dark": "Ciemny"}
_THEME_MENU_ITEMS: tuple[tuple[str, ThemeSetting], ...] = (
    ("Automatyczny", "auto"),
    ("Jasny", "light"),
    ("Ciemny", "dark"),
)

_GEOMETRY_KEY = "window_geometry"


class AboutDialog(QDialog):
    """Małe okno „O programie" z panelem :class:`AboutPanel`."""

    def __init__(self, parent: QWidget, mode: ThemeName) -> None:
        super().__init__(parent)
        self._mode = mode
        self.setWindowTitle("O programie")
        layout = QVBoxLayout(self)
        layout.addWidget(AboutPanel())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.resize(440, 380)

    def set_mode(self, mode: ThemeName) -> None:
        """Aktualizuje motyw okna i synchronizuje pasek tytułu (gdy ≠ system)."""
        self._mode = mode
        sync_titlebar(self, mode, system_scheme())

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 — Qt API
        """Po utworzeniu natywnego okna synchronizuje kolor paska tytułu."""
        super().showEvent(event)
        sync_titlebar(self, self._mode, system_scheme())


class MainWindow(QMainWindow):
    """Główne okno aplikacji EpubForge.

    Geometria zapisywana jest w configu jako szesnastkowy zrzut
    ``QMainWindow.saveGeometry`` pod kluczem ``window_geometry``.
    """

    def __init__(
        self,
        config_path: Path,
        config: ConfigStore,
        tools: dict[str, Tool],
        theme_manager: ThemeManager,
    ) -> None:
        super().__init__()
        self.config_path = config_path
        self.config_data = config
        self.tools = tools
        self.theme_manager = theme_manager
        self._about_dialog: AboutDialog | None = None

        # Debounce zapisu configu: każde mark_dirty restartuje licznik, a po ~1 s
        # bezczynności QTimer woła flush (GUI_STANDARD §8). Timing żyje tu, w GUI;
        # ConfigStore (core) zna tylko callback on_dirty.
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(_FLUSH_DEBOUNCE_MS)
        self._flush_timer.timeout.connect(self._flush_config)
        self.config_data.on_dirty = self._schedule_flush

        self.setWindowTitle(f"EpubForge {__version__}")
        self.setMinimumSize(760, 520)
        self._restore_geometry()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        self._build_topbar(layout)
        self._build_tabs(layout)
        self._build_status_bar()

        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._sync_theme_actions()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_topbar(self, layout: QVBoxLayout) -> None:
        """Buduje górny pasek: nazwa po lewej, motyw i About po prawej."""
        topbar = QHBoxLayout()
        title = QLabel("EpubForge")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title.setFont(title_font)
        topbar.addWidget(title)
        topbar.addStretch(1)

        self.theme_button = QToolButton()
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.theme_button.setToolTip("Motyw: Automatyczny / Jasny / Ciemny")
        self.theme_menu = QMenu(self.theme_button)
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self._theme_actions: dict[ThemeSetting, object] = {}
        for label, value in _THEME_MENU_ITEMS:
            action = self.theme_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, v=value: self._select_theme(v))
            self.theme_group.addAction(action)
            self._theme_actions[value] = action
        self.theme_button.setMenu(self.theme_menu)
        topbar.addWidget(self.theme_button)

        self.about_button = QToolButton()
        self.about_button.setText("ⓘ")
        self.about_button.setToolTip("O programie")
        self.about_button.clicked.connect(self._open_about)
        topbar.addWidget(self.about_button)

        layout.addLayout(topbar)

    def _build_tabs(self, layout: QVBoxLayout) -> None:
        """Buduje notebook z zakładkami roboczymi (bez meta-zakładek)."""
        self.tabs = QTabWidget()
        self.metadata_tab = MetadataTab(tools=self.tools)
        self.converter_tab = ConverterTab(config=self.config_data)
        self.fixer_tab = FixerTab(tools=self.tools)
        self.kfx_tab = KfxTab(tools=self.tools, config=self.config_data)
        self.tabs.addTab(self.metadata_tab, "Metadane")
        self.tabs.addTab(self.converter_tab, "Konwerter")
        self.tabs.addTab(self.fixer_tab, "Fixer")
        self.tabs.addTab(self.kfx_tab, "Eksport Kindle")
        layout.addWidget(self.tabs, stretch=1)

    def _build_status_bar(self) -> None:
        """Buduje dolny pasek statusu wykrytych narzędzi."""
        self.statusBar().showMessage(_format_tools_status(self.tools))

    # ── Motyw ────────────────────────────────────────────────────────────────

    def _select_theme(self, setting: ThemeSetting) -> None:
        """Stosuje wybrany tryb motywu."""
        self.theme_manager.apply(setting)

    def _sync_theme_actions(self) -> None:
        """Zaznacza akcję menu odpowiadającą bieżącemu ustawieniu i odświeża etykietę."""
        setting = self.theme_manager.setting
        action = self._theme_actions.get(setting)
        if action is not None:
            action.setChecked(True)  # type: ignore[attr-defined]
        self.theme_button.setText(f"Motyw: {_THEME_LABELS[setting]}")

    def _on_theme_changed(self, _theme: object) -> None:
        """Reaguje na zmianę motywu: pasek tytułu, log, etykieta, okno About."""
        self._sync_titlebar()
        self._sync_theme_actions()
        for log_view in self._log_views():
            log_view.set_theme(self.theme_manager.theme)
        if self._about_dialog is not None:
            self._about_dialog.set_mode(self.theme_manager.theme.name)

    def _sync_titlebar(self) -> None:
        """Synchronizuje pasek tytułu okna z motywem (DWM tylko gdy ≠ system)."""
        sync_titlebar(self, self.theme_manager.theme.name, system_scheme())

    # ── Debounce zapisu configu ─────────────────────────────────────────────────

    def _schedule_flush(self) -> None:
        """Restartuje licznik debounce — zapis nastąpi po ~1 s bezczynności."""
        self._flush_timer.start()

    def _flush_config(self) -> None:
        """Zapisuje config, jeśli ma niezapisane zmiany (cel timera debounce)."""
        self.config_data.flush()

    def _log_views(self) -> list[LogView]:
        """Zbiera widgety logu z zakładek (do przemalowania przy zmianie motywu)."""
        views: list[LogView] = []
        for tab in (self.converter_tab, self.fixer_tab, self.kfx_tab):
            view = getattr(tab, "log_view", None)
            if isinstance(view, LogView):
                views.append(view)
        return views

    # ── Okno „O programie" ──────────────────────────────────────────────────

    def _open_about(self) -> None:
        """Otwiera „O programie" jako okno modalne (pojedyncza instancja)."""
        if self._about_dialog is not None:
            self._about_dialog.raise_()
            self._about_dialog.activateWindow()
            return
        dialog = AboutDialog(self, self.theme_manager.theme.name)
        dialog.finished.connect(self._on_about_closed)
        self._about_dialog = dialog
        dialog.show()

    def _on_about_closed(self, _result: int) -> None:
        """Czyści referencję po zamknięciu okna About."""
        self._about_dialog = None

    # ── Pasek tytułu / cykl życia okna ─────────────────────────────────────────

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 — Qt API
        """Synchronizuje pasek tytułu po utworzeniu natywnego okna (winId)."""
        super().showEvent(event)
        self._sync_titlebar()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 — Qt API
        """Po (de)aktywacji okna ponawia synchronizację paska tytułu (Win10).

        Realny DWM odpala się tylko przy wymuszonym rozjeździe motyw≠system —
        :func:`sync_titlebar` sama to filtruje.
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            self._sync_titlebar()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 — Qt API
        """Zapisuje konfigurację (motyw, geometria) bezwarunkowo przy zamknięciu."""
        self.config_data["theme"] = self.theme_manager.setting
        self.config_data[_GEOMETRY_KEY] = bytes(self.saveGeometry().toHex().data()).decode("ascii")
        self.config_data.save_now()
        self._flush_timer.stop()
        super().closeEvent(event)

    def _restore_geometry(self) -> None:
        """Przywraca zapisaną geometrię okna albo ustawia domyślny rozmiar."""
        raw = self.config_data.get(_GEOMETRY_KEY)
        if isinstance(raw, str) and raw:
            self.restoreGeometry(QByteArray.fromHex(raw.encode("ascii")))
        else:
            self.resize(980, 680)


def _format_tools_status(tools: dict[str, Tool]) -> str:
    """Buduje zwięzły opis statusu wykrytych narzędzi."""
    labels = {
        "pandoc": "Pandoc",
        "calibre_ebook_convert": "Calibre",
        "calibre_viewer": "Viewer",
        "calibre_editor": "Editor",
        "sigil": "Sigil",
        "kindle_previewer": "KP3",
    }
    parts: list[str] = []
    for key, label in labels.items():
        tool = tools.get(key)
        marker = "OK" if tool is not None and tool.available else "brak"
        parts.append(f"{label}: {marker}")
    return " | ".join(parts)


def _install_excepthook(config_path: Path) -> None:
    """Instaluje globalny hook wyjątków: dialog + zrzut traceby do ``error.txt``."""
    error_file = config_path.parent / "error.txt"

    def handle(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logger.error("Nieobsłużony wyjątek:\n%s", text)
        try:
            error_file.write_text(text, encoding="utf-8")
        except OSError:
            logger.warning("Nie udało się zapisać %s", error_file)
        QMessageBox.critical(None, "Błąd krytyczny", f"Wystąpił nieoczekiwany błąd:\n{exc}")

    sys.excepthook = handle


def main() -> None:
    """Entry point ``epubforge-gui``."""
    app = QApplication(sys.argv)
    app.setApplicationName("EpubForge")

    config_path = default_config_path()
    # Detekcja narzędzi sama dopisuje cache do pliku — wczytujemy config DOPIERO
    # po niej, by ConfigStore (autorytatywny przy zapisie) miał komplet danych.
    try:
        tools = detect_with_cache(config_path)
    except OSError:
        tools = {}

    config = ConfigStore(config_path, load_config(config_path))
    theme_manager = ThemeManager(app, config)
    _install_excepthook(config_path)

    window = MainWindow(config_path, config, tools, theme_manager)
    theme_manager.apply(theme_manager.setting)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
