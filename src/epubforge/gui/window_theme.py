"""Ciemny/jasny pasek tytułu okna na Windows (DWM) — wersja Qt.

Na Windows pasek tytułu rysuje system (DWM), nie Qt — kolorujemy go przez
``DwmSetWindowAttribute``. Poza Windows funkcje są bezpiecznymi no-opami.

⚠️ Pułapka (GUI_STANDARD §4): ``winId()`` jest wiarygodny dopiero po utworzeniu
natywnego okna — wołaj :func:`set_titlebar_dark` z ``showEvent`` okna, nie z
``__init__``. Uchwyt przekazujemy do ctypes jako ``int(window.winId())``.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Atrybuty DWM: 20 = nowsze Win10/Win11, 19 = starsze buildy Win10.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19

# WinAPI do wymuszenia przemalowania ramki okna (pasek tytułu).
_WM_NCACTIVATE = 0x0086
# SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
_SWP_FRAME_REDRAW = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020


def set_titlebar_dark(window: QWidget, dark: bool) -> bool:
    """Ustawia ciemny (``dark=True``) lub jasny pasek tytułu okna.

    Args:
        window: okno najwyższego poziomu (``QMainWindow``, ``QDialog``...).
        dark: czy pasek ma być ciemny.

    Returns:
        ``True`` gdy atrybut udało się ustawić (tylko Windows), inaczej ``False``.
    """
    # Przypisanie zamiast early-return, by mypy nie uznał gałęzi za nieosiągalną
    # pod żadną platformą (--platform win32/linux/darwin).
    result = False
    if sys.platform == "win32":
        result = _set_titlebar_dark_win(window, dark)
    return result


def _set_titlebar_dark_win(window: QWidget, dark: bool) -> bool:
    """Windowsowa implementacja ustawienia ciemnego paska tytułu."""
    try:
        # int(winId()) — HWND okna Qt; wymaga utworzonego natywnego okna.
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        # getattr: ``ctypes.windll`` istnieje tylko na Windows (czysty mypy cross-platform).
        windll: Any = getattr(ctypes, "windll")  # noqa: B009
        dwm = windll.dwmapi
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hr = dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
        if hr != 0:  # starszy build Win10 — spróbuj atrybutu 19
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
            )
        _force_frame_redraw(windll, hwnd)
        return True
    except Exception as exc:
        # Różne błędy ctypes/DWM (brak API, zły HWND) — jednolicie jako brak wsparcia.
        logger.warning("Nie udało się ustawić ciemnego paska tytułu: %s", exc)
        return False


def _force_frame_redraw(windll: Any, hwnd: int) -> None:
    """Wymusza przemalowanie obszaru nieklienckiego (pasek tytułu).

    Bez mrugania oknem: dezaktywacja/aktywacja paska (``WM_NCACTIVATE``) plus
    ``SetWindowPos`` z ``SWP_FRAMECHANGED``. Naprawia sytuację, gdy na Win10
    pasek tytułu nie odświeża się po zmianie motywu.
    """
    user32 = windll.user32
    user32.SendMessageW(hwnd, _WM_NCACTIVATE, 0, 0)
    user32.SendMessageW(hwnd, _WM_NCACTIVATE, 1, 0)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAME_REDRAW)
