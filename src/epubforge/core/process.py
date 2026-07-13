"""Wspólny runner procesów zewnętrznych dla konwerterów i walidatorów (F-13).

Jedno utwardzone miejsce uruchamiania Pandoc/Calibre/EpubCheck/Ace/KP3… Zapewnia:

* **domyślne i konfigurowalne timeouty** (:class:`ProcessLimits`),
* **limit przechowywanego logu** z licznikiem uciętych bajtów (bufor nie puchnie
  przy „gadatliwym" procesie),
* **ograniczoną kolejkę** linii (backpressure — pamięć nie rośnie, gdy konsument
  jest wolniejszy od producenta),
* **obsługę błędów kodowania** (dekodowanie ``errors="replace"``),
* **kończenie CAŁEJ grupy/drzewa procesu** na Windows, Linux i macOS przy
  anulowaniu lub timeoucie (proces potomny nie zostawia „sierot").

Runner ma **jeden silnik** (:func:`_run`); wariant synchroniczny
(:func:`run_process`) i strumieniowy (:func:`run_process_streaming`) mają przez
to **identyczną semantykę** — różnią się tylko tym, że wariant strumieniowy woła
``on_line`` na żywo. Oba zawsze zwracają :class:`ProcessResult` z (przyciętym)
logiem, flagami ``cancelled``/``timed_out`` i licznikiem ``truncated_bytes``.

Uwaga o granicy pakietu: tor DETEKCJI narzędzi (``core/detection.py`` →
chodzkos-detection) ma własną mechanikę sond (``probe_tool``) i NIE korzysta z
tego runnera. Runner trzyma własną stałą :data:`CREATE_NO_WINDOW` (nie importuje
prywatnych symboli pakietu detekcji).
"""

from __future__ import annotations

import contextlib
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

# Flagi Windows: ukrycie okna konsoli (pułapka #7) oraz własna grupa procesu
# (pozwala adresować całe drzewo przy ubijaniu). Poza Windows = 0 (bez efektu).
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if sys.platform == "win32" else 0

# Odstęp próbkowania kolejki — jednocześnie granulacja sprawdzania anulowania.
_POLL_INTERVAL_S = 0.1

# Poziom linii logu: "ok" (zielony), "warn" (bursztyn), "err" (czerwony),
# "cmd" (wyciszona komenda), "info" (drugorzędny — domyślny).
LogLevel = str
LineSink = Callable[[str, LogLevel], None]
CancelCheck = Callable[[], bool]

# Postęp Calibre pojawia się w logu jako „NN%" (np. „ 34% Converting…").
_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")


@dataclass(frozen=True)
class ProcessLimits:
    """Konfigurowalne limity uruchomienia procesu.

    Attributes:
        timeout: twardy limit czasu w sekundach (``None`` = bez limitu). Domyślnie
            godzina — długie konwersje mieszczą się, a proces w zawieszeniu i tak
            zostanie ubity.
        max_log_bytes: górny limit przechowywanego logu (w bajtach UTF-8). Powyżej
            niego linie są liczone jako ucięte (``truncated_bytes``), nie
            gromadzone.
        max_queue_lines: pojemność kolejki linii między wątkiem czytającym a pętlą
            główną — zapełnienie wstrzymuje czytnik (backpressure), więc pamięć
            nie rośnie przy szybkim, gadatliwym procesie.
        terminate_grace_s: karencja między łagodnym a twardym ubiciem drzewa procesu.
    """

    timeout: float | None = 3600.0
    max_log_bytes: int = 8 * 1024 * 1024
    max_queue_lines: int = 8192
    terminate_grace_s: float = 3.0


DEFAULT_PROCESS_LIMITS = ProcessLimits()


@dataclass(frozen=True)
class ProcessResult:
    """Wynik uruchomienia procesu (wspólny dla trybu sync i streaming).

    Attributes:
        returncode: kod wyjścia procesu (``-1`` gdy nie doszło do ``wait``).
        cancelled: ``True`` gdy przerwano na żądanie ``should_cancel``.
        timed_out: ``True`` gdy proces przekroczył ``timeout`` i został ubity.
        output: przechowywany (przycięty do ``max_log_bytes``) log stdout+stderr.
        truncated_bytes: liczba bajtów logu odrzuconych po przekroczeniu limitu.
    """

    returncode: int
    cancelled: bool = False
    timed_out: bool = False
    output: str = ""
    truncated_bytes: int = 0


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


