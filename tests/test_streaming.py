"""Testy prymitywu strumieniowania subprocessu (``core.streaming``)."""

from __future__ import annotations

import sys

from epubforge.converters._streaming import run_command_streaming
from epubforge.core.streaming import (
    ProcessResult,
    level_for_line,
    parse_calibre_percent,
    run_subprocess_streaming,
)


def test_parse_calibre_percent() -> None:
    """Wyłuskuje procent 0..100, resztę zwraca jako None."""
    assert parse_calibre_percent(" 34% Converting…") == 34
    assert parse_calibre_percent("100% done") == 100
    assert parse_calibre_percent("0%") == 0
    assert parse_calibre_percent("brak procentu") is None
    assert parse_calibre_percent("999%") is None


def test_level_for_line() -> None:
    """Dobiera poziom logu po słowach kluczowych."""
    assert level_for_line("ERROR: coś") == "err"
    assert level_for_line("a warning here") == "warn"
    assert level_for_line("all ok") == "ok"
    assert level_for_line("zwykła linia") == "info"


def test_run_subprocess_streaming_happy_path() -> None:
    """Strumienia linie, zwraca kod 0 i flagi domyślnie False."""
    lines: list[tuple[str, str]] = []
    result = run_subprocess_streaming(
        [sys.executable, "-c", "print('pierwsza'); print('druga')"],
        lambda text, level: lines.append((text, level)),
    )
    assert isinstance(result, ProcessResult)
    assert result.returncode == 0
    assert not result.cancelled and not result.timed_out
    assert [text for text, _ in lines] == ["pierwsza", "druga"]


def test_run_subprocess_streaming_nonzero_exit() -> None:
    """Zwraca niezerowy kod bez wyjątku (decyzję o błędzie podejmuje wołający)."""
    result = run_subprocess_streaming(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        lambda text, level: None,
    )
    assert result.returncode == 3


def test_run_subprocess_streaming_timeout() -> None:
    """Przekroczenie timeoutu ubija proces i ustawia timed_out."""
    result = run_subprocess_streaming(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        lambda text, level: None,
        timeout=0.5,
    )
    assert result.timed_out
    assert not result.cancelled


def test_run_command_streaming_parses_progress() -> None:
    """run_command_streaming przekazuje procenty Calibre do on_progress."""
    progress: list[tuple[int, int]] = []
    result = run_command_streaming(
        [sys.executable, "-c", "print('34% Converting'); print('bez procentu')"],
        lambda text, level: None,
        lambda current, total: progress.append((current, total)),
    )
    assert result.returncode == 0
    assert (34, 100) in progress
