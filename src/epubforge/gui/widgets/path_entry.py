"""Pole ścieżki z przyciskiem wyboru pliku lub katalogu."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import filedialog, ttk
from typing import Literal

PathMode = Literal["dir", "file", "save"]
FileTypes = Sequence[tuple[str, str]]


class PathEntry(ttk.Frame):
    """Pole tekstowe z przyciskiem wyboru ścieżki."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        mode: PathMode = "dir",
        filetypes: FileTypes | None = None,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.filetypes: FileTypes = filetypes or [("Wszystkie pliki", "*.*")]
        self.on_change = on_change
        self.var = tk.StringVar()
        self.var.trace_add("write", self._notify_change)

        self.entry = ttk.Entry(self, textvariable=self.var)
        self.entry.pack(side="left", fill="x", expand=True)
        self.button = ttk.Button(self, text="...", width=3, command=self._browse)
        self.button.pack(side="right", padx=(6, 0))

    def get(self) -> str:
        """Zwraca aktualną ścieżkę bez białych znaków na końcach."""
        return self.var.get().strip()

    def set(self, value: str) -> None:
        """Ustawia wartość pola."""
        self.var.set(value)

    def _browse(self) -> None:
        """Otwiera systemowy dialog wyboru ścieżki."""
        if self.mode == "dir":
            path = filedialog.askdirectory()
        elif self.mode == "file":
            path = filedialog.askopenfilename(filetypes=self.filetypes)
        else:
            path = filedialog.asksaveasfilename(filetypes=self.filetypes)
        if path:
            self.var.set(path)

    def _notify_change(self, *_args: str) -> None:
        """Powiadamia callback o zmianie wartości."""
        if self.on_change is not None:
            self.on_change(self.get())
