"""Główna aplikacja tkinter dla EpubForge."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from epubforge import __version__
from epubforge.core import Tool, default_config_path, detect_with_cache, load_config, save_config
from epubforge.core.config import Config
from epubforge.gui.tabs import MetadataTab
from epubforge.gui.theme import DARK, LIGHT, Theme, apply_theme
from epubforge.gui.widgets import Toggle
from epubforge.gui.widgets.tooltip import Tooltip


class App(tk.Tk):
    """Główne okno aplikacji EpubForge."""

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = default_config_path() if config_path is None else config_path
        self.config_data: Config = load_config(self.config_path)
        self.theme_name = self._initial_theme_name()
        self.theme: Theme = DARK if self.theme_name == "dark" else LIGHT
        self.title(f"EpubForge {__version__}")
        self.geometry(str(self.config_data.get("geometry") or "980x680"))
        self.minsize(760, 520)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root_frame = ttk.Frame(self, style="Root.TFrame", padding=12)
        self.root_frame.pack(fill="both", expand=True)

        self._build_header()
        self._build_notebook()
        self._build_status_bar()
        apply_theme(self, self.theme)
        self._refresh_status()

    def _build_header(self) -> None:
        """Buduje górny pasek tytułu i przełącznik motywu."""
        header = ttk.Frame(self.root_frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 10))
        title = ttk.Label(header, text="EpubForge", style="Title.TLabel")
        title.pack(side="left")
        self.theme_toggle = Toggle(
            header,
            text="Dark",
            value=self.theme_name == "dark",
            on_change=self._toggle_theme,
        )
        self.theme_toggle.pack(side="right")
        Tooltip(self.theme_toggle, "Przełącz motyw jasny/ciemny")

    def _build_notebook(self) -> None:
        """Buduje notebook z zakładkami roboczymi."""
        self.notebook = ttk.Notebook(self.root_frame)
        self.notebook.pack(fill="both", expand=True)
        self.metadata_tab = MetadataTab(self.notebook)
        self.notebook.add(self.metadata_tab, text="Metadane")

    def _build_status_bar(self) -> None:
        """Buduje dolny pasek statusu narzędzi."""
        self.status_var = tk.StringVar(value="Wykrywanie narzędzi...")
        status = ttk.Frame(self.root_frame, style="Root.TFrame")
        status.pack(fill="x", pady=(10, 0))
        self.status_label = ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.pack(side="left")

    def _refresh_status(self) -> None:
        """Wykrywa narzędzia i odświeża pasek statusu."""
        try:
            tools = detect_with_cache(self.config_path)
        except OSError:
            self.status_var.set("Nie udało się odczytać statusu narzędzi")
            return
        self.status_var.set(_format_tools_status(tools))

    def _toggle_theme(self, enabled: bool) -> None:
        """Przełącza motyw aplikacji."""
        self.theme_name = "dark" if enabled else "light"
        self.theme = DARK if enabled else LIGHT
        apply_theme(self, self.theme)

    def _initial_theme_name(self) -> str:
        """Zwraca nazwę motywu z configu albo domyślny dark."""
        value = self.config_data.get("theme")
        return "light" if value == "light" else "dark"

    def _on_close(self) -> None:
        """Zapisuje konfigurację i zamyka okno."""
        current = load_config(self.config_path)
        current.update(self.config_data)
        current["theme"] = self.theme_name
        current["geometry"] = self.geometry()
        self.config_data = current
        save_config(self.config_path, current)
        self.destroy()


def _format_tools_status(tools: dict[str, Tool]) -> str:
    """Buduje zwięzły opis statusu wykrytych narzędzi."""
    labels = {
        "pandoc": "Pandoc",
        "calibre_ebook_convert": "Calibre",
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


def main() -> None:
    """Entry point ``epubforge-gui``."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
