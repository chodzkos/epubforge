"""Ciemny/jasny pasek tytułu okna na Windows (DWM).

Na Windows pasek tytułu rysuje system (DWM), nie tkinter — kolorujemy go przez
``DwmSetWindowAttribute``. Poza Windows funkcje są bezpiecznymi no-opami.

⚠️ Ograniczenie: natywne okna dialogowe systemu (``tkinter.filedialog`` —
Otwórz/Zapisz/Wybierz folder) są rysowane przez powłokę Windows i **pozostaną
jasne** niezależnie od motywu aplikacji. W czystym tkinter nie da się tego
prosto obejść.
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from contextlib import suppress
from typing import Any

# Okna z paskiem tytułu (mają withdraw/deiconify) — Tk i Toplevel.
Window = tk.Tk | tk.Toplevel

# Atrybuty DWM: 20 = nowsze Win10/Win11, 19 = starsze buildy Win10.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19


def set_titlebar_dark(window: Window, dark: bool) -> bool:
    """Ustawia ciemny (``dark=True``) lub jasny pasek tytułu okna.

    Args:
        window: okno (``Tk`` lub ``Toplevel``).
        dark: czy pasek ma być ciemny.

    Returns:
        ``True`` gdy atrybut udało się ustawić (tylko Windows), inaczej ``False``.
    """
    # Wzorzec z przypisaniem (nie early-return), by mypy nie uznał gałęzi za
    # nieosiągalną pod żadną platformą (--platform win32/linux/darwin).
    result = False
    if sys.platform == "win32":
        result = _set_titlebar_dark_win(window, dark)
    return result


def refresh_titlebar(window: Window) -> None:
    """Wymusza przemalowanie paska tytułu (potrzebne na Win10).

    Krótkie ``withdraw``/``deiconify`` — Win11 zwykle nie wymaga, Win10 tak.
    Wołać TYLKO po faktycznej zmianie motywu. Poza Windows: no-op.
    """
    if sys.platform == "win32":
        _refresh_window_win(window)


def _set_titlebar_dark_win(window: Window, dark: bool) -> bool:
    """Windowsowa implementacja ustawienia ciemnego paska tytułu."""
    try:
        window.update_idletasks()
        # winfo_id() zwraca uchwyt dziecka — prawdziwy HWND to jego rodzic.
        # getattr: ``ctypes.windll`` istnieje tylko na Windows (czysty mypy cross-platform).
        windll: Any = getattr(ctypes, "windll")  # noqa: B009
        hwnd = windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        dwm = windll.dwmapi
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hr = dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
        if hr != 0:  # starszy build Win10 — spróbuj atrybutu 19
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
            )
        return True
    except Exception:
        # Różne błędy ctypes/DWM (brak API, zły HWND) — traktujemy jednolicie jako brak wsparcia.
        return False


def _refresh_window_win(window: Window) -> None:
    """Mrugnięcie oknem wymuszające przemalowanie paska tytułu na Windows."""
    with suppress(tk.TclError):
        window.withdraw()
        window.deiconify()
