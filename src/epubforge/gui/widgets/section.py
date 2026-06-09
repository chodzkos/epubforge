"""Sekcja UI oparta o ttk.LabelFrame."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Section(ttk.LabelFrame):
    """Opakowanie dla grupy powiązanych kontrolek."""

    def __init__(self, parent: tk.Misc, title: str, padding: int = 10) -> None:
        super().__init__(parent, text=title, padding=padding)
