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

# Pełne nazwy języków (po polsku) → ISO 639-1. LubimyCzytac podaje ``inLanguage``
# jako polską nazwę (np. „polski"), nie kod.
_NAME_TO_ISO1 = {
    "polski": "pl",
    "angielski": "en",
    "niemiecki": "de",
    "francuski": "fr",
    "hiszpański": "es",
    "włoski": "it",
    "rosyjski": "ru",
    "ukraiński": "uk",
    "czeski": "cs",
    "słowacki": "sk",
    "niderlandzki": "nl",
    "holenderski": "nl",
    "portugalski": "pt",
    "szwedzki": "sv",
    "norweski": "no",
    "duński": "da",
    "fiński": "fi",
    "łaciński": "la",
    "grecki": "el",
    "węgierski": "hu",
    "litewski": "lt",
    "łotewski": "lv",
    "estoński": "et",
    "japoński": "ja",
    "chiński": "zh",
}


def to_iso639_1(code: str) -> str:
    """Zwraca dwuliterowy kod ISO 639-1 dla podanego kodu/nazwy języka lub pusty.

    Rozpoznaje: poprawny kod dwuliterowy (zwracany bez zmian), trzyliterowy kod
    ISO 639-2/B (przez :data:`_ISO3_TO_ISO1`) oraz pełną polską nazwę języka
    (przez :data:`_NAME_TO_ISO1`, np. „polski" → ``pl``). Wszystko inne → ``""``.

    Args:
        code: kod lub nazwa języka (``pol``, ``pl``, ``PL``, ``polski``).

    Returns:
        Kod ISO 639-1 małymi literami albo pusty łańcuch, gdy nierozpoznany.
    """
    normalized = code.strip().lower()
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    if normalized in _ISO3_TO_ISO1:
        return _ISO3_TO_ISO1[normalized]
    return _NAME_TO_ISO1.get(normalized, "")
