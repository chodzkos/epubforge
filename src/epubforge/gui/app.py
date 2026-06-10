"""Główna aplikacja tkinter dla EpubForge."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from epubforge import __version__
from epubforge.core import Tool, default_config_path, detect_with_cache, load_config, save_config
from epubforge.core.config import Config
from epubforge.gui.tabs import AboutTab, ConverterTab, FixerTab, KfxTab, MetadataTab
from epubforge.gui.theme import Theme, apply_theme, resolve_theme_name, theme_for_name
from epubforge.gui.window_theme import refresh_titlebar, set_titlebar_dark

logger = logging.getLogger(__name__)

# Dozwolone wartości ustawienia motywu w config.json.
_THEME_SETTINGS = ("auto", "light", "dark")


class App(tk.Tk):
    """Główne okno aplikacji EpubForge."""

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        # Załaduj natywny tkdnd do interpretera Tk — bez tego widgety mają
        # metody drag&drop (monkeypatch tkinterdnd2), ale komendy Tcl nie istnieją.
        self.dnd_available = self._init_tkdnd()
        self.config_path = default_config_path() if config_path is None else config_path
        self.config_data: Config = load_config(self.config_path)
        self.tools: dict[str, Tool] = {}
        self.status_var = tk.StringVar(value="Wykrywanie narzędzi...")
        self.theme_setting = self._initial_theme_setting()
        self.theme_var = tk.StringVar(value=self.theme_setting)
        self.theme_name = resolve_theme_name(self.theme_setting)
        self.theme: Theme = theme_for_name(self.theme_name)
        self.title(f"EpubForge {__version__}")
        self.geometry(str(self.config_data.get("geometry") or "980x680"))
        self.minsize(760, 520)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_status()

        self._build_menu()
        self.root_frame = ttk.Frame(self, style="Root.TFrame", padding=12)
        self.root_frame.pack(fill="both", expand=True)

        self._build_header()
        self._build_notebook()
        self._build_status_bar()
        # Zastosuj motyw po zbudowaniu widgetów (bez refresh — okno dopiero powstaje).
        self._apply_current_theme()

    def _init_tkdnd(self) -> bool:
        """Ładuje pakiet tkdnd do tego okna (jak robi ``TkinterDnD.Tk``).

        Robimy to na już utworzonym ``tk.Tk``, więc gdy natywna biblioteka tkdnd
        jest niedostępna, aplikacja działa dalej — tylko bez przeciągania plików.

        Returns:
            ``True`` gdy tkdnd się załadował, inaczej ``False``.
        """
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD._require(self)
        except (ImportError, tk.TclError, RuntimeError) as exc:
            logger.warning("Drag&drop niedostępne — tkdnd nie załadowane: %s", exc)
            return False
        return True

    def _build_menu(self) -> None:
        """Buduje pasek menu z 'Widok → Motyw' (Automatyczny/Jasny/Ciemny)."""
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=False)
        theme_menu = tk.Menu(view_menu, tearoff=False)
        for label, value in (("Automatyczny", "auto"), ("Jasny", "light"), ("Ciemny", "dark")):
            theme_menu.add_radiobutton(
                label=label,
                value=value,
                variable=self.theme_var,
                command=self._on_theme_menu,
            )
        view_menu.add_cascade(label="Motyw", menu=theme_menu)
        menubar.add_cascade(label="Widok", menu=view_menu)
        self.configure(menu=menubar)

    def _build_header(self) -> None:
        """Buduje górny pasek z tytułem aplikacji."""
        header = ttk.Frame(self.root_frame, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 10))
        title = ttk.Label(header, text="EpubForge", style="Title.TLabel")
        title.pack(side="left")

    def _build_notebook(self) -> None:
        """Buduje notebook z zakładkami roboczymi."""
        self.notebook = ttk.Notebook(self.root_frame)
        self.notebook.pack(fill="both", expand=True)
        self.metadata_tab = MetadataTab(self.notebook, tools=self.tools)
        self.notebook.add(self.metadata_tab, text="Metadane")
        self.converter_tab = ConverterTab(self.notebook, config=self.config_data)
        self.notebook.add(self.converter_tab, text="Konwerter")
        self.fixer_tab = FixerTab(self.notebook, tools=self.tools)
        self.notebook.add(self.fixer_tab, text="Fixer")
        self.kfx_tab = KfxTab(self.notebook, tools=self.tools, config=self.config_data)
        self.notebook.add(self.kfx_tab, text="Eksport Kindle")
        self.about_tab = AboutTab(self.notebook)
        self.notebook.add(self.about_tab, text="O programie")

    def _build_status_bar(self) -> None:
        """Buduje dolny pasek statusu narzędzi."""
        status = ttk.Frame(self.root_frame, style="Root.TFrame")
        status.pack(fill="x", pady=(10, 0))
        self.status_label = ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.pack(side="left")

    def _refresh_status(self) -> None:
        """Wykrywa narzędzia i odświeża pasek statusu."""
        try:
            self.tools = detect_with_cache(self.config_path)
        except OSError:
            self.status_var.set("Nie udało się odczytać statusu narzędzi")
            return
        self.status_var.set(_format_tools_status(self.tools))

    def _initial_theme_setting(self) -> str:
        """Zwraca ustawienie motywu z configu (auto/light/dark), domyślnie auto."""
        value = self.config_data.get("theme")
        return value if value in _THEME_SETTINGS else "auto"

    def _on_theme_menu(self) -> None:
        """Reaguje na wybór motywu z menu."""
        self._set_theme_setting(self.theme_var.get())

    def _set_theme_setting(self, setting: str) -> None:
        """Ustawia tryb motywu, zapisuje w configu i stosuje go."""
        new_name = resolve_theme_name(setting)
        changed = new_name != self.theme_name
        self.theme_setting = setting
        self.theme_var.set(setting)
        self.config_data["theme"] = setting
        self._apply_current_theme(refresh=changed)

    def _apply_current_theme(self, *, refresh: bool = False) -> None:
        """Rozwiązuje ustawienie na konkretny motyw i stosuje go do okna.

        Args:
            refresh: czy wymusić przemalowanie paska tytułu (Win10) — tylko gdy
                motyw faktycznie się zmienił, by uniknąć zbędnego mrugnięcia.
        """
        self.theme_name = resolve_theme_name(self.theme_setting)
        self.theme = theme_for_name(self.theme_name)
        apply_theme(self, self.theme)
        set_titlebar_dark(self, self.theme_name == "dark")
        if refresh:
            refresh_titlebar(self)

    def _on_close(self) -> None:
        """Zapisuje konfigurację i zamyka okno."""
        current = load_config(self.config_path)
        current.update(self.config_data)
        current["theme"] = self.theme_setting
        current["geometry"] = self.geometry()
        self.config_data = current
        save_config(self.config_path, current)
        self.destroy()


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


def main() -> None:
    """Entry point ``epubforge-gui``."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
