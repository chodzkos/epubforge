"""Stylizowany przełącznik oparty o ttk.Checkbutton."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class Toggle(ttk.Frame):
    """Lekki przełącznik bool z callbackiem zmiany stanu."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        text: str = "",
        value: bool = False,
        on_change: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.on_change = on_change
        self.var = tk.BooleanVar(value=value)
        self.checkbutton = ttk.Checkbutton(
            self,
            text=text,
            variable=self.var,
            command=self._notify_change,
        )
        self.checkbutton.pack(side="left")

    def get(self) -> bool:
        """Zwraca aktualny stan przełącznika."""
        return bool(self.var.get())

    def set(self, value: bool) -> None:
        """Ustawia stan przełącznika i powiadamia callback."""
        self.var.set(value)
        self._notify_change()

    def _notify_change(self) -> None:
        """Powiadamia callback o zmianie wartości."""
        if self.on_change is not None:
            self.on_change(self.get())
