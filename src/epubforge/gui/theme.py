"""Motyw aplikacji: ciemny i jasny — oba przez ``qdarktheme``.

Zgodnie z GUI_STANDARD §4 tryb ciemny i jasny realizuje ``qdarktheme`` z akcentem
marki. Oba warianty korzystają z tego samego generatora arkusza stylów (styl
Fusion + spójne metryki), więc przełączanie zmienia wyłącznie kolory, a NIE
rozmiary/odstępy/położenie kontrolek. Role palety (§5) trzymamy w dataclassie
:class:`Theme`, żeby widgety nie używały sztywnych hexów.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import qdarktheme
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from epubforge.core.config import Config

logger = logging.getLogger(__name__)

ThemeSetting = Literal["auto", "light", "dark"]
ThemeName = Literal["dark", "light"]

_THEME_SETTINGS: tuple[ThemeSetting, ...] = ("auto", "light", "dark")

# Akcent marki (znak rozpoznawczy aplikacji chodzkos) — GUI_STANDARD §5.
PRIMARY = "#5DCAA5"
PRIMARY_DARK = "#1D9E75"


@dataclass(frozen=True)
class Theme:
    """Role palety motywu (GUI_STANDARD §5).

    Attributes:
        name: ``"dark"`` albo ``"light"``.
        bg: tło główne.
        bg2: tło sekcji / paneli.
        bg3: tło pól / inputów.
        fg: tekst główny.
        fg2: tekst drugorzędny.
        fg3: tekst wyciszony / hinty.
        accent: akcent główny (jasny).
        accent2: akcent ciemniejszy (przyciski).
        border: ramki / separatory.
        red: błędy / akcje destrukcyjne.
        amber: ostrzeżenia.
    """

    name: ThemeName
    bg: str
    bg2: str
    bg3: str
    fg: str
    fg2: str
    fg3: str
    accent: str
    accent2: str
    border: str
    red: str
    amber: str


DARK = Theme(
    name="dark",
    bg="#1e2028",
    bg2="#252830",
    bg3="#2d3040",
    fg="#dde1ec",
    fg2="#8b90a7",
    fg3="#555a70",
    accent="#5DCAA5",
    accent2="#1D9E75",
    border="#383c50",
    red="#e25454",
    amber="#EF9F27",
)

LIGHT = Theme(
    name="light",
    bg="#ffffff",
    bg2="#f5f5f7",
    bg3="#e8e8ed",
    fg="#1d1d1f",
    fg2="#515154",
    fg3="#86868b",
    accent="#1D9E75",
    accent2="#0F7C5B",
    border="#d1d1d6",
    red="#d70015",
    amber="#b25000",
)

# Bieżący motyw — odczytywany przez widgety budowane dynamicznie (log, tooltipy
# kolorów, wybór natywnego/ciemnego dialogu plików). Ustawiany przez ThemeManager.
_current_theme: Theme = DARK


def current_theme() -> Theme:
    """Zwraca ostatnio zastosowany motyw (domyślnie DARK przed pierwszym apply)."""
    return _current_theme


def native_file_dialogs() -> bool:
    """Czy używać natywnych dialogów plików.

    W trybie ciemnym natywny dialog systemu jest jasny i psuje spójność — wtedy
    używamy dialogu Qt (``DontUseNativeDialog``). W trybie jasnym natywny jest OK.
    """
    return _current_theme.name == "light"


class ThemeManager(QObject):
    """Zarządza motywem aplikacji (auto/jasny/ciemny) i jego trwałością.

    Emituje sygnał :attr:`theme_changed` z obiektem :class:`Theme` po każdej
    zmianie — np. widgety logu odświeżają wtedy kolory ról.
    """

    theme_changed = Signal(object)

    def __init__(self, app: QApplication, config: Config) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._setting: ThemeSetting = self._initial_setting()
        self._theme: Theme = DARK

        # Reakcja na zmianę motywu systemowego w locie (tania) — tylko gdy auto.
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def setting(self) -> ThemeSetting:
        """Aktualne ustawienie trybu (auto/light/dark)."""
        return self._setting

    @property
    def theme(self) -> Theme:
        """Aktualnie zastosowany motyw (rozwiązany z ustawienia)."""
        return self._theme

    def _initial_setting(self) -> ThemeSetting:
        """Wczytuje ustawienie motywu z configu (domyślnie auto)."""
        value = self._config.get("theme")
        return value if value in _THEME_SETTINGS else "auto"

    def resolved_name(self, setting: ThemeSetting | None = None) -> ThemeName:
        """Mapuje ustawienie na konkretny motyw (``auto`` → motyw systemu)."""
        chosen = setting if setting is not None else self._setting
        if chosen == "auto":
            return self._system_name()
        return "light" if chosen == "light" else "dark"

    def _system_name(self) -> ThemeName:
        """Zwraca motyw systemu z ``QStyleHints`` (domyślnie ciemny)."""
        scheme = self._app.styleHints().colorScheme()
        return "light" if scheme == Qt.ColorScheme.Light else "dark"

    def apply(self, setting: ThemeSetting) -> None:
        """Ustawia tryb, zapisuje go w configu i stosuje do aplikacji."""
        global _current_theme
        self._setting = setting
        self._config["theme"] = setting
        name = self.resolved_name(setting)
        if name == "dark":
            self._apply_dark()
            self._theme = DARK
        else:
            self._apply_light()
            self._theme = LIGHT
        _current_theme = self._theme
        self._repolish()
        self.theme_changed.emit(self._theme)

    def _apply_dark(self) -> None:
        """Stosuje ciemny motyw qdarktheme z akcentem marki."""
        qdarktheme.setup_theme("dark", custom_colors={"primary": PRIMARY})

    def _apply_light(self) -> None:
        """Stosuje jasny motyw qdarktheme z akcentem marki.

        Świadomie używamy ``qdarktheme`` (a nie natywnego stylu), żeby metryki
        kontrolek były identyczne jak w trybie ciemnym — przełączanie zmienia
        tylko kolory, bez przeskoków rozmiaru/odstępów.
        """
        qdarktheme.setup_theme("light", custom_colors={"primary": PRIMARY_DARK})

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        """Gdy zmienia się motyw systemu, odśwież w trybie auto."""
        if self._setting == "auto":
            self.apply("auto")

    def _repolish(self) -> None:
        """Wymusza przemalowanie wszystkich widgetów po zmianie motywu."""
        style = self._app.style()
        for widget in self._app.allWidgets():
            style.unpolish(widget)
            style.polish(widget)
