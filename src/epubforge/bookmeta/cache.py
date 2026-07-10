"""Cache SQLite i rate limiter dla providerów sieciowych (grzecznościowy scraping).

Scraping stron (LubimyCzytac) wymaga uprzejmości wobec serwisu: **jedno zapytanie
na raz**, minimalny odstęp między żądaniami i **cache** (żeby nie pobierać tej
samej strony wielokrotnie). Ten moduł dostarcza obie rzeczy — bez nowych
zależności (``sqlite3`` ze stdlib):

* :class:`MetadataCache` — trwały cache odpowiedzi (klucz ``provider`` + ``query``)
  z TTL i **wersjonowanym schematem** (zmiana schematu = przebudowa tabeli, bez
  ręcznej migracji; lekcja z poprzednich projektów);
* :class:`RateLimiter` — wymusza minimalny odstęp między żądaniami; zegar i uśpienie
  są wstrzykiwalne, więc testy nie muszą realnie czekać.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Wersja schematu cache. Podbicie = przebudowa tabeli przy następnym otwarciu
# (stare, potencjalnie niezgodne wpisy są porzucane — cache jest odtwarzalny).
_SCHEMA_VERSION = 1
# Domyślny czas życia wpisu (30 dni) — metadane książek zmieniają się rzadko.
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60


class MetadataCache:
    """Trwały cache odpowiedzi providerów w bazie SQLite.

    Klucz wpisu to para (``provider``, ``query``) — np. ``("lubimyczytac", url)``.
    Wpisy starsze niż TTL są traktowane jak brak (i usuwane przy odczycie).
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Inicjalizuje cache i zapewnia zgodny schemat.

        Args:
            path: ścieżka pliku bazy; ``None`` = baza w pamięci (``:memory:``),
                przydatna w testach.
            clock: źródło czasu (epoch, sekundy) — wstrzykiwalne dla testów TTL.
        """
        self._clock = clock
        self._conn = sqlite3.connect(":memory:" if path is None else str(path))
        # Licznik trafień w cache (do statystyki „z cache" w hurtowym wzbogacaniu).
        self.hits = 0
        self._ensure_schema()

    def get(
        self, provider: str, query: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> str | None:
        """Zwraca zbuforowaną wartość albo ``None`` (brak lub przeterminowana).

        Przeterminowany wpis jest przy okazji usuwany.
        """
        row = self._conn.execute(
            "SELECT value, created_at FROM cache WHERE provider = ? AND query = ?",
            (provider, query),
        ).fetchone()
        if row is None:
            return None
        value, created_at = row
        if self._clock() - float(created_at) > ttl_seconds:
            self._conn.execute(
                "DELETE FROM cache WHERE provider = ? AND query = ?", (provider, query)
            )
            self._conn.commit()
            return None
        self.hits += 1
        return str(value)

    def set(self, provider: str, query: str, value: str) -> None:
        """Zapisuje (lub nadpisuje) wartość w cache ze znacznikiem czasu."""
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (provider, query, value, created_at) VALUES (?, ?, ?, ?)",
            (provider, query, value, self._clock()),
        )
        self._conn.commit()

    def close(self) -> None:
        """Zamyka połączenie z bazą."""
        self._conn.close()

    def _ensure_schema(self) -> None:
        """Tworzy tabelę cache; przy niezgodnej wersji schematu przebudowuje ją."""
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version != _SCHEMA_VERSION:
            if version != 0:
                logger.debug(
                    "Niezgodna wersja schematu cache (%s != %s) — przebudowa",
                    version,
                    _SCHEMA_VERSION,
                )
            self._conn.execute("DROP TABLE IF EXISTS cache")
            self._conn.execute(
                "CREATE TABLE cache ("
                "provider TEXT NOT NULL, query TEXT NOT NULL, value TEXT NOT NULL, "
                "created_at REAL NOT NULL, PRIMARY KEY (provider, query))"
            )
            self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._conn.commit()


class RateLimiter:
    """Wymusza minimalny odstęp między kolejnymi żądaniami (bez równoległości).

    Zegar (``clock``) i uśpienie (``sleep``) są wstrzykiwalne, więc w testach można
    zasymulować upływ czasu bez realnego czekania.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Args:
        min_interval: minimalny odstęp między żądaniami w sekundach.
        clock: monotoniczne źródło czasu (sekundy).
        sleep: funkcja usypiająca na zadaną liczbę sekund.
        """
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        """Blokuje, aż od poprzedniego żądania minie co najmniej ``min_interval``."""
        if self._last is not None:
            remaining = self._min_interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()
