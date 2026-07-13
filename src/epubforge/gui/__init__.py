"""GUI aplikacji EpubForge (PySide6).

Publiczne API (``MainWindow``, ``main``) ładujemy **leniwie** przez ``__getattr__``
(PEP 562) — sam ``import epubforge.gui`` nie ciągnie za sobą ``epubforge.gui.app``
ani PySide6. Dzięki temu narzędzia, które trafią na ten pakiet pośrednio (np.
introspekcja), nie wymagają extra ``gui``; PySide6 ładuje się dopiero przy
pierwszym odwołaniu do ``MainWindow``/``main`` albo jawnym ``import
epubforge.gui.app``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from epubforge.gui.app import MainWindow, main

__all__ = ["MainWindow", "main"]


def __getattr__(name: str) -> Any:
    """Leniwy dostęp do publicznego API GUI (ładuje PySide6 dopiero na żądanie)."""
    if name in __all__:
        from epubforge.gui import app

        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Uzupełnia ``dir(epubforge.gui)`` o leniwie eksportowane symbole."""
    return sorted({*globals(), *__all__})
