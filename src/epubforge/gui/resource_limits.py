"""Skalibrowane limity bezpiecznej materializacji zasobów w GUI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader

from epubforge.gui.css_inspector_limits import (
    CSS_INSPECTOR_WORKER_THRESHOLD_BYTES as CSS_INSPECTOR_WORKER_THRESHOLD_BYTES,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_DECLARATIONS as MAX_CSS_ELEMENT_REPORT_DECLARATIONS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_LIMITATIONS as MAX_CSS_ELEMENT_REPORT_LIMITATIONS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS as MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_PATH_DEPTH as MAX_CSS_ELEMENT_REPORT_PATH_DEPTH,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_RULES as MAX_CSS_ELEMENT_REPORT_RULES,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS as MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS as MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS as MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_RULE_DECLARATIONS as MAX_CSS_ELEMENT_RULE_DECLARATIONS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_ELEMENT_SCAN_RULES as MAX_CSS_ELEMENT_SCAN_RULES,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_DECLARATIONS as MAX_CSS_INSPECTOR_DECLARATIONS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES as MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_MAPPING_STYLESHEETS as MAX_CSS_INSPECTOR_MAPPING_STYLESHEETS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_RULE_DECLARATIONS as MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_RULES as MAX_CSS_INSPECTOR_RULES,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_SOURCE_BYTES as MAX_CSS_INSPECTOR_SOURCE_BYTES,
)
from epubforge.gui.css_inspector_limits import (
    utf8_fits as utf8_fits,
)

_MIB = 1024 * 1024

MAX_EDITOR_TEXT_BYTES = 16 * _MIB
MAX_MAIN_PREVIEW_BYTES = 8 * _MIB
MAX_PREVIEW_CSS_BYTES = 4 * _MIB
MAX_DIRECT_IMAGE_ENCODED_BYTES = 32 * _MIB
MAX_IMAGE_PIXELS = 32_000_000
MAX_DECODED_IMAGE_BYTES = 128 * _MIB
# Fallback utrzymuje zdekodowane rastry przez lifetime aktywnego QTextDocument.
# Budżet agregatu jest równy istniejącemu ceilingowi pojedynczego obrazu, więc
# nie odrzuca obrazu legalnego według guarda per-image, ale ogranicza ich sumę.
MAX_FALLBACK_DECODED_IMAGE_BYTES = MAX_DECODED_IMAGE_BYTES


class RasterStatus(str, Enum):
    """Wynik lekkiej inspekcji metadanych rastra przed pełnym dekodowaniem."""

    OK = "ok"
    INVALID = "invalid"
    TOO_LARGE = "too_large"


class PreviewTextKind(str, Enum):
    """Klasa tekstu mająca osobny limit pipeline podglądu."""

    DOCUMENT = "document"
    CSS = "css"


@dataclass(frozen=True)
class RasterProbe:
    """Wymiary i przewidywany koszt dekodowania obrazu do 32-bitowego rastra."""

    status: RasterStatus
    width: int = 0
    height: int = 0
    pixels: int = 0
    decoded_bytes: int = 0


@dataclass(frozen=True)
class PreviewTextViolation:
    """Pierwszy overlay tekstowy przekraczający limit swojej klasy."""

    path: str
    kind: PreviewTextKind


def probe_raster(data: bytes) -> RasterProbe:
    """Czyta tylko metadane obrazu i stosuje limity pikseli oraz pamięci dekodu."""
    device = QBuffer()
    device.setData(QByteArray(data))
    if not device.open(QIODevice.OpenModeFlag.ReadOnly):
        return RasterProbe(RasterStatus.INVALID)
    reader = QImageReader(device)
    size = reader.size()
    width = size.width()
    height = size.height()
    if width <= 0 or height <= 0:
        return RasterProbe(RasterStatus.INVALID)
    # Pythonowe int nie przepełnia się; oba mnożenia są bezpieczne także dla
    # złośliwych wymiarów z nagłówka.
    pixels = width * height
    decoded_bytes = pixels * 4
    status = (
        RasterStatus.TOO_LARGE
        if pixels > MAX_IMAGE_PIXELS or decoded_bytes > MAX_DECODED_IMAGE_BYTES
        else RasterStatus.OK
    )
    return RasterProbe(status, width, height, pixels, decoded_bytes)


def find_preview_text_violation(
    *,
    current_path: str | None,
    dirty: Mapping[str, str | bytes],
    pending_sizes: Mapping[str, int],
    media_types: Mapping[str, str],
    document_limit: int = MAX_MAIN_PREVIEW_BYTES,
    css_limit: int = MAX_PREVIEW_CSS_BYTES,
) -> PreviewTextViolation | None:
    """Sprawdza dirty/pending teksty bez kopiowania ich payloadów."""
    for path, value in dirty.items():
        if path == current_path:
            continue
        kind, limit = _preview_text_budget(
            path, media_types.get(path), document_limit=document_limit, css_limit=css_limit
        )
        if kind is not None and limit is not None:
            fits = utf8_fits(value, limit) if isinstance(value, str) else len(value) <= limit
            if not fits:
                return PreviewTextViolation(path, kind)
    for path, size in pending_sizes.items():
        if path == current_path or path in dirty:
            continue
        kind, limit = _preview_text_budget(
            path, media_types.get(path), document_limit=document_limit, css_limit=css_limit
        )
        if kind is not None and limit is not None and size > limit:
            return PreviewTextViolation(path, kind)
    return None


def _preview_text_budget(
    path: str,
    media_type: str | None,
    *,
    document_limit: int,
    css_limit: int,
) -> tuple[PreviewTextKind | None, int | None]:
    """Zwraca klasę i limit dla XHTML/HTML/CSS używanych przez preview."""
    lowered = path.lower()
    declared = (media_type or "").lower()
    if declared == "text/css" or lowered.endswith(".css"):
        return PreviewTextKind.CSS, css_limit
    if declared in {"application/xhtml+xml", "text/html"} or lowered.endswith(
        (".xhtml", ".html", ".htm")
    ):
        return PreviewTextKind.DOCUMENT, document_limit
    return None, None
