"""Zakładka GUI eksportu EPUB do formatów Kindle (KFX/MOBI/AZW3)."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import cast

from epubforge.converters import KfxOptions, MobiOptions, to_kfx, to_mobi
from epubforge.converters.to_kfx import KfxEngine
from epubforge.converters.to_mobi import MobiEngine, MobiFormat
from epubforge.core import Tool
from epubforge.core.config import Config
from epubforge.gui.output import remember_output_dir, remembered_output_dir, resolve_output_dir
from epubforge.gui.streaming import LogStreamer
from epubforge.gui.widgets import FileList, PathEntry, Section, Toggle

logger = logging.getLogger(__name__)

_KP3_WARNING = (
    "Kindle Previewer 3 jest eksperymentalny i bardziej wrażliwy na błędy EPUB. "
    "Przed konwersją usuń niestandardowe fonty, uprość CSS, unikaj wymuszonych "
    "marginesów i zostaw włączoną naprawę EPUB. Jeśli konwersja się nie powiedzie, "
    "wróć do silnika Calibre + wtyczka KFX Output."
)
_KINDLEGEN_WARNING = (
    "kindlegen jest oficjalnie wycofany przez Amazon (utknął na wersji 2.9) i nie "
    "jest już rozwijany. Nadal tworzy poprawne pliki MOBI, ale zalecanym, "
    "nowocześniejszym silnikiem jest Calibre ebook-convert."
)


class KfxTab(ttk.Frame):
    """Zakładka batchowego eksportu EPUB do KFX/MOBI/AZW3."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        tools: dict[str, Tool] | None = None,
        config: Config | None = None,
    ) -> None:
        super().__init__(parent, padding=12)
        self.tools = tools if tools is not None else {}
        self.config_data: Config = config if config is not None else {}
        self._running = False

        self.format_var = tk.StringVar(value="kfx")
        self.engine_var = tk.StringVar(value="calibre")
        self.mobi_engine_var = tk.StringVar(value="calibre")
        self.status_var = tk.StringVar(value="Dodaj pliki EPUB")
        self.progress_var = tk.IntVar(value=0)

        self._build_layout()
        self.streamer = LogStreamer(self.log_text)
        self.streamer.start_polling()
        self._on_format_change()

        remembered = remembered_output_dir(self.config_data)
        if remembered:
            self.output_dir.set(remembered)

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
        self._build_format_section(right)
        self._build_engine_sections(right)
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

    def _build_format_section(self, parent: tk.Misc) -> None:
        """Buduje wybór formatu docelowego (KFX / MOBI / AZW3)."""
        section = Section(parent, "Format docelowy")
        section.pack(fill="x")
        for value, label in (("kfx", "KFX"), ("mobi", "MOBI"), ("azw3", "AZW3")):
            ttk.Radiobutton(
                section,
                text=label,
                value=value,
                variable=self.format_var,
                command=self._on_format_change,
            ).pack(side="left", padx=(0, 10))

    def _build_engine_sections(self, parent: tk.Misc) -> None:
        """Buduje kontener z sekcjami silników (KFX i MOBI) — widoczna jedna."""
        self.engine_container = ttk.Frame(parent)
        self.engine_container.pack(fill="x", pady=(10, 0))
        self._build_kfx_engine_section(self.engine_container)
        self._build_mobi_engine_section(self.engine_container)

    def _build_kfx_engine_section(self, parent: tk.Misc) -> None:
        """Buduje sekcję wyboru silnika KFX."""
        self.kfx_engine_section = Section(parent, "Silnik KFX")

        calibre = ttk.Frame(self.kfx_engine_section)
        calibre.pack(fill="x")
        ttk.Radiobutton(
            calibre,
            text="Calibre + wtyczka KFX",
            value="calibre",
            variable=self.engine_var,
            command=self._refresh_kp3_warning,
        ).pack(side="left")
        ttk.Label(calibre, text="ZALECANE", style="Muted.TLabel").pack(side="left", padx=(8, 0))

        kp3 = ttk.Frame(self.kfx_engine_section)
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

        self.kp3_warning_text = tk.Text(self.kfx_engine_section, height=4, wrap="word")
        self.kp3_warning_text.configure(width=1, state="disabled")
        self._set_readonly_text(self.kp3_warning_text, _KP3_WARNING)

    def _build_mobi_engine_section(self, parent: tk.Misc) -> None:
        """Buduje sekcję wyboru silnika MOBI/AZW3."""
        self.mobi_engine_section = Section(parent, "Silnik MOBI/AZW3")

        calibre = ttk.Frame(self.mobi_engine_section)
        calibre.pack(fill="x")
        ttk.Radiobutton(
            calibre,
            text="Calibre ebook-convert",
            value="calibre",
            variable=self.mobi_engine_var,
            command=self._refresh_kindlegen_warning,
        ).pack(side="left")
        ttk.Label(calibre, text="ZALECANE", style="Muted.TLabel").pack(side="left", padx=(8, 0))

        kindlegen = ttk.Frame(self.mobi_engine_section)
        kindlegen.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(
            kindlegen,
            text="kindlegen",
            value="kindlegen",
            variable=self.mobi_engine_var,
            command=self._refresh_kindlegen_warning,
        ).pack(side="left")
        ttk.Label(
            kindlegen,
            text="WYCOFANY - opcjonalny",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        self.kindlegen_warning_text = tk.Text(self.mobi_engine_section, height=3, wrap="word")
        self.kindlegen_warning_text.configure(width=1, state="disabled")
        self._set_readonly_text(self.kindlegen_warning_text, _KINDLEGEN_WARNING)

    def _build_options_section(self, parent: tk.Misc) -> None:
        """Buduje pozostałe opcje konwersji."""
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
            text="Konwertuj",
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

    # ── Reakcje UI ──────────────────────────────────────────────────────────────

    def _on_format_change(self) -> None:
        """Pokazuje sekcję silnika właściwą dla wybranego formatu."""
        is_kfx = self.format_var.get() == "kfx"
        self.kfx_engine_section.pack_forget()
        self.mobi_engine_section.pack_forget()
        if is_kfx:
            self.kfx_engine_section.pack(fill="x")
            self._refresh_kp3_warning()
        else:
            self.mobi_engine_section.pack(fill="x")
            self._refresh_kindlegen_warning()
        self.convert_button.configure(text=f"Konwertuj do {self.format_var.get().upper()}")

    def _on_files_changed(self, files: list[Path]) -> None:
        """Aktualizuje przycisk i podpowiada katalog wyjściowy, gdy pole puste."""
        self.convert_button.state(["!disabled"] if files and not self._running else ["disabled"])
        self.status_var.set(f"Wybrano {len(files)} {_plural_files(len(files))} EPUB")
        if files and not self.output_dir.get().strip():
            self.output_dir.set(str(files[0].parent))

    def _refresh_kp3_warning(self) -> None:
        """Pokazuje porady przy eksperymentalnym KP3 (tylko w trybie KFX)."""
        if self.format_var.get() == "kfx" and self.engine_var.get() == "kindle-previewer":
            self.kp3_warning_text.pack(fill="x", pady=(8, 0))
        else:
            self.kp3_warning_text.pack_forget()

    def _refresh_kindlegen_warning(self) -> None:
        """Pokazuje ostrzeżenie przy wybraniu wycofanego kindlegen."""
        if self.format_var.get() != "kfx" and self.mobi_engine_var.get() == "kindlegen":
            self.kindlegen_warning_text.pack(fill="x", pady=(8, 0))
        else:
            self.kindlegen_warning_text.pack_forget()

    # ── Logika konwersji ─────────────────────────────────────────────────────────

    def _build_options_obj(self) -> KfxOptions:
        """Składa KfxOptions z aktualnego stanu formularza."""
        return KfxOptions(
            engine=cast(KfxEngine, self.engine_var.get()),
            fix_epub_first=self.fix_epub_toggle.get(),
        )

    def _build_mobi_options(self) -> MobiOptions:
        """Składa MobiOptions z aktualnego stanu formularza."""
        return MobiOptions(
            fmt=cast(MobiFormat, self.format_var.get()),
            engine=cast(MobiEngine, self.mobi_engine_var.get()),
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
        output = self.output_dir.get().strip()

        self._running = True
        self.convert_button.state(["disabled"])
        self.streamer.clear()
        self.progress_bar.configure(maximum=len(files))
        self.progress_var.set(0)
        self.status_var.set("Konwersja trwa...")

        remember_output_dir(self.config_data, output)
        output_dir = Path(output) if output else None
        if self.format_var.get() == "kfx":
            thread = threading.Thread(
                target=self._run_worker,
                args=(files, output_dir, self._build_options_obj()),
                daemon=True,
            )
        else:
            thread = threading.Thread(
                target=self._run_mobi_worker,
                args=(files, output_dir, self._build_mobi_options()),
                daemon=True,
            )
        thread.start()

    def _run_worker(self, files: list[Path], target_dir: Path | None, options: KfxOptions) -> None:
        """Konwertuje pliki do KFX po kolei i aktualizuje postęp.

        ``target_dir`` ``None`` (puste pole) oznacza zapis obok każdego źródła.
        """
        succeeded = 0
        total = len(files)
        for index, source in enumerate(files, start=1):
            self.after(0, self.status_var.set, f"Konwersja {index}/{total}: {source.name}")
            self.streamer.write(f"→ {source.name}\n", "cmd")
            try:
                result = to_kfx(source, resolve_output_dir(target_dir, source), options)
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

    def _run_mobi_worker(
        self, files: list[Path], target_dir: Path | None, options: MobiOptions
    ) -> None:
        """Konwertuje pliki do MOBI/AZW3 po kolei i aktualizuje postęp.

        ``target_dir`` ``None`` (puste pole) oznacza zapis obok każdego źródła.
        """
        succeeded = 0
        total = len(files)
        for index, source in enumerate(files, start=1):
            self.after(0, self.status_var.set, f"Konwersja {index}/{total}: {source.name}")
            self.streamer.write(f"→ {source.name}\n", "cmd")
            target = resolve_output_dir(target_dir, source) / f"{source.stem}.{options.fmt}"
            try:
                result = to_mobi(source, target, options)
            except Exception as exc:
                logger.exception("Błąd konwersji MOBI/AZW3: %s", source)
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

    def _set_readonly_text(self, widget: tk.Text, value: str) -> None:
        """Ustawia treść read-only pola Text."""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
