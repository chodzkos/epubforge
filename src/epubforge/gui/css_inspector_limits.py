"""Czyste limity i helpery inspektora CSS bez zależności Qt."""

from __future__ import annotations

_MIB = 1024 * 1024
_UTF8_CHUNK_CHARS = 64 * 1024

# Modele inspektora są mniejsze od legalnego zasobu CSS i nigdy nie wpływają na zapis.
MAX_CSS_INSPECTOR_RULES = 10_000
MAX_CSS_INSPECTOR_DECLARATIONS = 20_000
MAX_CSS_INSPECTOR_RULE_DECLARATIONS = 2_000
MAX_CSS_INSPECTOR_SOURCE_BYTES = 1 * _MIB
CSS_INSPECTOR_WORKER_THRESHOLD_BYTES = 64 * 1024
# Jeden raport elementu nie parsuje synchronicznie więcej niż istniejący próg workera.
MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES = CSS_INSPECTOR_WORKER_THRESHOLD_BYTES

# Raport elementu ma osobne limity transportu, mapowania i skanowania CSSOM.
MAX_CSS_ELEMENT_REPORT_RULES = 2_000
MAX_CSS_ELEMENT_SCAN_RULES = 20_000
MAX_CSS_ELEMENT_REPORT_DECLARATIONS = 5_000
MAX_CSS_ELEMENT_RULE_DECLARATIONS = 2_000
MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS = 256
MAX_CSS_ELEMENT_REPORT_LIMITATIONS = 128
MAX_CSS_ELEMENT_REPORT_PATH_DEPTH = 64
MAX_CSS_ELEMENT_REPORT_TEXT_CHARS = 4_096
# Łączny budżet przed JSON.stringify ogranicza iloczyn niezależnych capów pól.
MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS = 1 * _MIB
MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS = 20_000


def utf8_fits(text: str, max_bytes: int) -> bool:
    """Sprawdza rozmiar UTF-8 małymi buforami i kończy po przekroczeniu limitu."""
    if max_bytes < 0:
        return False
    total = 0
    for start in range(0, len(text), _UTF8_CHUNK_CHARS):
        total += len(text[start : start + _UTF8_CHUNK_CHARS].encode("utf-8"))
        if total > max_bytes:
            return False
    return True
