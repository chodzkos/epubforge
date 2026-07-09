"""Wspólny runner strumieniowy konwerterów — log na żywo + postęp + anulowanie.

Cienka nakładka na :func:`epubforge.core.streaming.run_subprocess_streaming`,
która przy okazji strumieniowania logu parsuje procenty Calibre i przekazuje je
do ``on_progress`` jako ``(NN, 100)``.
"""

from __future__ import annotations

from collections.abc import Callable

from epubforge.core.streaming import (
    CancelCheck,
    LineSink,
    ProcessResult,
    parse_calibre_percent,
    run_subprocess_streaming,
)

ProgressSink = Callable[[int, int], None]


def run_command_streaming(
    command: list[str],
    on_line: LineSink,
    on_progress: ProgressSink | None = None,
    should_cancel: CancelCheck | None = None,
) -> ProcessResult:
    """Uruchamia komendę strumieniowo; parsuje „NN%" Calibre na ``on_progress``.

    Args:
        command: pełna komenda konwertera.
        on_line: sink linii logu ``(text, level)``.
        on_progress: opcjonalny sink postępu ``(current, total)``; wołany dla
            linii zawierających procent (``total`` = 100).
        should_cancel: predykat anulowania przekazywany do runnera.

    Returns:
        :class:`ProcessResult` (kod wyjścia + flagi ``cancelled``/``timed_out``).
    """

    def handle(text: str, level: str) -> None:
        on_line(text, level)
        if on_progress is not None:
            percent = parse_calibre_percent(text)
            if percent is not None:
                on_progress(percent, 100)

    return run_subprocess_streaming(command, handle, should_cancel=should_cancel)
