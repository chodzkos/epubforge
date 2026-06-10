"""Zakładka „O programie" — wersja, opis, linki i miejsce na logo."""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Any

from epubforge import __version__

logger = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/chodzkos/epubforge"
HELP_URL = "https://github.com/chodzkos/epubforge#readme"
DESCRIPTION = "Narzędzie do walidacji, naprawy i konwersji plików EPUB"
LICENSE = "Licencja: MIT"

# Logo wczytywane z pliku — podmiana grafiki nie wymaga zmian w kodzie.
_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


class AboutTab(ttk.Frame):
    """Zakładka z informacjami o aplikacji."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=24)
        # Referencja do obrazka, by Tk nie zwolnił go po wyjściu z metody.
        self._logo_image: Any = None
        self._build_layout()

    def _build_layout(self) -> None:
        """Buduje wyśrodkowaną kolumnę z logo, opisem i linkami."""
        column = ttk.Frame(self)
        column.place(relx=0.5, rely=0.5, anchor="center")

        self._build_logo(column)
        self.name_label = ttk.Label(column, text="EpubForge", font=("TkDefaultFont", 18, "bold"))
        self.name_label.pack(pady=(12, 0))

        self.version_label = ttk.Label(column, text=f"Wersja {__version__}", style="Muted.TLabel")
        self.version_label.pack(pady=(2, 0))

        ttk.Label(column, text=DESCRIPTION, wraplength=420, justify="center").pack(pady=(10, 0))

        self.github_link = self._build_link(column, "GitHub", GITHUB_URL)
        self.help_link = self._build_link(column, "Pomoc (README)", HELP_URL)

        ttk.Label(column, text=LICENSE, style="Muted.TLabel").pack(pady=(12, 0))

    def _build_logo(self, parent: tk.Misc) -> None:
        """Pokazuje logo z pliku albo tekstowy zastępnik, gdy go brak."""
        image = self._load_logo()
        if image is not None:
            self._logo_image = image
            self.logo_label = ttk.Label(parent, image=image)
        else:
            self.logo_label = ttk.Label(parent, text="EpubForge", style="Title.TLabel")
        self.logo_label.pack()

    def _load_logo(self) -> Any:
        """Wczytuje ``assets/logo.png`` przez Pillow albo zwraca ``None``."""
        if not _LOGO_PATH.is_file():
            return None
        try:
            from PIL import Image, ImageTk

            return ImageTk.PhotoImage(Image.open(_LOGO_PATH))
        except (ImportError, OSError) as exc:
            logger.warning("Nie udało się wczytać logo %s: %s", _LOGO_PATH, exc)
            return None

    def _build_link(self, parent: tk.Misc, text: str, url: str) -> ttk.Label:
        """Tworzy klikalny link otwierający URL w przeglądarce."""
        link = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2")
        link.pack(pady=(8, 0))
        link.bind("<Button-1>", lambda _event: self._open(url))
        return link

    def _open(self, url: str) -> None:
        """Otwiera URL w domyślnej przeglądarce."""
        try:
            webbrowser.open(url)
        except OSError as exc:
            logger.warning("Nie udało się otworzyć %s: %s", url, exc)
