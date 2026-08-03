"""Kompatybilna nakładka strumieniowa — cienki adapter na :mod:`core.process`.

Historycznie tu mieszkał silnik strumieniowania subprocessu. Od F-13 wspólny
runner procesów (timeouty, limit logu, ograniczona kolejka, ubijanie CAŁEGO
drzewa procesu) żyje w :mod:`epubforge.core.process`. Ten moduł zostaje jako
**stabilne API zgodności**: konwertery, walidatory i ``gui/workers`` importują
stąd te same symbole co dawniej, bez zmian w miejscach wywołań.

Warstwa czysta (bez Qt) — nie łamie zasady zależności (``core`` nie importuje z
``gui``). Anulowanie pozostaje **kooperacyjne**: ``should_cancel`` jest próbkowane
między próbkami, a runner przy przerwaniu ubija całe drzewo procesu potomnego.
"""

from __future__ import annotations

from dataclasses import replace

from epubforge.core.process import (
    CREATE_NO_WINDOW,
    DEFAULT_PROCESS_LIMITS,
    CancelCheck,
    LineSink,
    LogLevel,
    ProcessResult,
    level_for_line,
    parse_calibre_percent,
    run_process_streaming,
)

__all__ = [
    "CREATE_NO_WINDOW",
    "CancelCheck",
    "LineSink",
    "LogLevel",
    "ProcessResult",
    "level_for_line",
    "parse_calibre_percent",
    "run_subprocess_streaming",
]


class _Default:
    """Wartownik: „nie podano timeoutu" → użyj domyślnego z :class:`ProcessLimits`."""


_USE_DEFAULT_TIMEOUT = _Default()


def run_subprocess_streaming(
    cmd: list[str],
    on_line: LineSink,
    cwd: str | None = None,
    should_cancel: CancelCheck | None = None,
    *,
    timeout: float | _Default | None = _USE_DEFAULT_TIMEOUT,
) -> ProcessResult:
    """Uruchamia subprocess strumieniowo (adapter na :func:`run_process_streaming`).

    Args:
        cmd: komenda do uruchomienia.
        on_line: callback ``(text, level)`` wołany dla każdej linii logu.
        cwd: katalog roboczy procesu.
        should_cancel: predykat anulowania (``True`` = ubij całe drzewo procesu).
        timeout: twardy limit czasu w sekundach. Pominięty → domyślny limit
            runnera; ``None`` → bez limitu; liczba → ten limit.

    Returns:
        :class:`ProcessResult` z kodem wyjścia i flagami ``cancelled``/``timed_out``.
    """
    if isinstance(timeout, _Default):
        limits = DEFAULT_PROCESS_LIMITS
    else:
        limits = replace(DEFAULT_PROCESS_LIMITS, timeout=timeout)
    return run_process_streaming(cmd, on_line, cwd=cwd, should_cancel=should_cancel, limits=limits)
