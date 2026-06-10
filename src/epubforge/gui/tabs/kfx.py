"""Zakładka GUI konwersji EPUB do KFX."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import cast

from epubforge.converters import KfxOptions, to_kfx
from epubforge.converters.to_kfx import KfxEngine
from epubforge.core import Tool
from epubforge.gui.streaming import LogStreamer
from epubforge.gui.widgets import FileList, PathEntry, Section, Toggle

logger = logging.getLogger(__name__)

_KP3_WARNING = (
    "Kindle Previewer 3 jest eksperymentalny i bardziej wrażliwy na błędy EPUB. "
    "Przed konwersją usuń niestandardowe fonty, uprość CSS, unikaj wymuszonych "
    "marginesów i zostaw włączoną naprawę EPUB. Jeśli konwersja się nie powiedzie, "
    "wróć do silnika Calibre + wtyczka KFX Output."
)


class KfxTab(ttk.Frame):
    """Zakładka do batchowej konwersji plików EPUB na KFX."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent, padding=12)
        self.tools = tools if tools is not None else {}
        self._running = False

        self.engine_var = tk.StringVar(value="calibre")
        self.status_var = tk.StringVar(value="Dodaj pliki EPUB")
        self.progress_var = tk.IntVar(value=0)

        self._build_layout()
        self.streamer = LogStreamer(self.log_text)
        self.streamer.start_polling()

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
        self._build_engine_section(right)
        self._build_options_section(right)
        self._build_log(right)
        self._build_actions(right)
        self._build_status()

    def _build_file_list(self, parent: tk.Misc) -> None:
        """Buduje listę plików EPUB."""
        section = Section(parent, "Pliki EPUB")
        section.pack(fill="both", expand=True)
        self.file_list = FileList(section, extensions={".epub"}, on_change=self._on_files_changed)
        self.file_list.pack(fill="both", expand=True)

    def _build_engine_section(self, parent: tk.Misc) -> None:
        """Buduje sekcję wyboru silnika konwersji."""
        section = Section(parent, "Silnik konwersji")
        section.pack(fill="x")

        calibre = ttk.Frame(section)
        calibre.pack(fill="x")
        ttk.Radiobutton(
            calibre,
            text="Calibre + wtyczka KFX",
            value="calibre",
            variable=self.engine_var,
            command=self._refresh_kp3_warning,
        ).pack(side="left")
        ttk.Label(calibre, text="ZALECANE", style="Muted.TLabel").pack(side="left", padx=(8, 0))

        kp3 = ttk.Frame(section)
        kp3.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(
            kp3,
            text="Kindle Previewer 3",
            value="kindle-previewer",
            variable=self.engine_var,
            command=self._refresh_kp3_warning,
        ).pack(side="left")
        ttk.Label(
            kp3,
            text="EKSPERYMENTALNE - wrażliwe na formatowanie",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        self.kp3_warning_text = tk.Text(section, height=4, wrap="word", state="disabled")
        self.kp3_warning_text.configure(width=1)
        self._set_warning_text(_KP3_WARNING)

    def _build_options_section(self, parent: tk.Misc) -> None:
        """Buduje pozostałe opcje konwersji KFX."""
        section = Section(parent, "Opcje")
        section.pack(fill="x", pady=(10, 0))
        section.columnconfigure(1, weight=1)

        self.fix_epub_toggle = Toggle(section, text="Napraw EPUB przed konwersją", value=True)
        self.fix_epub_toggle.grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(section, text="Folder wyjściowy").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(8, 0),
            padx=(0, 8),
        )
        self.output_dir = PathEntry(section, mode="dir")
        self.output_dir.grid(row=1, column=1, sticky="ew", pady=(8, 0))

    def _build_log(self, parent: tk.Misc) -> None:
        """Buduje pole logu konwersji."""
        section = Section(parent, "Log")
        section.pack(fill="both", expand=True, pady=(10, 0))
        section.columnconfigure(0, weight=1)
        section.rowconfigure(0, weight=1)

        self.log_text = tk.Text(section, height=9, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(section, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _build_actions(self, parent: tk.Misc) -> None:
        """Buduje przycisk konwersji."""
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(10, 0))

        self.convert_button = ttk.Button(
            actions,
            text="Konwertuj do KFX",
            command=self._run_conversion,
        )
        self.convert_button.pack(side="right")
        self.convert_button.state(["disabled"])

    def _build_status(self) -> None:
        """Buduje pasek statusu i postępu batch processing."""
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", pady=(10, 0))

        status = ttk.Label(status_frame, textvariable=self.status_var, style="Muted.TLabel")
        status.pack(side="left")

        self.progress_bar = ttk.Progressbar(
            status_frame,
            variable=self.progress_var,
            mode="determinate",
        )
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(10, 0))

    # ── Logika ────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        """Aktualizuje stan przycisku po zmianie listy plików."""
        self.convert_button.state(["!disabled"] if files and not self._running else ["disabled"])
        self.status_var.set(f"Wybrano {len(files)} {_plural_files(len(files))} EPUB")

    def _refresh_kp3_warning(self) -> None:
        """Pokazuje ostrzeżenie poradnikowe przy eksperymentalnym KP3."""
        if self.engine_var.get() == "kindle-previewer":
            self.kp3_warning_text.pack(fill="x", pady=(8, 0))
        else:
            self.kp3_warning_text.pack_forget()

    def _build_options_obj(self) -> KfxOptions:
        """Składa KfxOptions z aktualnego stanu formularza."""
        return KfxOptions(
            engine=cast(KfxEngine, self.engine_var.get()),
            fix_epub_first=self.fix_epub_toggle.get(),
        )

    def _run_conversion(self) -> None:
        """Waliduje formularz i uruchamia konwersję w osobnym wątku."""
        if self._running:
            return
        files = self.file_list.files()
        if not files:
            self.status_var.set("Brak plików EPUB do konwersji")
            return
        output = self.output_dir.get()
        if not output:
            self.streamer.write("BŁĄD: Wybierz folder wyjściowy.\n", "err")
            self.status_var.set("Wskaż folder wyjściowy")
            return

        self._running = True
        self.convert_button.state(["disabled"])
        self.streamer.clear()
        self.progress_bar.configure(maximum=len(files))
        self.progress_var.set(0)
        self.status_var.set("Konwersja KFX trwa...")

        thread = threading.Thread(
            target=self._run_worker,
            args=(files, Path(output), self._build_options_obj()),
            daemon=True,
        )
        thread.start()

    def _run_worker(self, files: list[Path], target_dir: Path, options: KfxOptions) -> None:
        """Konwertuje pliki po kolei i aktualizuje postęp."""
        succeeded = 0
        total = len(files)
        for index, source in enumerate(files, start=1):
            self.after(0, self.status_var.set, f"Konwersja {index}/{total}: {source.name}")
            self.streamer.write(f"→ {source.name}\n", "cmd")
            try:
                result = to_kfx(source, target_dir, options)
            except Exception as exc:
                logger.exception("Błąd konwersji KFX: %s", source)
                self.streamer.write(f"BŁĄD: {exc}\n\n", "err")
            else:
                if result.log:
                    self.streamer.write(f"{result.log}\n", "info")
                self.streamer.write(f"OK [{result.engine}]: {result.output_path.name}\n\n", "ok")
                succeeded += 1
            self.after(0, self.progress_var.set, index)

        self.after(0, self._finish_conversion, succeeded, total)

    def _finish_conversion(self, succeeded: int, total: int) -> None:
        """Aktualizuje UI po zakończeniu konwersji."""
        self._running = False
        self.convert_button.state(["!disabled"] if self.file_list.files() else ["disabled"])
        self.status_var.set(f"Zakończono: {succeeded}/{total} OK")

    def _set_warning_text(self, value: str) -> None:
        """Ustawia treść ostrzeżenia KP3 w read-only Text."""
        self.kp3_warning_text.configure(state="normal")
        self.kp3_warning_text.delete("1.0", "end")
        self.kp3_warning_text.insert("1.0", value)
        self.kp3_warning_text.configure(state="disabled")


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
