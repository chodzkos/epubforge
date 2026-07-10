"""Subkomenda CLI ``epubforge a11y`` — audyt dostępności EPUB przez DAISY Ace."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from epubforge.core import Tool, ValidationError, detect_with_cache
from epubforge.i18n import _
from epubforge.validators import AceMessage, AceReport, Severity, run_ace

# Porządek istotności malejąco — do filtra ``--min-severity`` (Ace nie ma FATAL).
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.FATAL: 3,
    Severity.ERROR: 2,
    Severity.WARNING: 1,
    Severity.INFO: 0,
}

# Kody wyjścia: 0 = dostępny, 1 = naruszenia/błąd, 2 = brak narzędzia.
_EXIT_OK = 0
_EXIT_INACCESSIBLE = 1
_EXIT_NO_TOOLS = 2


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``a11y`` w głównym parserze argparse."""
    parser = subparsers.add_parser("a11y", help=_("Audyt dostępności EPUB przez DAISY Ace"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB do audytu"))
    parser.add_argument("--json", type=Path, help=_("Zapisz pełny raport do pliku JSON"))
    parser.add_argument(
        "--min-severity",
        choices=("info", "warning", "error"),
        default="info",
        help=_("Pokaż tylko naruszenia od tego poziomu wzwyż"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Audytuje plik EPUB i wypisuje raport dostępności; zwraca kod wyjścia."""
    tools = detect_with_cache()
    ace = tools.get("ace")
    if not _tool_ready(ace):
        print(_tool_missing_help(), file=sys.stderr)
        return _EXIT_NO_TOOLS
    assert ace is not None and ace.path is not None  # gwarantowane przez _tool_ready

    try:
        report = run_ace(args.file, ace.path)
    except ValidationError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return _EXIT_INACCESSIBLE

    if args.json is not None:
        _write_json(args.json, report)
    _print_report(report, Severity(args.min_severity))
    return _EXIT_OK if report.accessible else _EXIT_INACCESSIBLE


def _tool_ready(ace: Tool | None) -> bool:
    """Czy narzędzie ``ace`` jest dostępne."""
    return ace is not None and ace.available and ace.path is not None


def _print_report(report: AceReport, min_severity: Severity) -> None:
    """Wypisuje podsumowanie (liczby per poziom) i przefiltrowaną listę naruszeń."""
    counts = report.counts()
    print(
        _("EPUB: {path}").format(path=report.epub_path)
        + (_(" — DOSTĘPNY") if report.accessible else _(" — NIEDOSTĘPNY"))
    )
    print(
        _("Błędów: {error}  ·  Ostrzeżeń: {warning}  ·  Informacji: {info}").format(
            error=counts[Severity.ERROR],
            warning=counts[Severity.WARNING],
            info=counts[Severity.INFO],
        )
    )
    threshold = _SEVERITY_ORDER[min_severity]
    for message in report.messages:
        if _SEVERITY_ORDER[message.severity] < threshold:
            continue
        print(_format_message(message))


def _format_message(message: AceMessage) -> str:
    """Formatuje wiersz „[POZIOM] ścieżka [reguła] treść"."""
    where = message.internal_path or "—"
    return f"[{message.severity.value.upper()}] {where} [{message.rule}] {message.message}"


def _write_json(path: Path, report: AceReport) -> None:
    """Zapisuje pełny raport jako JSON (``dataclasses.asdict`` + ścieżki jako str)."""
    path.write_text(
        json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _tool_missing_help() -> str:
    """Zwraca instrukcję instalacji Ace (gdy brak narzędzia)."""
    return _(
        "Audyt dostępności wymaga narzędzia DAISY Ace (Node.js).\n"
        "1. Zainstaluj Node.js LTS: https://nodejs.org/\n"
        "2. Zainstaluj Ace: npm install -g @daisy/ace\n"
        "3. Upewnij się, że komenda `ace` jest w PATH."
    )