def run_process(
    cmd: list[str],
    *,
    cwd: str | None = None,
    should_cancel: CancelCheck | None = None,
    limits: ProcessLimits = DEFAULT_PROCESS_LIMITS,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Uruchamia proces synchronicznie i zwraca wynik z przechwyconym logiem.

    Semantyka (timeout, limit logu, ubijanie drzewa, anulowanie) jest identyczna
    jak w :func:`run_process_streaming` — różnica polega wyłącznie na braku
    callbacku ``on_line`` (log dostajesz w ``result.output``).

    Raises:
        OSError: gdy nie udało się wystartować procesu (np. brak pliku wykonywalnego).
    """
    return _run(cmd, None, cwd, should_cancel, limits, env)


def run_process_streaming(
    cmd: list[str],
    on_line: LineSink,
    *,
    cwd: str | None = None,
    should_cancel: CancelCheck | None = None,
    limits: ProcessLimits = DEFAULT_PROCESS_LIMITS,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Uruchamia proces, streamując połączone stdout/stderr przez ``on_line``.

    Odczyt biegnie w wątku pomocniczym, a pętla główna próbkuje kolejkę co
    :data:`_POLL_INTERVAL_S`, dzięki czemu ``should_cancel`` i ``timeout`` działają
    także gdy proces milczy. Log jest równolegle gromadzony (przycięty) w wyniku.

    Raises:
        OSError: gdy nie udało się wystartować procesu.
    """
    return _run(cmd, on_line, cwd, should_cancel, limits, env)


class _Outcome(NamedTuple):
    """Wynik pętli konsumpcji: co przerwało czytanie."""

    cancelled: bool
    timed_out: bool


class _LogBuffer:
    """Bufor logu o ograniczonym rozmiarze z licznikiem uciętych bajtów."""

    def __init__(self, max_bytes: int) -> None:
        self._max = max_bytes
        self._parts: list[str] = []
        self._size = 0
        self.truncated = 0

    def add(self, line: str) -> None:
        """Dokłada linię, jeśli mieści się w limicie; nadmiar liczy jako ucięty."""
        chunk = line + "\n"
        size = len(chunk.encode("utf-8", "replace"))
        if self._size + size <= self._max:
            self._parts.append(chunk)
            self._size += size
        else:
            self.truncated += size

    def text(self) -> str:
        """Zwraca zgromadzony (przycięty) log."""
        return "".join(self._parts)


def _run(
    cmd: list[str],
    on_line: LineSink | None,
    cwd: str | None,
    should_cancel: CancelCheck | None,
    limits: ProcessLimits,
    env: dict[str, str] | None,
) -> ProcessResult:
    """Wspólny silnik dla trybu sync i streaming (jedna semantyka)."""
    proc = _spawn(cmd, cwd, env)
    lines: queue.Queue[str | None] = queue.Queue(maxsize=limits.max_queue_lines)
    reader = threading.Thread(target=_pump_lines, args=(proc, lines), daemon=True)
    reader.start()

    buffer = _LogBuffer(limits.max_log_bytes)
    deadline = None if limits.timeout is None else time.monotonic() + limits.timeout
    outcome = _consume_loop(lines, buffer, on_line, should_cancel, deadline)
    try:
        if outcome.cancelled or outcome.timed_out:
            _kill_tree(proc, limits.terminate_grace_s)
            _drain(lines, reader, buffer, on_line)
        returncode = proc.wait()
    finally:
        reader.join(timeout=1.0)

    return ProcessResult(
        returncode=returncode,
        cancelled=outcome.cancelled,
        timed_out=outcome.timed_out,
        output=buffer.text(),
        truncated_bytes=buffer.truncated,
    )


def _consume_loop(
    lines: queue.Queue[str | None],
    buffer: _LogBuffer,
    on_line: LineSink | None,
    should_cancel: CancelCheck | None,
    deadline: float | None,
) -> _Outcome:
    """Konsumuje linie do sentinela EOF; kończy wcześniej na anulowaniu/timeoucie."""
    while True:
        if should_cancel is not None and should_cancel():
            return _Outcome(cancelled=True, timed_out=False)
        if deadline is not None and time.monotonic() >= deadline:
            return _Outcome(cancelled=False, timed_out=True)
        try:
            item = lines.get(timeout=_POLL_INTERVAL_S)
        except queue.Empty:
            continue
        if item is None:  # sentinel EOF — proces zamknął strumień
            return _Outcome(cancelled=False, timed_out=False)
        _consume(item, buffer, on_line)


def _consume(line: str, buffer: _LogBuffer, on_line: LineSink | None) -> None:
    """Zapisuje linię do bufora i (w trybie streaming) woła ``on_line``."""
    buffer.add(line)
    if on_line is not None:
        on_line(line, level_for_line(line))


def _drain(
    lines: queue.Queue[str | None],
    reader: threading.Thread,
    buffer: _LogBuffer,
    on_line: LineSink | None,
) -> None:
    """Po ubiciu procesu dokańcza konsumpcję kolejki.

    Zdejmuje backpressure z wątku czytającego (kolejka ograniczona) i domyka log.
    Kończy na sentinelu albo gdy czytnik już nie żyje i kolejka jest pusta.
    """
    while True:
        try:
            item = lines.get(timeout=_POLL_INTERVAL_S)
        except queue.Empty:
            if not reader.is_alive():
                return
            continue
        if item is None:
            return
        _consume(item, buffer, on_line)


def _spawn(cmd: list[str], cwd: str | None, env: dict[str, str] | None) -> subprocess.Popen[str]:
    """Startuje proces we WŁASNEJ grupie/sesji, by dało się ubić całe drzewo."""
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if sys.platform == "win32":
        # Nowa grupa procesu + brak okna konsoli; drzewo ubijemy przez taskkill /T.
        kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    else:
        # Nowa sesja → proces staje się liderem grupy; dzieci dziedziczą pgid,
        # więc os.killpg dosięga całego drzewa.
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _pump_lines(proc: subprocess.Popen[str], sink: queue.Queue[str | None]) -> None:
    """Czyta stdout linia po linii do kolejki; na końcu wrzuca sentinel EOF.

    ``sink.put`` na pełnej (ograniczonej) kolejce blokuje — to zamierzony
    backpressure. Pętla główna/„_drain" zawsze konsumuje, więc czytnik dokończy.
    """
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                sink.put(line.rstrip("\n"))
    finally:
        sink.put(None)


def _kill_tree(proc: subprocess.Popen[str], grace: float) -> None:
    """Kończy CAŁE drzewo procesu potomnego (cross-platform)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        _kill_tree_windows(proc, grace)
    else:
        _kill_tree_posix(proc, grace)


def _kill_tree_posix(proc: subprocess.Popen[str], grace: float) -> None:
    """POSIX: SIGTERM na grupę procesu → karencja → SIGKILL na grupę.

    Cała treść pod dodatnim guardem ``sys.platform != "win32"`` — poza POSIX
    ``os.getpgid``/``killpg``/``SIGKILL`` nie istnieją (mypy ``--platform win32``).
    """
    if sys.platform != "win32":
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        _signal_group(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            _signal_group(pgid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=grace)


def _signal_group(pgid: int, sig: int) -> None:
    """Wysyła sygnał do całej grupy procesu, tolerując znikły proces (tylko POSIX)."""
    if sys.platform != "win32":
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(pgid, sig)


def _kill_tree_windows(proc: subprocess.Popen[str], grace: float) -> None:
    """Windows: ``taskkill /T /F`` ubija całe drzewo po PID; awaryjnie ``kill``."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=grace,
            check=False,
        )
    _hard_kill(proc, grace)


def _hard_kill(proc: subprocess.Popen[str], grace: float) -> None:
    """Twarde ubicie procesu i zebranie kodu wyjścia (tolerancyjne)."""
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=grace)
