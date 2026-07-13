"""Testy fault-injection wspólnego runnera procesów (``core/process.py``, F-13).

Sprawdzamy realne zachowanie przy awariach: timeout, ogromny log, proces potomny
(ubijanie CAŁEGO drzewa przy anulowaniu), błędy kodowania oraz spójność semantyki
trybu synchronicznego i strumieniowego. Uruchamiamy `sys.executable` z krótkim
``-c`` — bez zewnętrznych binariów, więc test jest cross-platform.

Kryterium (część): anulowanie NIE zostawia aktywnego drzewa procesu.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import epubforge
from epubforge.core.process import (
    ProcessLimits,
    ProcessResult,
    run_process,
    run_process_streaming,
)


def _py(code: str, *args: str) -> list[str]:
    """Buduje komendę `python -c <code> <args...>` na bieżącym interpreterze."""
    return [sys.executable, "-c", code, *args]


def test_run_process_captures_combined_output() -> None:
    """Sync: stdout+stderr trafiają scalone do ``output``; kod wyjścia zachowany."""
    code = "import sys; print('na stdout'); print('na stderr', file=sys.stderr)"
    result = run_process(_py(code))
    assert result.returncode == 0
    assert not result.cancelled and not result.timed_out
    assert "na stdout" in result.output
    assert "na stderr" in result.output
    assert result.truncated_bytes == 0


def test_streaming_emits_each_line() -> None:
    """Streaming: ``on_line`` dostaje kolejne linie, a wynik ma ten sam log."""
    lines: list[tuple[str, str]] = []
    result = run_process_streaming(
        _py("print('a'); print('b')"), lambda t, lvl: lines.append((t, lvl))
    )
    assert result.returncode == 0
    assert [text for text, _ in lines] == ["a", "b"]


def test_sync_and_streaming_same_semantics() -> None:
    """Ta sama komenda przez oba API → identyczny kod wyjścia i identyczny log."""
    cmd = _py("print('x'); print('y')")
    sync = run_process(cmd)
    stream = run_process_streaming(cmd, lambda _t, _l: None)
    assert sync.returncode == stream.returncode == 0
    assert sync.output == stream.output == "x\ny\n"


def test_timeout_flags_and_kills_fast() -> None:
    """Proces przekraczający ``timeout`` jest ubity szybko i oznaczony ``timed_out``."""
    started = time.monotonic()
    result = run_process(
        _py("import time; time.sleep(30)"),
        limits=ProcessLimits(timeout=0.5, terminate_grace_s=2.0),
    )
    elapsed = time.monotonic() - started
    assert result.timed_out
    assert not result.cancelled
    assert result.returncode != 0
    assert elapsed < 10  # ubite po timeoucie, NIE czekało pełnych 30 s


def test_cancel_terminates_whole_process_tree(tmp_path: Path) -> None:
    """Anulowanie ubija całe drzewo: proces-wnuk przestaje bić „heartbeat".

    Rodzic uruchamia potomka, który cyklicznie zapisuje rosnący licznik do pliku.
    Po anulowaniu (runner ubija grupę/drzewo) plik NIE zmienia się już dalej —
    dowód, że nie została żadna aktywna „sierota".
    """
    marker = tmp_path / "heartbeat.txt"
    child_src = (
        "import sys, time\n"
        "m = sys.argv[1]\n"
        "i = 0\n"
        "while True:\n"
        "    with open(m, 'w') as f:\n"
        "        f.write(str(i))\n"
        "    i += 1\n"
        "    time.sleep(0.05)\n"
    )
    parent_src = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
        "while True:\n"
        "    time.sleep(0.05)\n"
    )
    cmd = _py(parent_src, child_src, str(marker))

    def should_cancel() -> bool:
        # Anuluj, gdy wnuk już zaczął bić (plik istnieje i ma treść).
        return marker.exists() and marker.read_text() != ""

    result = run_process(
        cmd, should_cancel=should_cancel, limits=ProcessLimits(timeout=30, terminate_grace_s=3.0)
    )
    assert result.cancelled

    # Daj ewentualnie żywemu wnukowi szansę na kolejny zapis, potem zbadaj stabilność.
    time.sleep(0.3)
    first = marker.read_text()
    time.sleep(1.0)
    assert marker.read_text() == first, "wnuk wciąż żyje — drzewo procesu nie zostało ubite"


def test_huge_log_is_truncated_with_counter() -> None:
    """Ogromny log jest przycięty do limitu, a odrzucone bajty są policzone.

    Sprawdza zarazem, że runner KONSUMUJE cały strumień (proces kończy się kodem 0)
    mimo ograniczonej kolejki — backpressure działa, pamięć nie puchnie.
    """
    code = "[print('x' * 200) for _ in range(20000)]"  # ~4 MB na stdout
    limits = ProcessLimits(max_log_bytes=10_000, timeout=60)
    result = run_process(_py(code), limits=limits)
    assert result.returncode == 0
    assert result.truncated_bytes > 0
    assert len(result.output.encode("utf-8")) <= limits.max_log_bytes


def test_encoding_errors_are_replaced_not_raised() -> None:
    """Nie-UTF-8 bajty na stdout są dekodowane z podmianą, bez wyjątku."""
    code = "import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok\\n'); sys.stdout.flush()"
    result = run_process(_py(code))
    assert result.returncode == 0
    assert "ok" in result.output  # nie wysypało się na dekodowaniu


def test_missing_executable_raises_oserror() -> None:
    """Brak pliku wykonywalnego → ``OSError`` (runner nie połyka błędu startu)."""
    try:
        run_process(["definitely-not-a-real-binary-xyz", "--version"])
    except OSError:
        pass
    else:  # pragma: no cover — nie powinno się zdarzyć
        raise AssertionError("oczekiwano OSError przy braku pliku wykonywalnego")


def test_result_defaults() -> None:
    """Domyślne pola :class:`ProcessResult` — zgodność wsteczna (3 → 5 pól)."""
    result = ProcessResult(returncode=0)
    assert result.cancelled is False
    assert result.timed_out is False
    assert result.output == ""
    assert result.truncated_bytes == 0


def test_converters_and_validators_use_shared_runner() -> None:
    """Żaden konwerter/walidator NIE woła ``subprocess`` wprost — wszystko przez runner.

    Bramka egzekwuje kryterium „wspólny runner dla wszystkich konwerterów i
    walidatorów": wyszukanie ``subprocess.run``/``subprocess.Popen`` w tych
    pakietach zwraca pustkę (procesy startują wyłącznie przez ``core/process.py``).
    """
    root = Path(epubforge.__file__).parent
    direct_call = re.compile(r"\bsubprocess\.(run|Popen|call|check_output|check_call)\b")
    offenders: list[str] = []
    for package in ("converters", "validators"):
        for path in (root / package).rglob("*.py"):
            if direct_call.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"bezpośrednie użycie subprocess poza runnerem: {offenders}"
