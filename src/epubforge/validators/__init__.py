"""Walidatory plików EPUB (EpubCheck) — czysta logika, bez zależności od GUI."""

from epubforge.validators.epubcheck import (
    Severity,
    ValidationMessage,
    ValidationReport,
    parse_report,
    run_epubcheck,
)

__all__ = [
    "Severity",
    "ValidationMessage",
    "ValidationReport",
    "parse_report",
    "run_epubcheck",
]
