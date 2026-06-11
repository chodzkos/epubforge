"""Wątki robocze GUI (``QThread``) i pomocnik do streamowania subprocessu.

ŻELAZNA ZASADA (GUI_STANDARD §4): kod w :meth:`Worker.run` **nigdy** nie dotyka
widgetów — komunikuje się z GUI wyłącznie przez sygnały (połączenie kolejkowane).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Poziom linii logu: "ok" (zielony), "warn" (bursztyn), "err" (czerwony),
# "cmd" (wyciszona komenda), "info" (drugorzędny — domyślny).
LogLevel = str
EmitLine = Callable[[str, LogLevel], None]
EmitProgress = Callable[[int, int], None]


class Worker(QThread):
    """Uruchamia callable w osobnym wątku i raportuje wynik sygnałami.

    Callable dostaje dwa pierwsze argumenty: ``emit_line(text, level)`` do
    strumieniowania logu oraz ``emit_progress(current, total)`` do raportowania
    postępu; dalej idą argumenty przekazane do konstruktora.

    Sygnały:
        line: pojedyncza linia logu ``(text, level)``.
        progress: postęp batcha ``(current, total)``.
        done: praca zakończona sukcesem; niesie zwrócony obiekt.
        failed: praca rzuciła wyjątek; niesie komunikat błędu.

    Uwaga: ``QThread`` ma własny sygnał ``finished`` (bez argumentów), dlatego
    sygnał wyniku nazywa się :attr:`done`.
    """

    line = Signal(str, str)
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

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

    def run(self) -> None:
        try:
            result = self._fn(self._emit_line, self._emit_progress, *self._args, **self._kwargs)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.done.emit(result)

    def _emit_line(self, text: str, level: LogLevel = "info") -> None:
        """Emituje linię logu do GUI (połączenie kolejkowane między wątkami)."""
        self.line.emit(text, level)

    def _emit_progress(self, current: int, total: int) -> None:
        """Emituje postęp batcha do GUI (połączenie kolejkowane między wątkami)."""
        self.progress.emit(current, total)


def level_for_line(line: str) -> LogLevel:
    """Dobiera poziom kolorystyczny do treści linii logu."""
    lower = line.lower()
    if "error" in lower or "błąd" in lower or "failed" in lower:
        return "err"
    if "warn" in lower or "warning" in lower:
        return "warn"
    if "ok" in lower or "success" in lower:
        return "ok"
    return "info"


def run_subprocess_streaming(
    cmd: list[str],
    on_line: EmitLine,
    cwd: str | None = None,
) -> int:
    """Uruchamia subprocess i streamuje połączone stdout/stderr przez ``on_line``.

    Args:
        cmd: komenda do uruchomienia.
        on_line: callback ``(text, level)`` — zwykle ``Worker._emit_line``.
        cwd: katalog roboczy procesu.

    Returns:
        Kod wyjścia procesu.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.stdout is not None:
        for line in proc.stdout:
            stripped = line.rstrip("\n")
            on_line(stripped, level_for_line(stripped))
    return proc.wait()
