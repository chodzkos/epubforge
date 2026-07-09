"""Strumieniowe uruchamianie subprocessu — anulowanie kooperacyjne i postęp.

Warstwa czysta (bez Qt): używana zarówno przez konwertery (``converters/``) jak
i przez wątki robocze GUI (``gui/workers.py`` re-eksportuje te symbole). Dzięki
temu logika strumieniowania nie łamie zasady zależności (``core`` nie importuje
z ``gui``).

Anulowanie jest **wyłącznie kooperacyjne**: pętla czytania sprawdza między
próbkami ``should_cancel()`` i — przy żądaniu przerwania — grzecznie kończy
proces potomny (``terminate`` → 3 s karencji → ``kill``). Nie ma tu żadnego
zabijania wątków; wątek czytający kończy się sam po zamknięciu strumienia.
"""

from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

# Flaga ukrywająca okno konsoli na Windows (pułapka #7).
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Karencja między ``terminate`` a twardym ``kill`` procesu potomnego.
_TERMINATE_GRACE_S = 3.0
# Odstęp próbkowania kolejki linii — jednocześnie granulacja sprawdzania anulowania.
_POLL_INTERVAL_S = 0.1

# Poziom linii logu: "ok" (zielony), "warn" (bursztyn), "err" (czerwony),
# "cmd" (wyciszona komenda), "info" (drugorzędny — domyślny).
LogLevel = str
LineSink = Callable[[str, LogLevel], None]
CancelCheck = Callable[[], bool]

# Postęp Calibre pojawia się w logu jako „NN%" (np. „ 34% Converting…").
_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")


@dataclass(frozen=True)
class ProcessResult:
    """Wynik strumieniowego uruchomienia procesu.

    Attributes:
        returncode: kod wyjścia procesu (``-1`` gdy przerwany przed ``wait``).
        cancelled: ``True`` gdy przerwano na żądanie ``should_cancel``.
        timed_out: ``True`` gdy proces przekroczył ``timeout`` i został ubity.
    """

    returncode: int
    cancelled: bool = False
    timed_out: bool = False


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


def parse_calibre_percent(line: str) -> int | None:
    """Wyłuskuje procent postępu z linii logu Calibre (``0..100``) lub ``None``."""
    match = _PERCENT_RE.search(line)
    if match is None:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 100 else None


def run_subprocess_streaming(
    cmd: list[str],
    on_line: LineSink,
    cwd: str | None = None,
    should_cancel: CancelCheck | None = None,
    *,
    timeout: float | None = None,
) -> ProcessResult:
    """Uruchamia subprocess i streamuje połączone stdout/stderr przez ``on_line``.

    Odczyt biegnie w wątku pomocniczym, a pętla główna próbkuje kolejkę linii co
    :data:`_POLL_INTERVAL_S`. Dzięki temu ``should_cancel`` jest sprawdzane także
    gdy proces milczy (np. długa konwersja bez logów) — nie tylko „między liniami".

    Args:
        cmd: komenda do uruchomienia.
        on_line: callback ``(text, level)`` — zwykle ``Worker._emit_line``.
        cwd: katalog roboczy procesu.
        should_cancel: predykat sprawdzany cyklicznie; ``True`` = przerwij proces.
        timeout: twardy limit czasu w sekundach (``None`` = bez limitu).

    Returns:
        :class:`ProcessResult` z kodem wyjścia oraz flagami ``cancelled``/``timed_out``.
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

    lines: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(target=_pump_lines, args=(proc, lines), daemon=True)
    reader.start()

    deadline = None if timeout is None else time.monotonic() + timeout
    cancelled = False
    timed_out = False
    try:
        while True:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            try:
                item = lines.get(timeout=_POLL_INTERVAL_S)
            except queue.Empty:
                continue
            if item is None:  # sentinel EOF — proces zamknął strumień
                break
            on_line(item, level_for_line(item))
    finally:
        if cancelled or timed_out:
            _terminate_process(proc)
        returncode = proc.wait()
        reader.join(timeout=1.0)

    return ProcessResult(returncode=returncode, cancelled=cancelled, timed_out=timed_out)


def _pump_lines(proc: subprocess.Popen[str], sink: queue.Queue[str | None]) -> None:
    """Czyta stdout procesu linia po linii do kolejki; na końcu wrzuca sentinel."""
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                sink.put(line.rstrip("\n"))
    finally:
        sink.put(None)


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    """Kończy proces kooperacyjnie: ``terminate`` → karencja → twardy ``kill``.

    NIGDY nie zabija wątków — jedynie proces potomny. Wątek czytający kończy się
    sam, gdy proces zamknie stdout.
    """
    proc.terminate()
    try:
        proc.wait(timeout=_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
