"""Panel „O programie" — logo, nazwa, wersja, linki i licencja (Qt)."""

from __future__ import annotations

import logging
import sys
import webbrowser
from pathlib import Path

from chodzkos_gui_kit.qt.widgets import HelpWindow
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from epubforge import __version__
from epubforge.gui.help_window import HELP_TITLE, populate_help_window
from epubforge.i18n import _

logger = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/chodzkos/epubforge"


def _asset_path(name: str) -> Path:
    """Zwraca ścieżkę do zasobu z ``gui/assets`` — działa też w bundlu PyInstaller.

    W spakowanym ``.exe`` zasoby leżą pod ``sys._MEIPASS`` (z zachowaniem
    struktury pakietu), w trybie deweloperskim — obok modułu.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "gui" / "assets" / name
    return Path(__file__).resolve().parent.parent / "assets" / name


# Logo wczytywane z pliku — podmiana grafiki nie wymaga zmian w kodzie.
_LOGO_PATH = _asset_path("logo.png")


class AboutPanel(QWidget):
    """Wyśrodkowana kolumna z informacjami o aplikacji."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        self._build_logo(layout)

        name = QLabel("EpubForge")
        name_font = name.font()
        name_font.setPointSize(name_font.pointSize() + 8)
        name_font.setBold(True)
        name.setFont(name_font)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        version = QLabel(_("Wersja {version}").format(version=__version__))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        description = QLabel(_("Narzędzie do walidacji, naprawy i konwersji plików EPUB"))
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description)

        layout.addWidget(self._build_link("GitHub", GITHUB_URL))

        help_button = QPushButton(_("Pomoc"))
        help_button.setToolTip(_("Otwórz pomoc offline (zakładki per funkcja)"))
        help_button.clicked.connect(self._open_help)
        layout.addWidget(help_button, alignment=Qt.AlignmentFlag.AlignCenter)

        license_label = QLabel(_("Licencja: MIT"))
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_label)

    def _build_logo(self, layout: QVBoxLayout) -> None:
        """Pokazuje logo z pliku albo nic, gdy go brak / nie da się wczytać."""
        if not _LOGO_PATH.is_file():
            return
        pixmap = QPixmap(str(_LOGO_PATH))
        if pixmap.isNull():
            logger.warning("Nie udało się wczytać logo %s", _LOGO_PATH)
            return
        logo = QLabel()
        logo.setPixmap(pixmap)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

    def _build_link(self, text: str, url: str) -> QLabel:
        """Tworzy klikalny link otwierający URL w przeglądarce."""
        link = QLabel(f'<a href="{url}">{text}</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setToolTip(_("Otwórz w przeglądarce: {url}").format(url=url))
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(self._open)
        return link

    def _open(self, url: str) -> None:
        """Otwiera URL w domyślnej przeglądarce."""
        try:
            webbrowser.open(url)
        except OSError as exc:
            logger.warning("Nie udało się otworzyć %s: %s", url, exc)

    def _open_help(self) -> None:
        """Otwiera offline okno pomocy (kitowy ``HelpWindow`` + zakładki EpubForge).

        Zakładki dokładane są po konstrukcji (Markdown z plików pakietu + HTML narzędzi)
        przez :func:`~epubforge.gui.help_window.populate_help_window`.
        """
        window = HelpWindow(self, title=HELP_TITLE)
        populate_help_window(window)
        window.exec()
