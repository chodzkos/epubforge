"""Testy cache SQLite i rate limitera (:mod:`epubforge.bookmeta.cache`)."""

from __future__ import annotations

import threading
from pathlib import Path

from epubforge.bookmeta.cache import DEFAULT_TTL_SECONDS, MetadataCache, RateLimiter

# ── MetadataCache ────────────────────────────────────────────────────────────────


def test_cache_set_and_get() -> None:
    """Zapisany wpis jest odczytywalny po kluczu (provider, query)."""
    cache = MetadataCache()
    cache.set("lubimyczytac", "url1", "<html>1</html>")
    assert cache.get("lubimyczytac", "url1") == "<html>1</html>"
    assert cache.get("lubimyczytac", "brak") is None
    assert cache.get("inny", "url1") is None


def test_cache_ttl_expiry() -> None:
    """Wpis starszy niż TTL jest traktowany jak brak (i usuwany)."""
    now = [1000.0]
    cache = MetadataCache(clock=lambda: now[0])
    cache.set("lc", "u", "v")
    now[0] += DEFAULT_TTL_SECONDS + 1
    assert cache.get("lc", "u") is None
    # po odczycie wpis usunięty — nawet cofnięcie czasu nie przywraca
    now[0] = 1000.0
    assert cache.get("lc", "u") is None


def test_cache_persists_to_disk(tmp_path: Path) -> None:
    """Cache przeżywa zamknięcie i ponowne otwarcie tej samej bazy."""
    db = tmp_path / "cache.sqlite"
    first = MetadataCache(db)
    first.set("lc", "u", "trwałe")
    first.close()
    second = MetadataCache(db)
    assert second.get("lc", "u") == "trwałe"


def test_cache_schema_version_rebuild(tmp_path: Path) -> None:
    """Niezgodna wersja schematu → tabela przebudowana (bez wywrotki)."""
    db = tmp_path / "cache.sqlite"
    cache = MetadataCache(db)
    cache.set("lc", "u", "v")
    # symuluj starą wersję schematu
    cache._conn.execute("PRAGMA user_version = 999")
    cache._conn.commit()
    cache.close()
    rebuilt = MetadataCache(db)  # wykryje niezgodność i odtworzy tabelę
    assert rebuilt.get("lc", "u") is None  # stare dane porzucone
    rebuilt.set("lc", "u2", "nowe")
    assert rebuilt.get("lc", "u2") == "nowe"


# ── Thread-safety (regresja: „SQLite objects ... same thread") ──────────────────────


def test_cache_put_get_across_threads() -> None:
    """Regresja: połączenie tworzone w wątku głównym, put w wątku 1, get w wątku 2.

    Odtwarza buga „SQLite objects created in a thread can only be used in that same
    thread" — na starym kodzie (bez ``check_same_thread=False``) rzucał; teraz przechodzi.
    """
    cache = MetadataCache()  # połączenie powstaje w wątku głównym (jak wspólny provider)
    errors: list[BaseException] = []

    def put() -> None:
        try:
            cache.set("lubimyczytac", "u", "wartość")
        except BaseException as exc:
            errors.append(exc)

    result: list[str | None] = []

    def get() -> None:
        try:
            result.append(cache.get("lubimyczytac", "u"))
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=put)
    t1.start()
    t1.join()
    t2 = threading.Thread(target=get)
    t2.start()
    t2.join()

    assert errors == []  # brak wyjątku międzywątkowego
    assert result == ["wartość"]


def test_cache_concurrent_put_get_same_key() -> None:
    """2 wątki po 50 naprzemiennych put/get na tym samym kluczu -> bez wyjątków, baza spójna."""
    cache = MetadataCache()
    errors: list[BaseException] = []

    def worker(tag: str) -> None:
        try:
            for i in range(50):
                cache.set("lubimyczytac", "key", f"{tag}-{i}")
                cache.get("lubimyczytac", "key")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    # Baza spójna: klucz istnieje i zawiera jedną z zapisanych wartości (last-write-wins).
    value = cache.get("lubimyczytac", "key")
    assert value is not None
    assert value.split("-")[0] in {"A", "B"}


# ── RateLimiter ──────────────────────────────────────────────────────────────────


def test_rate_limiter_first_call_does_not_sleep() -> None:
    """Pierwsze żądanie nie czeka (brak poprzedniego)."""
    sleeps: list[float] = []
    limiter = RateLimiter(2.0, clock=lambda: 100.0, sleep=sleeps.append)
    limiter.wait()
    assert sleeps == []


def test_rate_limiter_enforces_interval() -> None:
    """Drugie żądanie tuż po pierwszym czeka o brakujący czas."""
    now = [100.0]
    sleeps: list[float] = []
    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=sleeps.append)
    limiter.wait()  # ustawia _last = 100.0
    now[0] = 100.5  # minęło tylko 0.5 s
    limiter.wait()  # brakuje 1.5 s do progu
    assert sleeps == [1.5]


def test_rate_limiter_no_sleep_when_interval_passed() -> None:
    """Gdy odstęp już minął, kolejne żądanie nie czeka."""
    now = [0.0]
    sleeps: list[float] = []
    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=sleeps.append)
    limiter.wait()
    now[0] = 5.0  # minęło więcej niż próg
    limiter.wait()
    assert sleeps == []
