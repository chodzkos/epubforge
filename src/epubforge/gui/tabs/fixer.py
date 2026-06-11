"""Zakładka GUI do naprawy plików EPUB."""

from __future__ import annotations

import logging
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import cast

from epubforge.core import Epub, Tool, Tools
from epubforge.fixers import CssFixOptions, HyphenationOptions, fix_css, hyphenate
from epubforge.fixers.hyphenator import HyphenationMethod
from epubforge.gui.streaming import CREATE_NO_WINDOW, LogStreamer
from epubforge.gui.widgets import FileList, Section, Toggle, Tooltip

logger = logging.getLogger(__name__)

_LANGUAGES = ["pl", "en", "en_US", "en_GB", "de", "fr", "es", "it", "cs", "uk"]


class FixerTab(ttk.Frame):
    """Zakładka do hyphenacji i normalizacji CSS w plikach EPUB."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent, padding=12)
        self.tools = tools if tools is not None else {"calibre_viewer": Tools.calibre_viewer()}
        self.last_fixed_file: Path | None = None
        self._running = False

        self.hyphen_lang_var = tk.StringVar(value="pl")
        self.hyphen_method_var = tk.StringVar(value="soft-hyphen")
        self.css_margin_px_var = tk.StringVar(value="20")
        self.status_var = tk.StringVar(value="Dodaj pliki EPUB")

        self._build_layout()
        self.streamer = LogStreamer(self.log_text)
        self.streamer.start_polling()
        self._refresh_preview_button()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Buduje dwukolumnowy układ: pliki po lewej, opcje po prawej."""
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 10, 0))
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=2)

        self._build_file_list(left)
        self._build_options(right)
        self._build_log(right)
        self._build_actions(right)

        status = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")
        status.pack(fill="x", pady=(10, 0))

    def _build_file_list(self, parent: tk.Misc) -> None:
        """Buduje listę plików EPUB."""
        section = Section(parent, "Pliki EPUB")
        section.pack(fill="both", expand=True)
        self.file_list = FileList(section, extensions={".epub"}, on_change=self._on_files_changed)
        self.file_list.pack(fill="both", expand=True)

    def _build_options(self, parent: tk.Misc) -> None:
        """Buduje sekcje opcji hyphenacji i CSS."""
        options = ttk.Frame(parent)
        options.pack(fill="x")
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)

        self._build_hyphenation_section(options)
        self._build_css_section(options)

    def _build_hyphenation_section(self, parent: tk.Misc) -> None:
        """Buduje opcje dzielenia wyrazów."""
        section = Section(parent, "Hyphenation")
        section.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        section.columnconfigure(1, weight=1)

        self.hyphen_enabled_toggle = Toggle(section, text="Włącz", value=True)
        self.hyphen_enabled_toggle.grid(row=0, column=0, columnspan=2, sticky="w")
        Tooltip(
            self.hyphen_enabled_toggle.checkbutton, "Włącz dzielenie wyrazów dla wybranych EPUB"
        )

        ttk.Label(section, text="Język").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        lang_box = ttk.Combobox(
            section,
            textvariable=self.hyphen_lang_var,
            values=_LANGUAGES,
            state="readonly",
            width=10,
        )
        lang_box.grid(row=1, column=1, sticky="w", pady=4)
        Tooltip(lang_box, "Język słownika dzielenia wyrazów (pyphen), np. pl, en_US")

        ttk.Label(section, text="Metoda").grid(row=2, column=0, sticky="nw", pady=4, padx=(0, 8))
        methods = ttk.Frame(section)
        methods.grid(row=2, column=1, sticky="w", pady=4)
        _method_tooltips = {
            "soft-hyphen": (
                "Wstawia miękkie myślniki (\\u00ad) w tekście. Działa na KAŻDYM "
                "czytniku (też starym Kindle), ALE psuje słownik i wyszukiwarkę "
                "na czytniku."
            ),
            "css": (
                "Wstrzykuje regułę CSS 'hyphens: auto' — czysty tekst, ale słabo "
                "wspierane na Kindle."
            ),
        }
        for value, label in (("soft-hyphen", "soft-hyphen"), ("css", "css")):
            radio = ttk.Radiobutton(
                methods,
                text=label,
                value=value,
                variable=self.hyphen_method_var,
                command=self._refresh_hyphen_warning,
            )
            radio.pack(anchor="w")
            Tooltip(radio, _method_tooltips[value])

        self.hyphen_warning_label = ttk.Label(
            section,
            text="Soft-hyphen może psuć słownik i wyszukiwarkę na czytniku Kindle.",
            style="Muted.TLabel",
            wraplength=260,
        )
        self.hyphen_warning_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 6))

        self.hyphen_skip_headers_toggle = Toggle(
            section,
            text="Pomiń nagłówki",
            value=True,
        )
        self.hyphen_skip_headers_toggle.grid(row=4, column=0, columnspan=2, sticky="w")
        Tooltip(
            self.hyphen_skip_headers_toggle.checkbutton,
            "Nie dziel wyrazów w nagłówkach (h1-h3)",
        )

    def _build_css_section(self, parent: tk.Misc) -> None:
        """Buduje opcje normalizacji CSS."""
        section = Section(parent, "CSS Fixer")
        section.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.css_remove_colors_toggle = Toggle(section, text="Usuń kolory", value=False)
        self.css_remove_colors_toggle.pack(anchor="w")
        Tooltip(
            self.css_remove_colors_toggle.checkbutton,
            "Usuwa deklaracje color/background z CSS (czytnik narzuca własne)",
        )

        self.css_remove_fonts_toggle = Toggle(section, text="Usuń fonty", value=False)
        self.css_remove_fonts_toggle.pack(anchor="w")
        Tooltip(
            self.css_remove_fonts_toggle.checkbutton,
            "UWAGA: usuwa @font-face i pliki fontów z EPUB — nieodwracalne dla danej kopii",
        )

        self.css_inject_reset_toggle = Toggle(section, text="Dodaj reset CSS", value=True)
        self.css_inject_reset_toggle.pack(anchor="w")
        Tooltip(
            self.css_inject_reset_toggle.checkbutton,
            "Dodaje delikatny reset (marginesy/padding) dla spójnego renderowania",
        )

        self.css_replace_justify_toggle = Toggle(
            section,
            text="Zamień justowanie na lewe",
            value=False,
        )
        self.css_replace_justify_toggle.pack(anchor="w")
        Tooltip(
            self.css_replace_justify_toggle.checkbutton,
            "Zamienia text-align: justify na left (mniej dużych odstępów)",
        )

        self.css_skip_hyphen_headers_toggle = Toggle(
            section,
            text="Wyłącz hyphenację nagłówków",
            value=True,
        )
        self.css_skip_hyphen_headers_toggle.pack(anchor="w")
        Tooltip(
            self.css_skip_hyphen_headers_toggle.checkbutton,
            "Dodaje regułę CSS wyłączającą dzielenie wyrazów w nagłówkach",
        )

        margin = ttk.Frame(section)
        margin.pack(fill="x", pady=(6, 0))
        self.css_book_margin_toggle = Toggle(margin, text="Margines książki", value=False)
        self.css_book_margin_toggle.pack(side="left")
        Tooltip(
            self.css_book_margin_toggle.checkbutton,
            "Wstrzykuje margines strony (w px) z pola obok",
        )
        self.margin_spinbox = ttk.Spinbox(
            margin,
            from_=0,
            to=120,
            increment=1,
            textvariable=self.css_margin_px_var,
            width=5,
        )
        self.margin_spinbox.pack(side="left", padx=(6, 3))
        Tooltip(self.margin_spinbox, "Szerokość marginesu strony w pikselach (0-120)")
        ttk.Label(margin, text="px").pack(side="left")

    def _build_log(self, parent: tk.Misc) -> None:
        """Buduje pole logu naprawy EPUB."""
        section = Section(parent, "Log")
        section.pack(fill="both", expand=True, pady=(10, 0))
        section.columnconfigure(0, weight=1)
        section.rowconfigure(0, weight=1)

        self.log_text = tk.Text(section, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(section, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _build_actions(self, parent: tk.Misc) -> None:
        """Buduje przyciski uruchomienia i podglądu."""
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(10, 0))

        self.fix_button = ttk.Button(actions, text="Napraw", command=self._run_fix)
        self.fix_button.pack(side="left")
        self.fix_button.state(["disabled"])
        Tooltip(self.fix_button, "Hyphenacja i naprawa CSS wybranych plików (zapis w miejscu).")

        self.preview_button = ttk.Button(
            actions,
            text="Podgląd w Calibre Viewer",
            command=self._view_result,
        )
        self.preview_button.pack(side="right")
        Tooltip(self.preview_button, "Otwiera ostatni naprawiony EPUB w Calibre Viewer")

    # ── Logika ────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        """Aktualizuje stan przycisków po zmianie listy plików."""
        self.last_fixed_file = None
        self.fix_button.state(["!disabled"] if files and not self._running else ["disabled"])
        self._refresh_preview_button()
        self.status_var.set(f"Wybrano {len(files)} {_plural_files(len(files))}")

    def _refresh_hyphen_warning(self) -> None:
        """Pokazuje ostrzeżenie tylko przy metodzie soft-hyphen."""
        if self.hyphen_method_var.get() == "soft-hyphen":
            self.hyphen_warning_label.grid()
        else:
            self.hyphen_warning_label.grid_remove()

    def _build_hyphen_options(self) -> HyphenationOptions | None:
        """Składa opcje hyphenacji z aktualnego stanu UI."""
        if not self.hyphen_enabled_toggle.get():
            return None
        return HyphenationOptions(
            language=self.hyphen_lang_var.get(),
            method=cast(HyphenationMethod, self.hyphen_method_var.get()),
            skip_headers=self.hyphen_skip_headers_toggle.get(),
        )

    def _build_css_options(self) -> CssFixOptions:
        """Składa opcje CSS fixer z aktualnego stanu UI."""
        return CssFixOptions(
            remove_colors=self.css_remove_colors_toggle.get(),
            remove_fonts=self.css_remove_fonts_toggle.get(),
            inject_reset=self.css_inject_reset_toggle.get(),
            replace_justify="left" if self.css_replace_justify_toggle.get() else "keep",
            inject_book_margin_px=self._book_margin_px(),
            skip_hyphenation_headers=self.css_skip_hyphen_headers_toggle.get(),
        )

    def _book_margin_px(self) -> int | None:
        """Zwraca margines książki w px albo None, jeśli opcja jest wyłączona."""
        if not self.css_book_margin_toggle.get():
            return None
        try:
            return max(0, int(self.css_margin_px_var.get()))
        except ValueError:
            return None

    def _run_fix(self) -> None:
        """Waliduje wejście i uruchamia naprawę w osobnym wątku."""
        if self._running:
            return
        files = self.file_list.files()
        if not files:
            self.status_var.set("Brak plików EPUB do naprawy")
            return

        self._running = True
        self.last_fixed_file = None
        self.fix_button.state(["disabled"])
        self.preview_button.state(["disabled"])
        self.streamer.clear()
        self.status_var.set("Naprawianie...")

        thread = threading.Thread(
            target=self._run_worker,
            args=(files, self._build_hyphen_options(), self._build_css_options()),
            daemon=True,
        )
        thread.start()

    def _run_worker(
        self,
        files: list[Path],
        hyphen_options: HyphenationOptions | None,
        css_options: CssFixOptions,
    ) -> None:
        """Naprawia pliki po kolei w wątku roboczym."""
        succeeded = 0
        last_fixed: Path | None = None
        total = len(files)
        for index, path in enumerate(files, start=1):
            self.after(0, self.status_var.set, f"Naprawianie {index}/{total}: {path.name}")
            self.streamer.write(f"→ {path.name}\n", "cmd")
            try:
                with Epub(path) as epub:
                    if hyphen_options is not None:
                        self.streamer.write("Hyphenation...\n", "info")
                        hyphenate(epub, hyphen_options)
                    self.streamer.write("CSS Fixer...\n", "info")
                    fix_css(epub, css_options)
                    last_fixed = epub.save()
            except Exception as exc:
                logger.exception("Nie udało się naprawić EPUB: %s", path)
                self.streamer.write(f"BŁĄD: {exc}\n", "err")
                continue
            self.streamer.write(f"OK: {last_fixed}\n", "ok")
            succeeded += 1

        self.after(0, self._finish_fix, succeeded, total, last_fixed)

    def _finish_fix(self, succeeded: int, total: int, last_fixed: Path | None) -> None:
        """Aktualizuje UI po zakończeniu pracy wątku."""
        self._running = False
        self.last_fixed_file = last_fixed
        self.fix_button.state(["!disabled"] if self.file_list.files() else ["disabled"])
        self._refresh_preview_button()
        self.status_var.set(f"Zakończono: {succeeded}/{total} OK")

    def _refresh_preview_button(self) -> None:
        """Włącza podgląd tylko po sukcesie i przy wykrytym Calibre Viewer."""
        if self.last_fixed_file is not None and self._viewer_tool() is not None:
            self.preview_button.state(["!disabled"])
        else:
            self.preview_button.state(["disabled"])

    def _viewer_tool(self) -> Tool | None:
        """Zwraca dostępny Calibre Viewer albo None."""
        viewer = self.tools.get("calibre_viewer")
        if viewer is None or not viewer.available or viewer.path is None:
            return None
        return viewer

    def _view_result(self) -> None:
        """Otwiera ostatni naprawiony EPUB w Calibre Viewer."""
        viewer = self._viewer_tool()
        if self.last_fixed_file is None or viewer is None or viewer.path is None:
            self.status_var.set("Nie wykryto Calibre Viewer albo brak wyniku")
            return
        try:
            subprocess.Popen(
                [str(viewer.path), str(self.last_fixed_file)],
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self.streamer.write(f"BŁĄD: Nie udało się otworzyć podglądu: {exc}\n", "err")
            return
        self.streamer.write(f"Uruchomiono podgląd: {self.last_fixed_file.name}\n", "info")


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
