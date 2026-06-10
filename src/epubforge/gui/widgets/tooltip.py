"""Tooltip dla widgetów tkinter — czytelny w obu motywach."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from epubforge.gui.theme import current_theme


class Tooltip:
    """Prosty tooltip wyświetlany po najechaniu kursorem."""

    def __init__(self, widget: tk.Misc, text: str, delay_ms: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, _event: tk.Event[Any] | None = None) -> None:
        self.after_id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, _event: tk.Event[Any] | None = None) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        self._hide()

    def _show(self) -> None:
        if self.tip_window is not None or not self.text:
            return
        # Kolory z bieżącego motywu — czytelne zarówno w dark, jak i light.
        theme = current_theme()
        x = self.widget.winfo_rootx() + 24
        y = self.widget.winfo_rooty() + 24
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        self.tip_window.configure(bg=theme["border"])
        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            bg=theme["bg3"],
            fg=theme["fg"],
            highlightbackground=theme["border"],
            highlightthickness=1,
            relief="flat",
            borderwidth=0,
            font=("TkDefaultFont", 9),
            padx=8,
            pady=4,
        )
        label.pack(padx=1, pady=1)

    def _hide(self) -> None:
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None
