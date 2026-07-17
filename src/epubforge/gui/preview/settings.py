"""Ustawienia podglądu edytora — cienki adapter nad istniejącym ``ConfigStore``.

Kryteria Prompt 1 / GUI_STANDARD (gui-kit):

* NIE tworzymy drugiego pliku konfiguracji ani drugiego timera zapisu — zapis
  idzie przez przypisanie klucza najwyższego poziomu w istniejącym ``ConfigStore``
  (``store[key] = value``), co uruchamia ``on_dirty`` i debounce GUI;
* NIE mutujemy zagnieżdżonych słowników w miejscu — słowniki (``user_style``,
  ``last_viewport``) przypisujemy jako całość, żeby ``ConfigStore`` oznaczył zmianę;
* moduł jest czystym Pythonem (bez Qt) — działa też w testach na zwykłym ``dict``.

Klucze zgodne z preferowaną konwencją dokumentu (``editor_preview_*``).
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

# Klucze najwyższego poziomu w config.json (patrz dokument, sekcja gui-kit).
BACKEND_KEY = "editor_preview_backend"
SPLIT_VIEW_KEY = "editor_preview_split_view"
PROFILE_KEY = "editor_preview_profile"

#: Dozwolone wartości backendu podglądu.
VALID_BACKENDS: tuple[str, ...] = ("auto", "webengine", "text")

_DEFAULT_BACKEND = "auto"
_DEFAULT_PROFILE = "default"


class PreviewSettings:
    """Typowany dostęp do ustawień podglądu w istniejącym ``ConfigStore``.

    Args:
        store: obiekt słownikopodobny — w aplikacji ``ConfigStore`` (podtyp
            ``dict`` z ``on_dirty``), w testach zwykły ``dict``. ``None`` →
            ulotny ``dict`` (brak trwałości), by widgety działały bez configu.
    """

    def __init__(self, store: MutableMapping[str, Any] | None = None) -> None:
        self._store: MutableMapping[str, Any] = store if store is not None else {}

    # ── Backend ────────────────────────────────────────────────────────────────

    @property
    def backend(self) -> str:
        """Preferowany backend: ``"auto" | "webengine" | "text"`` (domyślnie auto)."""
        value = self._store.get(BACKEND_KEY, _DEFAULT_BACKEND)
        return value if value in VALID_BACKENDS else _DEFAULT_BACKEND

    @backend.setter
    def backend(self, value: str) -> None:
        # Klamrowanie do dozwolonych wartości — nieznaną traktujemy jak auto,
        # zamiast zapisywać śmieć do configu.
        self._store[BACKEND_KEY] = value if value in VALID_BACKENDS else _DEFAULT_BACKEND

    # ── Widok dzielony ───────────────────────────────────────────────────────--

    @property
    def split_view(self) -> bool:
        """Czy tryb dzielony Kod | Podgląd jest włączony (domyślnie nie)."""
        return bool(self._store.get(SPLIT_VIEW_KEY, False))

    @split_view.setter
    def split_view(self, value: bool) -> None:
        self._store[SPLIT_VIEW_KEY] = bool(value)

    # ── Profil podglądu ──────────────────────────────────────────────────────--

    @property
    def profile(self) -> str:
        """Ostatni profil podglądu (Prompt 6 nada mu znaczenie; domyślnie ``default``)."""
        return str(self._store.get(PROFILE_KEY, _DEFAULT_PROFILE))

    @profile.setter
    def profile(self, value: str) -> None:
        self._store[PROFILE_KEY] = str(value)
