"""Motyw aplikacji — własny silnik (GUI_STANDARD v2.0 §4, §5).

Zamiast zewnętrznej biblioteki motywów budujemy motyw sami: styl ``Fusion``
+ :class:`QPalette` jako baza kolorów + generowany QSS wyłącznie na akcenty.
Dzięki temu mamy realny akcent marki ``#5DCAA5`` i pełną kontrolę, a build nie
zależy od porzuconego ``pyqtdarktheme``.

Kontrakt (§4):
* ``app.setStyle("Fusion")`` PRZED ``setPalette`` — natywne style Windows
  ignorują większość ról palety i zostawiają jasne kontrolki mimo ciemnej palety;
* QPalette = baza kolorów, QSS = TYLKO akcenty (ramki, zaokrąglenia, hover,
  pressed, focus, tooltip) — bez dublowania kolorów bazowych, bo QSS nadpisuje
  paletę i przy zmianie motywu zostają plamy;
* auto-motyw przez ``styleHints().colorScheme()`` (``Unknown`` → fallback dark);
* sygnał ``colorSchemeChanged`` podłączony WYŁĄCZNIE w trybie auto;
* po każdej zmianie: ``unpolish``/``polish`` po ``app.allWidgets()``.

Role i stany pochodne (§5) trzyma frozen :class:`Theme` — jedyne źródło hexów
dla customowych widgetów (poza tym modułem hexów w ``gui/`` nie ma).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QToolTip

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
    """Role palety i stany pochodne motywu (GUI_STANDARD §5).

    Jedyne źródło wartości hex w warstwie GUI — widgety czytają role stąd,
    nie wpisują własnych kolorów.

    Attributes:
        name: ``"dark"`` albo ``"light"``.
        bg: tło główne.
        bg2: tło sekcji / paneli.
        bg3: tło pól / inputów.
        fg: tekst główny.
        fg2: tekst drugorzędny.
        fg3: tekst wyciszony / hinty.
        accent: akcent główny (jasny) — wypełnienia, ikony, ramki.
        accent2: akcent ciemniejszy — przyciski, zaznaczenie.
        border: ramki / separatory.
        red: błędy / akcje destrukcyjne.
        amber: ostrzeżenia.
        link: kolor linku (w jasnym motywie ciemniejszy — nota WCAG §5).
        hover: tło kontrolki pod kursorem.
        pressed: tło kontrolki wciśniętej.
        selection_bg: tło zaznaczenia (= accent2).
        selection_fg: tekst na zaznaczeniu.
        disabled_fg: tekst nieaktywny (= fg3).
        disabled_bg: tło nieaktywne (= bg2).
        placeholder: tekst podpowiedzi w polach (= fg3).
        focus_border: ramka pola z fokusem (= accent).
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
    link: str
    hover: str
    pressed: str
    selection_bg: str
    selection_fg: str
    disabled_fg: str
    disabled_bg: str
    placeholder: str
    focus_border: str


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
    link="#5DCAA5",
    hover="#383c50",
    pressed="#262936",
    selection_bg="#1D9E75",
    selection_fg="#ffffff",
    disabled_fg="#555a70",
    disabled_bg="#252830",
    placeholder="#555a70",
    focus_border="#5DCAA5",
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
    link="#0F7C5B",
    hover="#dcdce2",
    pressed="#d4d4da",
    selection_bg="#0F7C5B",
    selection_fg="#ffffff",
    disabled_fg="#86868b",
    disabled_bg="#f5f5f7",
    placeholder="#86868b",
    focus_border="#1D9E75",
)

# Bieżący motyw — odczytywany przez widgety budowane dynamicznie (log, dialogi).
# Ustawiany przez ThemeManager przy każdym apply().
_current_theme: Theme = DARK


def current_theme() -> Theme:
    """Zwraca ostatnio zastosowany motyw (domyślnie DARK przed pierwszym apply)."""
    return _current_theme


def system_scheme() -> ThemeName:
    """Zwraca motyw systemu z ``QStyleHints`` (``Unknown`` → fallback dark).

    ``Unknown`` zdarza się na Linuksie bez portalu XDG — traktujemy jako ciemny,
    bo ciemny jest motywem podstawowym aplikacji (§4).
    """
    scheme = QGuiApplication.styleHints().colorScheme()
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def _build_palette(theme: Theme) -> QPalette:
    """Buduje :class:`QPalette` z ról motywu (baza kolorów dla Fusion)."""
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    palette = QPalette()

    palette.setColor(role.Window, QColor(theme.bg))
    palette.setColor(role.Button, QColor(theme.bg))
    palette.setColor(role.Base, QColor(theme.bg3))
    palette.setColor(role.AlternateBase, QColor(theme.bg2))
    palette.setColor(role.Text, QColor(theme.fg))
    palette.setColor(role.WindowText, QColor(theme.fg))
    palette.setColor(role.ButtonText, QColor(theme.fg))
    palette.setColor(role.PlaceholderText, QColor(theme.placeholder))
    palette.setColor(role.Highlight, QColor(theme.selection_bg))
    palette.setColor(role.HighlightedText, QColor(theme.selection_fg))
    palette.setColor(role.Link, QColor(theme.link))
    palette.setColor(role.ToolTipBase, QColor(theme.bg2))
    palette.setColor(role.ToolTipText, QColor(theme.fg))

    # Grupa Disabled MUSI być ustawiona jawnie — inaczej Fusion wylicza własne,
    # niespójne z motywem kolory (GUI_STANDARD §5, pułapka palety).
    palette.setColor(group.Disabled, role.WindowText, QColor(theme.disabled_fg))
    palette.setColor(group.Disabled, role.Text, QColor(theme.disabled_fg))
    palette.setColor(group.Disabled, role.ButtonText, QColor(theme.disabled_fg))
    palette.setColor(group.Disabled, role.Button, QColor(theme.disabled_bg))
    palette.setColor(group.Disabled, role.Base, QColor(theme.disabled_bg))
    return palette


