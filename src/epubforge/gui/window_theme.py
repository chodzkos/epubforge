"""Ciemny/jasny pasek tytułu okna na Windows (DWM) — wersja Qt.

Na Windows pasek tytułu rysuje system (DWM), nie Qt — kolorujemy go przez
``DwmSetWindowAttribute``. Poza Windows funkcje są bezpiecznymi no-opami.

⚠️ Pułapka (GUI_STANDARD v2.0 §4): od Qt 6.5+ pasek tytułu SAM podąża za motywem
SYSTEMU. Ręczny DWM jest potrzebny TYLKO gdy motyw aplikacji ≠ motyw systemu
(użytkownik wymusił inny niż systemowy) — do tego służy :func:`sync_titlebar`.
Przy zgodzie motywów nie ruszamy paska. ``winId()`` jest wiarygodny dopiero po
utworzeniu natywnego okna — wołaj z ``showEvent``, nie z ``__init__``; uchwyt
przekazujemy do ctypes jako ``int(window.winId())``.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from epubforge.gui.theme import ThemeName

logger = logging.getLogger(__name__)

# Atrybuty DWM: 20 = nowsze Win10/Win11, 19 = starsze buildy Win10.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19

# WinAPI do wymuszenia przemalowania ramki okna (pasek tytułu).
_WM_NCACTIVATE = 0x0086
# SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
_SWP_FRAME_REDRAW = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020


def sync_titlebar(window: QWidget, effective_mode: ThemeName, system: ThemeName) -> None:
    """Synchronizuje pasek tytułu z efektywnym motywem aplikacji (§4).

    Qt 6.5+ na Windows samo prowadzi pasek za motywem **systemu**. Ręczny DWM
    wymuszamy WYŁĄCZNIE przy rozjeździe (``effective_mode != system``) — np. gdy
    użytkownik wybrał ciemny, a system jest jasny. Przy zgodzie nie robimy nic.

    Args:
        window: okno najwyższego poziomu (``QMainWindow``, ``QDialog``...).
        effective_mode: faktycznie zastosowany motyw aplikacji (``dark``/``light``).
        system: motyw systemu (``dark``/``light``).
    """
    if effective_mode == system:
        return
    set_titlebar_dark(window, effective_mode == "dark")


def set_titlebar_dark(window: QWidget, dark: bool) -> bool:
    """Ustawia ciemny (``dark=True``) lub jasny pasek tytułu okna.

    Niskopoziomowy helper DWM — w aplikacji wołaj raczej :func:`sync_titlebar`,
    która wymusza DWM tylko przy rozjeździe motywów.

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
