"""Wątki robocze GUI (``QThread``) i pomocnik do streamowania subprocessu.

ŻELAZNA ZASADA (GUI_STANDARD §4): kod w :meth:`Worker.run` **nigdy** nie dotyka
widgetów — komunikuje się z GUI wyłącznie przez sygnały (połączenie kolejkowane).

Prymityw strumieniowania (:func:`run_subprocess_streaming`, :class:`ProcessResult`,
:func:`level_for_line`) mieszka w :mod:`epubforge.core.streaming` (warstwa czysta,
bez Qt) i jest tu re-eksportowany dla zgodności — konwertery używają go wprost,
nie importując z ``gui``.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

from epubforge.core.streaming import (
    CREATE_NO_WINDOW,
    LogLevel,
    ProcessResult,
    level_for_line,
    run_subprocess_streaming,
)

__all__ = [
    "CREATE_NO_WINDOW",
    "EmitLine",
    "EmitProgress",
    "LogLevel",
    "ProcessResult",
    "ShouldCancel",
    "Worker",
    "level_for_line",
    "run_subprocess_streaming",
]

EmitLine = Callable[[str, LogLevel], None]
EmitProgress = Callable[[int, int], None]
ShouldCancel = Callable[[], bool]


class Worker(QThread):
    """Uruchamia callable w osobnym wątku i raportuje wynik sygnałami.

    Callable dostaje dwa pierwsze argumenty: ``emit_line(text, level)`` do
    strumieniowania logu oraz ``emit_progress(current, total)`` do raportowania
    postępu; dalej idą argumenty przekazane do konstruktora.

    **Anulowanie (opt-in).** Callable, które chce wspierać anulowanie, deklaruje
    jako TRZECI parametr pozycyjny ``should_cancel: Callable[[], bool]`` (zaraz po
    ``emit_line`` i ``emit_progress``). :class:`Worker` wykrywa go przez
    introspekcję sygnatury (nazwa ``should_cancel`` w parametrach) i tylko wtedy
    dokłada ten hook — stare callable przyjmujące dwa hooki działają bez zmian.
    Wybrano introspekcję zamiast osobnej flagi konstruktora, bo zachowuje jedną
    ścieżkę wywołania i nie wymusza zmiany żadnego istniejącego workera.

    Anulowanie jest **kooperacyjne**: :meth:`cancel` ustawia zdarzenie, a callable
    sam kończy pracę, gdy ``should_cancel()`` zwróci ``True`` (zwykle przez
    :func:`run_subprocess_streaming`, który ubija proces potomny). NIGDY nie
    wołamy ``QThread.terminate()``.

    Sygnały:
        line: pojedyncza linia logu ``(text, level)``.
        progress: postęp ``(current, total)``.
        done: praca zakończona sukcesem; niesie zwrócony obiekt.
        failed: praca rzuciła wyjątek (i NIE była anulowana); niesie komunikat.
        cancelled: praca przerwana na żądanie użytkownika (bez argumentów).

    Uwaga: ``QThread`` ma własny sygnał ``finished`` (bez argumentów), dlatego
    sygnał wyniku nazywa się :attr:`done`.
    """

    line = Signal(str, str)
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancel_event = threading.Event()
        self._accepts_cancel = _accepts_should_cancel(fn)

    def cancel(self) -> None:
        """Zgłasza żądanie przerwania (kooperacyjne — nie ubija wątku)."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Czy zażądano anulowania tej pracy."""
        return self._cancel_event.is_set()

    def run(self) -> None:
        hooks: list[Any] = [self._emit_line, self._emit_progress]
        if self._accepts_cancel:
            hooks.append(self._should_cancel)
        try:
            result = self._fn(*hooks, *self._args, **self._kwargs)
        except Exception as exc:
            # Anulowanie objawia się często wyjątkiem (ubity proces, brak wyniku).
            # Gdy zażądano anulowania, raportujemy je jako cancelled, nie failed.
            if self.is_cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
            return
        if self.is_cancelled:
            self.cancelled.emit()
        else:
            self.done.emit(result)

    def _emit_line(self, text: str, level: LogLevel = "info") -> None:
        """Emituje linię logu do GUI (połączenie kolejkowane między wątkami)."""
        self.line.emit(text, level)

    def _emit_progress(self, current: int, total: int) -> None:
        """Emituje postęp do GUI (połączenie kolejkowane między wątkami)."""
        self.progress.emit(current, total)

    def _should_cancel(self) -> bool:
        """Hook przekazywany callable'owi: czy użytkownik zażądał anulowania."""
        return self._cancel_event.is_set()


def _accepts_should_cancel(fn: Callable[..., Any]) -> bool:
    """Czy callable deklaruje parametr ``should_cancel`` (opt-in na anulowanie)."""
    try:
        return "should_cancel" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
