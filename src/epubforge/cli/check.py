"""Subkomenda CLI ``epubforge check`` — walidacja EPUB przez EpubCheck."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from epubforge.core import Tool, ValidationError, detect_with_cache
from epubforge.i18n import _
from epubforge.validators import Severity, ValidationMessage, ValidationReport, run_epubcheck

# Porządek istotności malejąco — do filtra ``--min-severity``.
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.FATAL: 3,
    Severity.ERROR: 2,
    Severity.WARNING: 1,
    Severity.INFO: 0,
}

# Kody wyjścia: 0 = poprawny, 1 = błędy walidacji, 2 = brak narzędzi.
_EXIT_OK = 0
_EXIT_INVALID = 1
_EXIT_NO_TOOLS = 2


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``check`` w głównym parserze argparse."""
    parser = subparsers.add_parser("check", help=_("Waliduj EPUB przez EpubCheck"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB do walidacji"))
    parser.add_argument("--json", type=Path, help=_("Zapisz pełny raport do pliku JSON"))
    parser.add_argument(
        "--min-severity",
        choices=("info", "warning", "error", "fatal"),
        default="info",
        help=_("Pokaż tylko komunikaty od tego poziomu wzwyż"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Waliduje plik EPUB i wypisuje raport; zwraca kod wyjścia."""
    tools = detect_with_cache()
    java = tools.get("java")
    jar = tools.get("epubcheck")
    if not _tools_ready(java, jar):
        print(_tools_missing_help(), file=sys.stderr)
        return _EXIT_NO_TOOLS
    assert java is not None and java.path is not None  # gwarantowane przez _tools_ready
    assert jar is not None and jar.path is not None

    try:
        report = run_epubcheck(args.file, java.path, jar.path)
    except ValidationError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return _EXIT_INVALID

    if args.json is not None:
        _write_json(args.json, report)
    _print_report(report, Severity(args.min_severity))
    return _EXIT_OK if report.valid else _EXIT_INVALID


def _tools_ready(java: Tool | None, jar: Tool | None) -> bool:
    """Czy ``java`` (≥11) i ``epubcheck.jar`` są dostępne."""
    return (
        java is not None
        and java.available
        and java.path is not None
        and jar is not None
        and jar.available
        and jar.path is not None
    )


def _print_report(report: ValidationReport, min_severity: Severity) -> None:
    """Wypisuje podsumowanie (liczby per poziom) i przefiltrowaną listę komunikatów."""
    counts = report.counts()
    print(
        _("EPUB: {path}").format(path=report.epub_path)
        + (_(" — POPRAWNY") if report.valid else _(" — NIEPOPRAWNY"))
    )
    print(
        _("Błędów: {fatal_error}  ·  Ostrzeżeń: {warning}  ·  Informacji: {info}").format(
            fatal_error=counts[Severity.FATAL] + counts[Severity.ERROR],
            warning=counts[Severity.WARNING],
            info=counts[Severity.INFO],
        )
    )
    threshold = _SEVERITY_ORDER[min_severity]
    for message in report.messages:
        if _SEVERITY_ORDER[message.severity] < threshold:
            continue
        print(_format_message(message))


def _format_message(message: ValidationMessage) -> str:
    """Formatuje wiersz „ścieżka:linia [KOD] treść"."""
    where = message.internal_path or "—"
    if message.line is not None:
        where = f"{where}:{message.line}"
    return f"[{message.severity.value.upper()}] {where} [{message.code}] {message.message}"


def _write_json(path: Path, report: ValidationReport) -> None:
    """Zapisuje pełny raport jako JSON (``dataclasses.asdict`` + ścieżki jako str)."""
    path.write_text(
        json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _tools_missing_help() -> str:
    """Zwraca instrukcję instalacji Javy i EpubChecka (gdy brak narzędzi)."""
    return _(
        "Walidacja wymaga Javy (Temurin JRE 17+) oraz epubcheck.jar.\n"
        "1. Zainstaluj Temurin: https://adoptium.net/\n"
        "2. Pobierz epubcheck-5.x: https://github.com/w3c/epubcheck/releases\n"
        "3. Rozpakuj jar do <config>/epubcheck/epubcheck.jar lub wskaż go w GUI."
    )
