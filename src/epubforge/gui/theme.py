"""Motywy jasny i ciemny dla GUI."""

from __future__ import annotations

import tkinter as tk
from contextlib import suppress
from tkinter import ttk
from typing import Any, cast

Theme = dict[str, str]

DARK: Theme = {
    "bg": "#1e2028",
    "bg2": "#252830",
    "bg3": "#2d3040",
    "fg": "#dde1ec",
    "fg2": "#8b90a7",
    "fg3": "#555a70",
    "accent": "#5dcaa5",
    "accent2": "#1d9e75",
    "border": "#383c50",
    "red": "#e25454",
    "amber": "#ef9f27",
}

LIGHT: Theme = {
    "bg": "#ffffff",
    "bg2": "#f5f5f5",
    "bg3": "#e8e8ed",
    "fg": "#1d1d1f",
    "fg2": "#515154",
    "fg3": "#86868b",
    "accent": "#1d9e75",
    "accent2": "#0f7c5b",
    "border": "#d1d1d6",
    "red": "#d70015",
    "amber": "#b25000",
}


def apply_theme(root: tk.Misc, theme: Theme) -> None:
    """Aplikuje motyw do ttk style i rekurencyjnie do widgetów klasycznych."""
    _configure_ttk_style(root, theme)
    _apply_widget_theme(root, theme)


def _configure_ttk_style(root: tk.Misc, theme: Theme) -> None:
    """Konfiguruje style ttk dla danego motywu."""
    style = ttk.Style(root)
    with suppress(tk.TclError):
        style.theme_use("clam")

    style.configure(
        ".", background=theme["bg2"], foreground=theme["fg"], fieldbackground=theme["bg3"]
    )
    style.configure("TFrame", background=theme["bg2"])
    style.configure("Root.TFrame", background=theme["bg"])
    style.configure("TLabel", background=theme["bg2"], foreground=theme["fg"])
    style.configure("Muted.TLabel", background=theme["bg2"], foreground=theme["fg2"])
    style.configure(
        "Link.TLabel",
        background=theme["bg2"],
        foreground=theme["accent"],
        font=("TkDefaultFont", 10, "underline"),
    )
    style.configure(
        "Title.TLabel",
        background=theme["bg"],
        foreground=theme["fg"],
        font=("TkDefaultFont", 15, "bold"),
    )
    style.configure(
        "TButton", background=theme["bg3"], foreground=theme["fg"], bordercolor=theme["border"]
    )
    style.map("TButton", background=[("active", theme["bg2"])])
    style.configure("TCheckbutton", background=theme["bg2"], foreground=theme["fg"])
    style.map("TCheckbutton", background=[("active", theme["bg2"])])
    style.configure(
        "TEntry", fieldbackground=theme["bg3"], foreground=theme["fg"], insertcolor=theme["accent"]
    )
    style.configure("TLabelframe", background=theme["bg2"], bordercolor=theme["border"])
    style.configure("TLabelframe.Label", background=theme["bg2"], foreground=theme["fg"])
    style.configure("TNotebook", background=theme["bg"], borderwidth=0)
    style.configure(
        "TNotebook.Tab", background=theme["bg3"], foreground=theme["fg"], padding=(12, 6)
    )
    style.map("TNotebook.Tab", background=[("selected", theme["bg2"])])


def _apply_widget_theme(widget: tk.Misc, theme: Theme) -> None:
    """Aplikuje kolory do widgetów tkinter, które nie korzystają ze style ttk."""
    class_name = widget.winfo_class()
    try:
        if class_name in {"Tk", "Toplevel"}:
            _safe_configure(widget, bg=theme["bg"])
        elif class_name in {"Frame", "Labelframe"}:
            _safe_configure(widget, bg=theme["bg2"])
        elif class_name == "Label":
            _safe_configure(widget, bg=theme["bg2"], fg=theme["fg"])
        elif class_name == "Button":
            _safe_configure(widget, bg=theme["bg3"], fg=theme["fg"], activebackground=theme["bg2"])
        elif class_name == "Entry":
            _safe_configure(
                widget, bg=theme["bg3"], fg=theme["fg"], insertbackground=theme["accent"]
            )
        elif class_name == "Listbox":
            _safe_configure(
                widget,
                bg=theme["bg3"],
                fg=theme["fg"],
                selectbackground=theme["accent2"],
                selectforeground=theme["bg"],
                highlightbackground=theme["border"],
            )
        elif class_name == "Text":
            _safe_configure(
                widget, bg=theme["bg3"], fg=theme["fg"], insertbackground=theme["accent"]
            )
        elif class_name in {"Checkbutton", "Radiobutton"}:
            _safe_configure(widget, bg=theme["bg2"], fg=theme["fg"], activebackground=theme["bg2"])
    except tk.TclError:
        pass

    for child in widget.winfo_children():
        _apply_widget_theme(child, theme)


def _safe_configure(widget: tk.Misc, **options: str) -> None:
    """Konfiguruje widget dynamicznymi opcjami tkinter."""
    cast(Any, widget).configure(**options)
