"""Mapowanie kodów języka na ISO 639-1 (dwuliterowe, jak w ``dc:language``).

Zewnętrzne katalogi podają język różnie: BN w rekordzie MARC (pole ``008`` lub
``041``) używa trzyliterowych kodów ISO 639-2/B (``pol``, ``eng``), Open Library
też trzyliterowych (``/languages/eng``). Docelowy ``dc:language`` EPUB-a to
zwykle dwuliterowy ISO 639-1 — ten moduł tłumaczy najczęstsze kody.
"""

from __future__ import annotations

# Mapa ISO 639-2/B (i wariantów /T) → ISO 639-1. Ograniczona do języków realnie
# spotykanych w katalogach; nieznany kod zwraca pusty łańcuch (pole zostaje puste).
_ISO3_TO_ISO1 = {
    "pol": "pl",
    "eng": "en",
    "ger": "de",
    "deu": "de",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "ita": "it",
    "rus": "ru",
    "ukr": "uk",
    "cze": "cs",
    "ces": "cs",
    "slo": "sk",
    "slk": "sk",
    "dut": "nl",
    "nld": "nl",
    "por": "pt",
    "swe": "sv",
    "nor": "no",
    "dan": "da",
    "fin": "fi",
    "lat": "la",
    "gre": "el",
    "ell": "el",
    "hun": "hu",
    "lit": "lt",
    "lav": "lv",
    "est": "et",
    "jpn": "ja",
    "chi": "zh",
    "zho": "zh",
}


def to_iso639_1(code: str) -> str:
    """Zwraca dwuliterowy kod ISO 639-1 dla podanego kodu języka lub pusty.

    Trzyliterowe kody są tłumaczone przez :data:`_ISO3_TO_ISO1`; poprawny kod
    dwuliterowy jest zwracany bez zmian. Wszystko inne (w tym pusty string) → ``""``.

    Args:
        code: kod języka w dowolnym z formatów (``pol``, ``pl``, ``PL``).

    Returns:
        Kod ISO 639-1 małymi literami albo pusty łańcuch, gdy nierozpoznany.
    """
    normalized = code.strip().lower()
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    return _ISO3_TO_ISO1.get(normalized, "")