def _build_qss(theme: Theme) -> str:
    """Generuje QSS WYŁĄCZNIE na akcenty (ramki, zaokrąglenia, stany).

    Świadomie NIE wpisujemy tu kolorów bazowych (bg/bg2/bg3/fg/fg2/fg3) — te
    pochodzą z :class:`QPalette`. Dublowanie powodowałoby plamy przy zmianie
    motywu (QSS nadpisuje paletę).
    """
    return f"""
QPushButton, QToolButton {{
    border: 1px solid {theme.border};
    border-radius: 6px;
    padding: 4px 12px;
}}
QPushButton:hover, QToolButton:hover {{
    background-color: {theme.hover};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {theme.pressed};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QAbstractSpinBox {{
    border: 1px solid {theme.border};
    border-radius: 4px;
    padding: 2px 4px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QAbstractSpinBox:focus {{
    border: 1px solid {theme.focus_border};
}}
QGroupBox {{
    border: 1px solid {theme.border};
    border-radius: 6px;
    margin-top: 6px;
    padding-top: 6px;
}}
QTabWidget::pane {{
    border: 1px solid {theme.border};
    border-radius: 6px;
}}
QToolTip {{
    border: 1px solid {theme.border};
    padding: 4px;
}}
"""


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Stosuje motyw do aplikacji wg kontraktu §4.

    Kolejność jest istotna: najpierw styl ``Fusion`` (inaczej natywny styl
    Windows zignoruje paletę), potem paleta, potem QSS na akcenty, na końcu
    jawna paleta tooltipów i przemalowanie istniejących widgetów.
    """
    app.setStyle("Fusion")
    palette = _build_palette(theme)
    app.setPalette(palette)
    app.setStyleSheet(_build_qss(theme))
    QToolTip.setPalette(palette)
    _repolish(app)


def _repolish(app: QApplication) -> None:
    """Wymusza przemalowanie wszystkich widgetów po zmianie palety/QSS.

    Po ``unpolish``/``polish`` dodatkowo wołamy ``update()`` na każdym widgecie
    (i raz jeszcze na oknach top-level) — bez tego częściowo widoczne okna
    odświeżają się z opóźnieniem przy zmianie motywu systemu w tle (tryb auto).
    """
    style = app.style()
    for widget in app.allWidgets():
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    for window in app.topLevelWidgets():
        window.update()


class ThemeManager(QObject):
    """Zarządza motywem aplikacji (auto/jasny/ciemny) i jego trwałością.

    Emituje :attr:`theme_changed` z :class:`Theme` po każdej zmianie. Sygnał
    systemowy ``colorSchemeChanged`` jest podłączony wyłącznie w trybie auto
    (referencję połączenia trzymamy, by je odłączyć przy wymuszeniu motywu).
    """

    theme_changed = Signal(object)

    def __init__(self, app: QApplication, config: Config) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._setting: ThemeSetting = self._initial_setting()
        self._theme: Theme = DARK
        # Uchwyt połączenia colorSchemeChanged — None gdy nie subskrybujemy.
        self._auto_connection: object | None = None

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
            return system_scheme()
        return "light" if chosen == "light" else "dark"

    def apply(self, setting: ThemeSetting) -> None:
        """Ustawia tryb, zapisuje go w configu i stosuje do aplikacji."""
        global _current_theme
        self._setting = setting
        self._config["theme"] = setting
        name = self.resolved_name(setting)
        self._theme = DARK if name == "dark" else LIGHT
        apply_theme(self._app, self._theme)
        _current_theme = self._theme
        self._update_auto_subscription()
        self.theme_changed.emit(self._theme)

    def _update_auto_subscription(self) -> None:
        """Podłącza ``colorSchemeChanged`` tylko w trybie auto, inaczej odłącza."""
        hints = self._app.styleHints()
        if self._setting == "auto" and self._auto_connection is None:
            self._auto_connection = hints.colorSchemeChanged.connect(self._on_system_scheme_changed)
        elif self._setting != "auto" and self._auto_connection is not None:
            hints.colorSchemeChanged.disconnect(self._auto_connection)
            self._auto_connection = None

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        """Gdy zmienia się motyw systemu, odśwież w trybie auto."""
        if self._setting == "auto":
            self.apply("auto")
