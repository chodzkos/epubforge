"""Eksport raportów i workery zakładki Walidacja."""

from __future__ import annotations

import dataclasses
import json
from html import escape
from pathlib import Path
from typing import cast

from chodzkos_gui_kit.qt.dialogs import save_file
from PySide6.QtWidgets import QLabel, QWidget

from epubforge.core import ConfigStore
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel
from epubforge.i18n import _
from epubforge.validators import (
    AceReport,
    ValidationMessage,
    ValidationReport,
    run_ace,
    run_epubcheck,
)


class ValidatorReportsMixin:
    """Obsługa eksportu raportów bez powiększania głównego modułu zakładki."""

    _report: ValidationReport | None
    _ace_report: AceReport | None
    _config: ConfigStore | None
    status_label: QLabel

    def _export_report(self) -> None:
        """Eksportuje aktywny raport EpubCheck albo Ace do JSON lub HTML."""
        if self._report is None and self._ace_report is None:
            return
        path = save_file(
            cast(QWidget, self),
            _("Eksport raportu"),
            "",
            _("JSON (*.json);;HTML (*.html)"),
            self._config,
        )
        if not path:
            return
        target = Path(path)
        as_html = target.suffix.lower() == ".html"
        if self._ace_report is not None:
            content = (
                _ace_report_to_html(self._ace_report)
                if as_html
                else _ace_report_to_json(self._ace_report)
            )
        else:
            assert self._report is not None
            content = _report_to_html(self._report) if as_html else _report_to_json(self._report)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            self.status_label.setText(_("Nie udało się zapisać: {error}").format(error=exc))
            return
        self.status_label.setText(_("Zapisano raport: {name}").format(name=target.name))


def _report_to_json(report: ValidationReport) -> str:
    """Serializuje raport do JSON, zapisując ścieżki jako tekst."""
    return json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str)


def _report_to_html(report: ValidationReport) -> str:
    """Buduje samowystarczalną stronę HTML z komunikatami EpubChecka."""
    verdict = "valid" if report.valid else "INVALID"
    rows = "\n".join(
        f"<tr><td>{escape(message.severity.value)}</td><td>{escape(message.code)}</td>"
        f"<td>{escape(_location_text(message))}</td><td>{escape(message.message)}</td></tr>"
        for message in report.messages
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>EpubCheck — {escape(report.epub_path.name)}</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}</style></head><body>"
        f"<h1>EpubCheck: {escape(report.epub_path.name)}</h1>"
        f"<p>{escape(verdict)} · {escape(report.epubcheck_version)}</p>"
        "<table><thead><tr><th>Severity</th><th>Code</th><th>Location</th><th>Message</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def _location_text(message: ValidationMessage) -> str:
    """Składa ścieżkę i linię komunikatu do eksportu."""
    where = message.internal_path or "—"
    return f"{where}:{message.line}" if message.line is not None else where


def _ace_report_to_json(report: AceReport) -> str:
    """Serializuje raport Ace do JSON, zapisując ścieżki jako tekst."""
    return json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str)


def _ace_report_to_html(report: AceReport) -> str:
    """Buduje samowystarczalną stronę HTML z naruszeniami Ace."""
    verdict = "accessible" if report.accessible else "INACCESSIBLE"
    rows = "\n".join(
        f"<tr><td>{escape(message.severity.value)}</td><td>{escape(message.rule)}</td>"
        f"<td>{escape(message.internal_path or '—')}</td>"
        f"<td>{escape(message.message)}</td></tr>"
        for message in report.messages
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>DAISY Ace — {escape(report.epub_path.name)}</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}</style></head><body>"
        f"<h1>DAISY Ace: {escape(report.epub_path.name)}</h1>"
        f"<p>{escape(verdict)} · {escape(report.ace_version)}</p>"
        "<table><thead><tr><th>Severity</th><th>Rule</th><th>Location</th><th>Message</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def _run_check_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    epub_path: Path,
    java_path: Path,
    jar_path: Path,
) -> ValidationReport:
    """Uruchamia EpubCheck w workerze z obsługą anulowania."""
    return run_epubcheck(epub_path, java_path, jar_path, should_cancel=should_cancel)


def _run_ace_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    epub_path: Path,
    ace_path: Path,
) -> AceReport:
    """Uruchamia DAISY Ace w workerze z obsługą anulowania."""
    return run_ace(epub_path, ace_path, should_cancel=should_cancel)
