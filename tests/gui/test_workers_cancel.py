"""Testy anulowania i zgodności wstecznej wątków roboczych GUI (Etap 19)."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.workers import Worker, _accepts_should_cancel, run_subprocess_streaming

pytestmark = pytest.mark.gui

# Proces-atrapa: śpi długo, nie produkuje logu — sprawdza anulowanie „w ciszy".
_SLEEP_CMD = [sys.executable, "-c", "import time; time.sleep(60)"]


def _sleeper(emit_line: object, emit_progress: object, should_cancel: object) -> object:
    """Worker uruchamiający długi proces przez strumieniowy runner (z anulowaniem)."""
    return run_subprocess_streaming(
        _SLEEP_CMD,
        lambda text, level: None,
        should_cancel=should_cancel,  # type: ignore[arg-type]
    )


def test_cancel_kills_process_and_emits_cancelled(qtbot: QtBot) -> None:
    """cancel() ubija proces w < 5 s, emituje ``cancelled`` i NIE emituje ``failed``."""
    failed: list[str] = []
    worker = Worker(_sleeper)
    worker.failed.connect(failed.append)

    worker.start()
    qtbot.waitUntil(worker.isRunning, timeout=2000)

    # waitSignal z timeout=5000 wymusza, że anulowanie zamyka proces w < 5 s.
    with qtbot.waitSignal(worker.cancelled, timeout=5000):
        worker.cancel()

    assert worker.wait(2000)
    assert failed == []
    assert worker.is_cancelled


def test_old_two_hook_callable_still_works(qtbot: QtBot) -> None:
    """Callable przyjmujące tylko dwa hooki (bez should_cancel) działa jak dawniej."""
    seen: list[tuple[str, str]] = []

    def legacy(emit_line: object, emit_progress: object) -> str:
        emit_line("linia", "info")  # type: ignore[operator]
        return "wynik"

    worker = Worker(legacy)
    worker.line.connect(lambda text, level: seen.append((text, level)))
    with qtbot.waitSignal(worker.done, timeout=2000) as blocker:
        worker.start()

    assert worker.wait(2000)
    assert blocker.args == ["wynik"]
    assert seen == [("linia", "info")]


def test_worker_maps_exception_to_cancelled_when_cancel_requested(qtbot: QtBot) -> None:
    """Gdy zażądano anulowania, wyjątek z callable staje się ``cancelled``, nie ``failed``."""
    failed: list[str] = []

    def boom(emit_line: object, emit_progress: object, should_cancel: object) -> None:
        raise RuntimeError("ubity proces")

    worker = Worker(boom)
    worker.cancel()  # anulowanie ZANIM wystartuje — run() zobaczy is_cancelled
    worker.failed.connect(failed.append)
    with qtbot.waitSignal(worker.cancelled, timeout=2000):
        worker.start()

    assert worker.wait(2000)
    assert failed == []


def test_accepts_should_cancel_introspection() -> None:
    """Introspekcja wykrywa trzeci hook po nazwie parametru ``should_cancel``."""

    def with_cancel(emit_line: object, emit_progress: object, should_cancel: object) -> None:
        return None

    def without_cancel(emit_line: object, emit_progress: object) -> None:
        return None

    assert _accepts_should_cancel(with_cancel) is True
    assert _accepts_should_cancel(without_cancel) is False
