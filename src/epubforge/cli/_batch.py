"""Wspólna obsługa batchowych komend CLI."""

from __future__ import annotations

import argparse
import difflib
import time
import zipfile
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from rich.console import Console
from rich.table import Table
from rich.text import Text

from epubforge.core import Epub
from epubforge.gui.editor_files import decode_text, is_editable, resolve_internal_path
from epubforge.i18n import _

BatchHandler: TypeAlias = Callable[[Path, object], str]
BatchResult: TypeAlias = tuple[str, bool, str, float]

_DIFF_LINE_LIMIT = 40


@dataclass(frozen=True)
class BatchTask:
    """Pojedyncza praca dla procesu roboczego."""

    path: Path
    handler: BatchHandler
    payload: object


def add_batch_arguments(parser: argparse.ArgumentParser, *, file_help: str) -> None:
    """Dodaje pozycyjne pliki ``nargs='+'`` oraz ``--jobs`` do parsera."""
    parser.add_argument("files", type=Path, nargs="+", help=file_help)
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        default=1,
        help=_("Liczba równoległych procesów roboczych (domyślnie: 1)"),
    )


def run_batch(
    paths: Sequence[Path],
    *,
    jobs: int,
    handler: BatchHandler,
    payload: object,
) -> int:
    """Uruchamia handler dla unikalnych plików i drukuje raport zbiorczy."""
    unique_paths = _deduplicate_paths(paths)
    tasks = [BatchTask(path=path, handler=handler, payload=payload) for path in unique_paths]
    results = _run_tasks(tasks, jobs=max(1, jobs))
    _print_results(results)
    return 1 if any(not ok for _path, ok, _message, _seconds in results) else 0


def format_dry_run(epub: Epub, *, diff_full: bool) -> str:
    """Formatuje diff niezapisanych zmian w otwartym EPUB-ie."""
    changes = epub.pending_changes()
    originals = _read_original_entries(epub.path, changes.modified, changes.deleted)
    media_types = _media_types_by_path(epub)
    lines: list[str] = []

    for internal_path, updated in changes.modified.items():
        original = originals.get(internal_path, b"")
        media_type = media_types.get(internal_path)
        lines.extend(
            _format_changed_entry(
                internal_path,
                original,
                updated,
                media_type=media_type,
                diff_full=diff_full,
            )
        )

    for internal_path in sorted(changes.deleted):
        original = originals.get(internal_path, b"")
        media_type = media_types.get(internal_path)
        lines.extend(
            _format_changed_entry(
                internal_path,
                original,
                b"",
                media_type=media_type,
                diff_full=diff_full,
            )
        )

    lines.append(
        _("{modified} plików zmienionych, {deleted} usuniętych; nic nie zapisano").format(
            modified=len(changes.modified),
            deleted=len(changes.deleted),
        )
    )
    return "\n".join(lines)


def _run_batch_worker(task: BatchTask) -> BatchResult:
    """Top-level worker dla ``ProcessPoolExecutor``."""
    start = time.perf_counter()
    try:
        message = task.handler(task.path, task.payload)
    except Exception as exc:
        return (str(task.path), False, _("Błąd: {error}").format(error=exc), _elapsed(start))
    return (str(task.path), True, message, _elapsed(start))


def _run_tasks(tasks: Sequence[BatchTask], *, jobs: int) -> list[BatchResult]:
    """Uruchamia prace sekwencyjnie albo w puli procesów."""
    if jobs == 1 or len(tasks) <= 1:
        return [_run_batch_worker(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        return list(executor.map(_run_batch_worker, tasks))


def _print_results(results: Sequence[BatchResult]) -> None:
    """Drukuje tabelę rich oraz komunikaty szczegółowe z workerów."""
    console = Console()
    table = Table()
    table.add_column(_("Plik"))
    table.add_column(_("Status"))
    table.add_column(_("Czas"), justify="right")
    for path, ok, _message, seconds in results:
        status = Text(_("OK") if ok else _("FAIL"), style="green" if ok else "red")
        table.add_row(path, status, f"{seconds:.2f}s")
    console.print(table)
    for _path, _ok, message, _seconds in results:
        if message:
            console.print(message, markup=False, highlight=False, soft_wrap=True)


def _deduplicate_paths(paths: Sequence[Path]) -> list[Path]:
    """Usuwa duplikaty ścieżek, zachowując pierwsze wystąpienie."""
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _positive_int(value: str) -> int:
    """Parsuje dodatnią liczbę całkowitą dla argparse."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(_("--jobs musi być większe od zera"))
    return parsed


def _elapsed(start: float) -> float:
    """Zwraca czas od ``start`` w sekundach."""
    return time.perf_counter() - start


def _read_original_entries(
    epub_path: Path,
    modified: dict[str, bytes],
    deleted: frozenset[str],
) -> dict[str, bytes]:
    """Czyta oryginalne bajty tylko dla wpisów potrzebnych do diffu."""
    wanted = set(modified) | set(deleted)
    originals: dict[str, bytes] = {}
    with zipfile.ZipFile(epub_path) as zf:
        available = set(zf.namelist())
        for internal_path in wanted:
            if internal_path in available:
                originals[internal_path] = zf.read(internal_path)
    return originals


def _media_types_by_path(epub: Epub) -> dict[str, str]:
    """Buduje mapę ścieżka wewnętrzna -> media-type z manifestu."""
    opf_dir = epub.opf_dir()
    return {resolve_internal_path(item.href, opf_dir): item.media_type for item in epub.manifest}


def _format_changed_entry(
    internal_path: str,
    original: bytes,
    updated: bytes,
    *,
    media_type: str | None,
    diff_full: bool,
) -> list[str]:
    """Formatuje zmianę tekstową jako unified diff, a binarną jako deltę rozmiaru."""
    if is_editable(internal_path, media_type):
        return _format_text_diff(
            internal_path,
            original,
            updated,
            diff_full=diff_full,
        )
    delta = len(updated) - len(original)
    return [
        _("{path}: plik binarny, delta rozmiaru {delta:+d} B").format(
            path=internal_path,
            delta=delta,
        )
    ]


def _format_text_diff(
    internal_path: str,
    original: bytes,
    updated: bytes,
    *,
    diff_full: bool,
) -> list[str]:
    """Zwraca ograniczony unified diff dla pliku tekstowego."""
    original_text, _original_replaced = decode_text(original)
    updated_text, _updated_replaced = decode_text(updated)
    diff = list(
        difflib.unified_diff(
            original_text.splitlines(),
            updated_text.splitlines(),
            fromfile=f"a/{internal_path}",
            tofile=f"b/{internal_path}",
            lineterm="",
        )
    )
    if diff_full or len(diff) <= _DIFF_LINE_LIMIT:
        return diff
    hidden = len(diff) - _DIFF_LINE_LIMIT
    return [
        *diff[:_DIFF_LINE_LIMIT],
        _("... skrócono diff o {count} linii; użyj --diff-full, aby zobaczyć całość").format(
            count=hidden
        ),
    ]
