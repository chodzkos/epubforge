"""Hurtowe wzbogacanie metadanych EPUB oraz biblioteki Calibre (Etap 30).

Publiczne API:

* :func:`enrich_paths` — wzbogać pliki/katalogi EPUB (sekwencyjnie, wspólny rate
  limiter/cache LC);
* :func:`enrich_library` — wzbogać bibliotekę Calibre przez ``calibredb``;
* :class:`EnrichOptions`, :class:`BookOutcome`, :class:`EnrichSummary` — model;
* :func:`write_report`, :func:`format_summary`, :func:`format_outcome_line` — raport.
"""

from epubforge.enrich.calibre import CalibreError, enrich_library, preflight
from epubforge.enrich.engine import collect_epubs, enrich_epub, enrich_paths, plan_enrichment
from epubforge.enrich.model import (
    DEFAULT_FIELDS,
    POLICIES,
    BookOutcome,
    EnrichOptions,
    EnrichSummary,
    FieldChange,
    normalize_fields,
)
from epubforge.enrich.report import format_outcome_line, format_summary, write_report

__all__ = [
    "DEFAULT_FIELDS",
    "POLICIES",
    "BookOutcome",
    "CalibreError",
    "EnrichOptions",
    "EnrichSummary",
    "FieldChange",
    "collect_epubs",
    "enrich_epub",
    "enrich_library",
    "enrich_paths",
    "format_outcome_line",
    "format_summary",
    "normalize_fields",
    "plan_enrichment",
    "preflight",
    "write_report",
]
