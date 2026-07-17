"""Wykrywanie dostępności Qt WebEngine — wyłącznie lokalnie w warstwie GUI.

WAŻNE (kryterium Prompt 1): dostępności modułu Pythona NIE sprawdzamy przez
``chodzkos-detection`` (to sondy binariów CLI i usług HTTP). Sprawdzamy ją tu,
przez :func:`importlib.util.find_spec` i kontrolowany import.

:func:`probe_webengine` jest tania i bez efektów ubocznych — używa wyłącznie
``find_spec`` (nie importuje samego WebEngine). Właściwy, kontrolowany import
(który potrafi zainicjalizować Chromium) wykonuje :func:`import_webengine_widgets`
dopiero przy tworzeniu backendu, opakowany w obsługę błędów.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass
from types import ModuleType

logger = logging.getLogger(__name__)

# Moduł toru Widgets Qt WebEngine (nie Quick/Qml) — decyduje o dokładnym podglądzie.
_WEBENGINE_WIDGETS = "PySide6.QtWebEngineWidgets"


@dataclass(frozen=True)
class WebEngineProbe:
    """Wynik lekkiej sondy dostępności Qt WebEngine."""

    available: bool
    reason: str


def probe_webengine() -> WebEngineProbe:
    """Sprawdza obecność modułu Qt WebEngine bez jego importowania.

    ``find_spec`` importuje jedynie pakiet nadrzędny ``PySide6`` (lekki), a samego
    ``QtWebEngineWidgets`` nie ładuje — więc sonda nie inicjalizuje Chromium ani
    nie wciąga ciężkiego modułu do procesu, w którym może nie być potrzebny.

    Returns:
        :class:`WebEngineProbe` z flagą i czytelnym powodem (do diagnostyki UI).
    """
    try:
        spec = importlib.util.find_spec(_WEBENGINE_WIDGETS)
    except (ImportError, ValueError) as exc:
        # ModuleNotFoundError (brak PySide6) i ValueError (uszkodzony __spec__).
        return WebEngineProbe(available=False, reason=str(exc))
    if spec is None:
        return WebEngineProbe(available=False, reason="Brak modułu QtWebEngineWidgets")
    return WebEngineProbe(available=True, reason="")


def import_webengine_widgets() -> ModuleType | None:
    """Kontrolowany import ``QtWebEngineWidgets`` — zwraca moduł albo ``None``.

    W przeciwieństwie do :func:`probe_webengine` ten import REALNIE ładuje moduł
    (może zainicjalizować część Chromium). Każdy błąd jest łapany i logowany —
    brak lub awaria WebEngine nie może zepsuć GUI ani CLI.
    """
    # Inicjalizacja WebEngine bywa dowolnie awaryjna (brak GPU, biblioteki
    # systemowe, sandbox) — świadomie łapiemy szeroko, bo awaria importu ma
    # skutkować cichym fallbackiem, nie wywróceniem GUI.
    try:
        return importlib.import_module(_WEBENGINE_WIDGETS)
    except Exception as exc:
        logger.warning("Nie udało się zaimportować %s: %s", _WEBENGINE_WIDGETS, exc)
        return None
