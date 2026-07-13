"""Testy wątku roboczego GUI (:class:`epubforge.gui.workers.Worker`).

Wywołujemy ``run()`` bezpośrednio (synchronicznie w wątku testu), więc sygnały
lecą natychmiast — bez realnego ``QThread.start()``. Pokrywa: sukces, błąd,
anulowanie (przy błędzie i przy sukcesie) oraz opt-in na ``should_cancel``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.workers import Worker, _accepts_should_cancel

pytestmark = pytest.mark.gui


def test_worker_done_emits_result_and_hooks(qtbot: QtBot) -> None:
    """Sukces → sygnał ``done`` z wynikiem; hooki line/progress działają."""

    def fn(emit_line: Any, emit_progress: Any, value: int) -> int:
        emit_line("hej", "info")
        emit_progress(1, 2)
        return value

    worker = Worker(fn, 42)
    results: list[object] = []
    lines: list[tuple[str, str]] = []
    progress: list[tuple[int, int]] = []
    worker.done.connect(results.append)
    worker.line.connect(lambda text, level: lines.append((text, level)))
    worker.progress.connect(lambda a, b: progress.append((a, b)))
    worker.run()
    assert results == [42]
    assert lines == [("hej", "info")]
    assert progress == [(1, 2)]


def test_worker_failed_emits_message(qtbot: QtBot) -> None:
    """Wyjątek bez anulowania → sygnał ``failed`` z komunikatem."""

    def fn(_emit_line: Any, _emit_progress: Any) -> None:
        raise RuntimeError("boom")

    worker = Worker(fn)
    failed: list[str] = []
    worker.failed.connect(failed.append)
    worker.run()
    assert failed == ["boom"]


def test_worker_exception_after_cancel_is_cancelled(qtbot: QtBot) -> None:
    """Wyjątek PO anulowaniu → sygnał ``cancelled`` (nie ``failed``)."""

    def fn(_emit_line: Any, _emit_progress: Any) -> None:
        raise RuntimeError("ubity proces")

    worker = Worker(fn)
    worker.cancel()
    cancelled: list[bool] = []
    failed: list[str] = []
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.failed.connect(failed.append)
    worker.run()
    assert cancelled == [True]
    assert failed == []


def test_worker_success_after_cancel_is_cancelled(qtbot: QtBot) -> None:
    """Sukces PO anulowaniu → sygnał ``cancelled`` (wynik odrzucony)."""

    def fn(_emit_line: Any, _emit_progress: Any) -> str:
        return "ok"

    worker = Worker(fn)
    worker.cancel()
    cancelled: list[bool] = []
    done: list[object] = []
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.done.connect(done.append)
    worker.run()
    assert cancelled == [True]
    assert done == []


def test_worker_passes_should_cancel_when_declared(qtbot: QtBot) -> None:
    """Callable z parametrem ``should_cancel`` dostaje działający hook anulowania."""
    seen: dict[str, bool] = {}

    def fn(_emit_line: Any, _emit_progress: Any, should_cancel: Any) -> None:
        seen["value"] = should_cancel()

    worker = Worker(fn)
    assert worker.is_cancelled is False
    worker.cancel()
    assert worker.is_cancelled is True
    worker.run()
    assert seen["value"] is True


def test_accepts_should_cancel_detection() -> None:
    """Introspekcja wykrywa opt-in na anulowanie i toleruje nie-callable."""
    assert _accepts_should_cancel(lambda el, ep, should_cancel: None) is True
    assert _accepts_should_cancel(lambda el, ep: None) is False
    assert _accepts_should_cancel(42) is False  # nie-callable → False, bez wyjątku
