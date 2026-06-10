"""Lista plików z toolbar i opcjonalnym drag and drop."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, cast

try:
    from tkinterdnd2 import DND_FILES

    HAS_DND = True
except ImportError:
    DND_FILES = "DND_Files"
    HAS_DND = False

logger = logging.getLogger(__name__)

DEFAULT_EXTENSIONS = {".epub", ".txt", ".md", ".markdown", ".docx", ".html", ".htm", ".pdf"}


class FileList(ttk.Frame):
    """Lista plików z przyciskami dodawania, usuwania i czyszczenia."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        extensions: Iterable[str] | None = None,
        on_change: Callable[[list[Path]], None] | None = None,
        confirm: Callable[[Path], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.extensions = {ext.lower() for ext in (extensions or DEFAULT_EXTENSIONS)}
        self.on_change = on_change
        # Hook wołany przed dodaniem pliku — zwrot False pomija plik
        # (np. potwierdzenie eksperymentalnej konwersji PDF).
        self.confirm = confirm
        self._files: list[Path] = []

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))

        ttk.Button(toolbar, text="+ Pliki", command=self._add_files).pack(side="left")
        ttk.Button(toolbar, text="+ Folder", command=self._add_folder).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Usuń", command=self._remove_selected).pack(side="left")
        ttk.Button(toolbar, text="Wyczyść", command=self.clear).pack(side="left", padx=4)

        self.count_label = ttk.Label(toolbar, text="0 plików", style="Muted.TLabel")
        self.count_label.pack(side="right")

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(list_frame, selectmode="extended", height=8)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)

        if HAS_DND:
            self._enable_drag_and_drop()

    def files(self) -> list[Path]:
        """Zwraca kopię listy plików."""
        return list(self._files)

    def add_files(self, paths: Iterable[Path]) -> None:
        """Dodaje pliki spełniające filtr rozszerzeń."""
        changed = False
        for path in paths:
            candidate = Path(path)
            if candidate.suffix.lower() not in self.extensions:
                continue
            if candidate in self._files:
                continue
            if self.confirm is not None and not self.confirm(candidate):
                continue
            self._files.append(candidate)
            changed = True
        if changed:
            self._refresh()

    def clear(self) -> None:
        """Czyści listę plików."""
        if not self._files:
            return
        self._files.clear()
        self._refresh()

    def _add_files(self) -> None:
        """Dodaje pliki wybrane w dialogu systemowym."""
        filetypes = [("Obsługiwane", " ".join(f"*{ext}" for ext in sorted(self.extensions)))]
        paths = filedialog.askopenfilenames(filetypes=filetypes)
        self.add_files(Path(path) for path in paths)

    def _add_folder(self) -> None:
        """Dodaje obsługiwane pliki z wybranego katalogu."""
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.add_files(path for path in Path(folder).iterdir() if path.is_file())

    def _remove_selected(self) -> None:
        """Usuwa zaznaczone pozycje."""
        listbox = cast(Any, self.listbox)
        selection = tuple(int(index) for index in listbox.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self._files.pop(index)
        self._refresh()

    def _on_drop(self, event: Any) -> None:
        """Obsługuje drop plików z tkinterdnd2."""
        raw_paths = self.tk.splitlist(str(event.data))
        self.add_files(Path(path.strip("{}")) for path in raw_paths)

    def _enable_drag_and_drop(self) -> None:
        """Włącza drag&drop, jeśli natywny tkdnd jest faktycznie dostępny.

        Metody ``drop_target_register``/``dnd_bind`` istnieją zawsze (tkinterdnd2
        je monkeypatchuje), ale gdy pakiet tkdnd nie został załadowany do okna,
        ich wywołanie rzuca ``TclError``. Łapiemy to cicho — lista działa dalej,
        tylko bez przeciągania plików.
        """
        drop_register = getattr(self.listbox, "drop_target_register", None)
        dnd_bind = getattr(self.listbox, "dnd_bind", None)
        if not (callable(drop_register) and callable(dnd_bind)):
            return
        try:
            drop_register(DND_FILES)
            dnd_bind("<<Drop>>", self._on_drop)
        except tk.TclError as exc:
            logger.warning("Drag&drop niedostępne: %s", exc)

    def _refresh(self) -> None:
        """Odświeża widok listbox i licznik."""
        self.listbox.delete(0, "end")
        for path in self._files:
            self.listbox.insert("end", f"{path.name}  ({path.parent})")
        count = len(self._files)
        self.count_label.configure(text=f"{count} {_plural_files(count)}")
        if self.on_change is not None:
            self.on_change(self.files())


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
