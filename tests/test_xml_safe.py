"""Testy regresyjne utwardzenia parsera XML (:mod:`epubforge.core._xml_safe`).

Sprawdzają, że niezaufany XML z EPUB-a nie prowadzi do XXE ani rozwijania encji
(billion laughs, lokalny ``file://``), a jednocześnie poprawne pliki nadal
parsują się bez zmian (predefiniowane encje ``&amp;`` itd. działają).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from epubforge.core import Epub, Metadata
from epubforge.core._xml_safe import parse_untrusted

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

SENTINEL = "TOP_SECRET_SENTINEL_9f3a2b"

# Encje rekurencyjne w stylu „billion laughs" — przy rozwijaniu eksplodują
# wykładniczo. Utwardzony parser NIE może ich rozwijać.
_BILLION_LAUGHS_DTD = (
    "<!DOCTYPE package [\n"
    '<!ENTITY lol "lol">\n'
    '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
    '<!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">\n'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n'
    "]>\n"
)


def _opf(title_inner: str, doctype: str = "") -> bytes:
    """Buduje minimalny, poprawny OPF z podanym wnętrzem ``dc:title``."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}'
        f'<package xmlns="{OPF_NS}" version="3.0" unique-identifier="bookid">'
        f'<metadata xmlns:dc="{DC_NS}">'
        f'<dc:identifier id="bookid">urn:uuid:test</dc:identifier>'
        f"<dc:title>{title_inner}</dc:title>"
        f"<dc:language>en</dc:language></metadata>"
        f'<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        f'<spine><itemref idref="c1"/></spine></package>'
    ).encode()


def _external_entity_dtd(secret_path: Path) -> str:
    """DTD z encją zewnętrzną ``SYSTEM file://`` wskazującą na lokalny plik.

    Używa :meth:`Path.as_uri`, by URI był poprawny na każdej platformie
    (``file:///tmp/...`` na POSIX, ``file:///C:/...`` na Windows — surowa ścieżka
    Windows z backslashami i literą dysku nie jest poprawnym URI).
    """
    return f'<!DOCTYPE package [ <!ENTITY xxe SYSTEM "{secret_path.as_uri()}"> ]>\n'


def _title_from_opf_safe(opf_bytes: bytes) -> str:
    """Tytuł z ``from_opf`` albo ``""`` gdy parser odrzucił encję zewnętrzną.

    Oba wyniki są bezpieczne: encja nierozwinięta (pusty tytuł) LUB odrzucenie
    referencji do encji zewnętrznej (``XMLSyntaxError``). W żadnym z nich sekret
    nie jest odczytany — a właśnie to weryfikujemy.
    """
    try:
        return Metadata.from_opf(opf_bytes).title
    except etree.XMLSyntaxError:
        return ""


# ── Poprawne pliki: brak regresji ────────────────────────────────────────────


def test_predefined_entities_still_resolve() -> None:
    """Predefiniowane encje XML (``&amp;``) nadal są interpretowane."""
    root = parse_untrusted(b'<?xml version="1.0"?><r>A &amp; B &lt; C</r>')
    assert root.text == "A & B < C"


def test_from_opf_predefined_entity_roundtrip() -> None:
    """Poprawny OPF z ``&amp;`` w tytule parsuje się tak jak dawniej."""
    meta = Metadata.from_opf(_opf("Fizyka &amp; Chemia"))
    assert meta.title == "Fizyka & Chemia"


# ── Encje rekurencyjne (billion laughs) ───────────────────────────────────────


def test_recursive_entities_not_expanded_via_helper() -> None:
    """Encje rekurencyjne nie są rozwijane — brak eksplozji, tekst nierozwinięty."""
    root = parse_untrusted(_opf("&lol3;", _BILLION_LAUGHS_DTD))
    # Cała treść drzewa nie może zawierać rozwiniętego łańcucha „lollol".
    assert "lollol" not in (etree.tostring(root, encoding="unicode"))


def test_recursive_entities_not_expanded_via_from_opf() -> None:
    """``Metadata.from_opf`` nie rozwija bomby encji (i nie wisi)."""
    meta = Metadata.from_opf(_opf("&lol3;", _BILLION_LAUGHS_DTD))
    # Encja pozostaje nierozwinięta → tekst tytułu nie „puchnie".
    assert "lol" not in meta.title
    assert len(meta.title) < 100


# ── Encja zewnętrzna file:// (XXE) ────────────────────────────────────────────


def test_external_file_entity_not_read_via_from_opf(tmp_path: Path) -> None:
    """Encja ``SYSTEM file://`` nie jest dereferencjonowana — plik nie jest czytany."""
    secret = tmp_path / "secret.txt"
    secret.write_text(SENTINEL, encoding="utf-8")

    title = _title_from_opf_safe(_opf("&xxe;", _external_entity_dtd(secret)))

    assert SENTINEL not in title


def test_external_file_entity_not_read_via_epub(tmp_path: Path) -> None:
    """Otwarcie EPUB-a z encją XXE w OPF nie czyta pliku spoza archiwum."""
    secret = tmp_path / "secret.txt"
    secret.write_text(SENTINEL, encoding="utf-8")

    epub_path = tmp_path / "malicious.epub"
    container = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<container version="1.0" xmlns="{CONTAINER_NS}"><rootfiles>'
        f'<rootfile full-path="OEBPS/content.opf" '
        f'media-type="application/oebps-package+xml"/></rootfiles></container>'
    ).encode()
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", _opf("&xxe;", _external_entity_dtd(secret)))

    with Epub(epub_path) as epub:
        # Parsowanie manifestu/spine (epub.py) nie może wisieć ani czytać sekretu.
        assert epub.manifest[0].id == "c1"
        title = _title_from_opf_safe(epub.read_file(epub.opf_path))
    assert SENTINEL not in title


# ── Zachowanie błędów ─────────────────────────────────────────────────────────


def test_malformed_xml_raises_syntax_error() -> None:
    """Niepoprawny składniowo XML nadal rzuca ``XMLSyntaxError`` (strict, bez recover)."""
    with pytest.raises(etree.XMLSyntaxError):
        parse_untrusted(b"<a><b></a>")
