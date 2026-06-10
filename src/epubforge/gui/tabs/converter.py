"""Zakładka konwersji formatów wejściowych do EPUB."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import cast

from epubforge.converters import SUPPORTED_INPUT_EXTENSIONS, ConvertOptions, to_epub
from epubforge.converters.to_epub import Engine
from epubforge.core import Metadata
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.gui.streaming import LogStreamer
from epubforge.gui.widgets import FileList, PathEntry, Section

# Najczęstsze kody języków dla dropdownu (kolejność = priorytet wyświetlania).
_LANGUAGES = ["pl", "en", "de", "fr", "es", "it", "ru", "cs", "uk", "nl", "pt"]

_PDF_WARNING = (
    "Konwersja PDF → EPUB jest eksperymentalna. Calibre wstawia sztywne "
    "marginesy i może łamać akapity. Najlepsze wyniki dla prostych PDF "
    "tekstowych. Kontynuować?"
)


class ConverterTab(ttk.Frame):
    """Zakładka konwersji TXT/DOCX/HTML/MD/PDF… → EPUB."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=12)
        self.title_var = tk.StringVar()
        self.author_var = tk.StringVar()
        self.language_var = tk.StringVar(value="pl")
        self.engine_var = tk.StringVar(value="auto")
        self.status_var = tk.StringVar(value="Dodaj pliki wejściowe")
        self._converting = False

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
        self._build_options(right)
        self._build_log(right)

        status = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")
        status.pack(fill="x", pady=(10, 0))

    def _build_file_list(self, parent: tk.Misc) -> None:
        """Buduje listę plików wejściowych z potwierdzeniem PDF."""
        section = Section(parent, "Pliki wejściowe")
        section.pack(fill="both", expand=True)
        self.file_list = FileList(
            section,
            extensions=SUPPORTED_INPUT_EXTENSIONS,
            confirm=self._confirm_file,
        )
        self.file_list.pack(fill="both", expand=True)

    def _build_options(self, parent: tk.Misc) -> None:
        """Buduje formularz metadanych, okładki, silnika i wyjścia."""
        section = Section(parent, "Opcje konwersji")
        section.pack(fill="x")
        section.columnconfigure(1, weight=1)

        ttk.Label(section, text="Tytuł").grid(row=0, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Entry(section, textvariable=self.title_var).grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(section, text="Autor").grid(row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Entry(section, textvariable=self.author_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(section, text="Język").grid(row=2, column=0, sticky="w", pady=3, padx=(0, 8))
        ttk.Combobox(
            section,
            textvariable=self.language_var,
            values=_LANGUAGES,
            state="readonly",
            width=8,
        ).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(section, text="Okładka").grid(row=3, column=0, sticky="w", pady=3, padx=(0, 8))
        self.cover_entry = PathEntry(
            section,
            mode="file",
            filetypes=[("Obrazy", "*.jpg *.jpeg *.png *.gif"), ("Wszystkie pliki", "*.*")],
        )
        self.cover_entry.grid(row=3, column=1, sticky="ew", pady=3)

        ttk.Label(section, text="Silnik").grid(row=4, column=0, sticky="w", pady=3, padx=(0, 8))
        engines = ttk.Frame(section)
        engines.grid(row=4, column=1, sticky="w", pady=3)
        for value, label in (("auto", "Auto"), ("pandoc", "Pandoc"), ("calibre", "Calibre")):
            ttk.Radiobutton(engines, text=label, value=value, variable=self.engine_var).pack(
                side="left", padx=(0, 8)
            )

        ttk.Label(section, text="Folder wyjściowy").grid(
            row=5, column=0, sticky="w", pady=3, padx=(0, 8)
        )
        self.output_entry = PathEntry(section, mode="dir")
        self.output_entry.grid(row=5, column=1, sticky="ew", pady=3)

        self.convert_button = ttk.Button(section, text="Konwertuj", command=self._convert)
        self.convert_button.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_log(self, parent: tk.Misc) -> None:
        """Buduje pole logu konwersji."""
        section = Section(parent, "Log")
        section.pack(fill="both", expand=True, pady=(10, 0))
        section.columnconfigure(0, weight=1)
        section.rowconfigure(0, weight=1)

        self.log_text = tk.Text(section, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(section, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    # ── Logika ────────────────────────────────────────────────────────────────

    def _confirm_file(self, path: Path) -> bool:
        """Dla plików PDF wymaga potwierdzenia (konwersja eksperymentalna)."""
        if path.suffix.lower() != ".pdf":
            return True
        return messagebox.askyesno("Konwersja PDF → EPUB", _PDF_WARNING)

    def _build_convert_options(self) -> ConvertOptions:
        """Składa opcje konwersji z aktualnych wartości formularza."""
        author = self.author_var.get().strip()
        metadata = Metadata(
            title=self.title_var.get().strip(),
            creators=[author] if author else [],
            language=self.language_var.get().strip() or "en",
        )
        cover = self.cover_entry.get()
        return ConvertOptions(
            metadata=metadata,
            cover_image=Path(cover) if cover else None,
        )

    def _convert(self) -> None:
        """Waliduje wejście i uruchamia konwersję w osobnym wątku."""
        if self._converting:
            return
        files = self.file_list.files()
        if not files:
            self.status_var.set("Brak plików do konwersji")
            return
        output = self.output_entry.get()
        if not output or not Path(output).is_dir():
            self.status_var.set("Wskaż istniejący folder wyjściowy")
            return

        self._converting = True
        self.convert_button.state(["disabled"])
        self.streamer.clear()
        self.status_var.set("Konwertowanie...")

        options = self._build_convert_options()
        engine = cast(Engine, self.engine_var.get())
        output_dir = Path(output)
        thread = threading.Thread(
            target=self._run_conversion,
            args=(files, output_dir, options, engine),
            daemon=True,
        )
        thread.start()

    def _run_conversion(
        self,
        files: list[Path],
        output_dir: Path,
        options: ConvertOptions,
        engine: Engine,
    ) -> None:
        """Konwertuje pliki po kolei (wątek roboczy) i streamuje log."""
        succeeded = 0
        for source in files:
            target = output_dir / f"{source.stem}.epub"
            self.streamer.write(f"→ {source.name} → {target.name}\n", "cmd")
            try:
                result = to_epub(source, target, options, engine)
            except (ConverterNotFoundError, ConversionError) as exc:
                self.streamer.write(f"BŁĄD: {exc}\n", "err")
                continue
            if result.log:
                self.streamer.write(f"{result.log}\n", "info")
            self.streamer.write(f"OK [{result.engine}]: {target.name}\n", "ok")
            succeeded += 1
        self.after(0, lambda: self._finish_conversion(succeeded, len(files)))

    def _finish_conversion(self, succeeded: int, total: int) -> None:
        """Aktualizuje UI po zakończeniu konwersji (wątek główny)."""
        self._converting = False
        self.convert_button.state(["!disabled"])
        self.status_var.set(f"Zakończono: {succeeded}/{total} OK")
