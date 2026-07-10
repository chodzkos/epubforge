"""Bezpieczny klient HTTP dla providerów metadanych (pierwszy kod sieciowy).

Cała warstwa sieciowa projektu przechodzi przez ten moduł, żeby twarde zasady
bezpieczeństwa (lekcja D2 z audytu ``chodzkos-detection``) obowiązywały w jednym
miejscu i nie dało się ich obejść w pojedynczym providerze:

* **wyłącznie ``https``** — schemat URL jest walidowany przed połączeniem;
* **twardy timeout** — żadne zapytanie nie blokuje wątku w nieskończoność;
* **limit rozmiaru odpowiedzi** — ``read(MAX_BYTES)`` chroni przed złośliwym /
  omyłkowo ogromnym payloadem (nadmiar jest ucinany, więc zepsuty JSON → ``None``);
* **żaden błąd nie wychodzi na zewnątrz** — każdy wyjątek sieciowy ląduje w
  ``logger.debug`` i zwracamy ``None`` (warstwa UI nigdy nie widzi wyjątku).

Zależności: wyłącznie stdlib ``urllib`` — projekt nie dokłada ``requests``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Twardy limit rozmiaru odpowiedzi w bajtach (D2). Odpowiedzi metadanych z BN /
# Open Library / Google Books to kilka-kilkadziesiąt kB; 1 MB to bezpieczny sufit.
MAX_BYTES = 1_000_000
# Domyślny timeout pojedynczego zapytania (sekundy).
DEFAULT_TIMEOUT = 5
# Nagłówek identyfikujący klienta (grzecznościowo wobec darmowych API).
_USER_AGENT = "EpubForge (+https://github.com/chodzkos/epubforge)"


def fetch_bytes(
    url: str, *, timeout: float = DEFAULT_TIMEOUT, user_agent: str | None = None
) -> bytes | None:
    """Pobiera treść spod ``https`` URL, zwracając ``None`` przy dowolnym błędzie.

    Args:
        url: pełny adres — musi zaczynać się od ``https://`` (inne schematy są
            odrzucane bez połączenia).
        timeout: maksymalny czas oczekiwania na odpowiedź w sekundach.
        user_agent: opcjonalny nagłówek ``User-Agent`` (np. z wersją projektu dla
            grzecznościowego scrapingu); domyślnie :data:`_USER_AGENT`.

    Returns:
        Do :data:`MAX_BYTES` bajtów treści albo ``None`` (nie-https URL, błąd
        sieci, timeout, błąd HTTP) — funkcja **nigdy nie rzuca wyjątku**.
    """
    if not url.lower().startswith("https://"):
        logger.debug("Odrzucono URL o niedozwolonym schemacie: %s", url)
        return None
    request = urllib.request.Request(url, headers={"User-Agent": user_agent or _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return bytes(response.read(MAX_BYTES))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("Nie udało się pobrać %s: %s", url, exc)
        return None


def fetch_json(
    url: str, *, timeout: float = DEFAULT_TIMEOUT, user_agent: str | None = None
) -> Any | None:
    """Pobiera i parsuje odpowiedź JSON spod ``https`` URL.

    Args:
        url: pełny adres ``https``.
        timeout: maksymalny czas oczekiwania w sekundach.
        user_agent: opcjonalny nagłówek ``User-Agent``.

    Returns:
        Zdekodowany obiekt JSON albo ``None``, gdy pobranie się nie powiodło
        lub treść nie jest poprawnym JSON-em (np. ucięta przez :data:`MAX_BYTES`).
    """
    raw = fetch_bytes(url, timeout=timeout, user_agent=user_agent)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.debug("Niepoprawny JSON z %s: %s", url, exc)
        return None
