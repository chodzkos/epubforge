"""Testy subsettingu fontów (``fixers.fonts``).

Font testowy budujemy w locie przez ``fontTools`` (kilka glifów). Cały moduł
jest pomijany, gdy ``fonttools`` nie jest zainstalowane.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from epubforge.core import Epub
from epubforge.fixers import FontSubsetOptions, subset_fonts
from epubforge.fixers import fonts as fonts_module

# Znaki treści (poza zestawem bezpieczeństwa: „ß" wymusza retencję z treści).
_CONTENT = "Aąß"
# Znaki, które font ma, ale których nie ma ani w treści, ani w zestawie bezpieczeństwa.
_DROPPABLE = [ord("中"), ord("Ж"), 0x2603]
# Znaki z zestawu bezpieczeństwa obecne w foncie (muszą przetrwać subset).
_SAFETY_IN_FONT = [ord("„"), ord("—"), ord("…"), 0x00AD, 0x00A0, ord("Z"), ord("Q")]


def _build_font(codepoints: list[int], *, flavor: str | None = None) -> bytes:
    """Buduje minimalny font TTF/WOFF z glifem-kwadratem dla każdego codepointu."""
    names = [".notdef"] + [f"g{cp:04X}" for cp in codepoints]
    builder = FontBuilder(unitsPerEm=1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({cp: f"g{cp:04X}" for cp in codepoints})

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((500, 500))
    pen.lineTo((500, 0))
    pen.closePath()
    square = pen.glyph()
    glyphs = {name: (TTGlyphPen(None).glyph() if name == ".notdef" else square) for name in names}
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(dict.fromkeys(names, (600, 0)))
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    if flavor is not None:
        builder.font.flavor = flavor
    buffer = io.BytesIO()
    builder.font.save(buffer)
    return buffer.getvalue()


_CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)
_NAV = (
    '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>t</title></head>'
    '<body><nav epub:type="toc"><ol><li><a href="ch1.xhtml">c</a></li></ol></nav></body></html>'
)


def _opf(font_href: str, font_media: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="b">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="b">u</dc:identifier><dc:title>t</dc:title>'
        "<dc:language>pl</dc:language></metadata>"
        "<manifest>"
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="css" href="s.css" media-type="text/css"/>'
        f'<item id="f1" href="{font_href}" media-type="{font_media}"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    )


def _build_epub(
    tmp_path: Path,
    font_bytes: bytes,
    *,
    font_href: str = "fonts/test.ttf",
    font_media: str = "font/ttf",
    unicode_range: bool = False,
    name: str = "book.epub",
) -> Path:
    """Buduje EPUB 3 z fontem, CSS @font-face i rozdziałem używającym _CONTENT."""
    range_decl = "unicode-range:U+0000-00FF;" if unicode_range else ""
    css = f"@font-face{{font-family:T;src:url({font_href});{range_decl}}}p{{font-family:T;}}"
    chapter = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>c</title></head><body><p>{_CONTENT}</p></body></html>"
    )
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _opf(font_href, font_media))
        zf.writestr("OEBPS/nav.xhtml", _NAV)
        zf.writestr("OEBPS/ch1.xhtml", chapter)
        zf.writestr("OEBPS/s.css", css)
        zf.writestr(f"OEBPS/{font_href}", font_bytes)
    return path


def _cmap(data: bytes) -> set[int]:
    """Zwraca zbiór codepointów z najlepszego cmap fontu."""
    return set(TTFont(io.BytesIO(data)).getBestCmap().keys())


def _all_codepoints() -> list[int]:
    """Codepointy budowanego fontu: treść + zestaw bezpieczeństwa + do wyrzucenia."""
    return sorted({ord(c) for c in _CONTENT} | set(_SAFETY_IN_FONT) | set(_DROPPABLE))


# ── Zbiór znaków ──────────────────────────────────────────────────────────────


def test_subset_keeps_content_and_safety_drops_rest(tmp_path: Path) -> None:
    """Po subsecie cmap zawiera każdy codepoint z treści + zestaw bezpieczeństwa; resztę usuwa."""
    epub_path = _build_epub(tmp_path, _build_font(_all_codepoints()))
    with Epub(epub_path) as epub:
        report = subset_fonts(epub, FontSubsetOptions())
        epub.save()

    assert report.changed_files == ["OEBPS/fonts/test.ttf"]
    with Epub(epub_path) as epub:
        cmap = _cmap(epub.read_file("OEBPS/fonts/test.ttf"))
    for char in _CONTENT:  # kryterium akceptacji: każdy codepoint z treści
        assert ord(char) in cmap
    for codepoint in _SAFETY_IN_FONT:  # „, —, …, U+00AD, U+00A0 zawsze zachowane
        assert codepoint in cmap
    for codepoint in _DROPPABLE:
        assert codepoint not in cmap


def test_extra_chars_option_retained(tmp_path: Path) -> None:
    """``extra_chars`` wymusza zachowanie wskazanych glifów mimo braku w treści."""
    epub_path = _build_epub(tmp_path, _build_font(_all_codepoints()))
    with Epub(epub_path) as epub:
        subset_fonts(epub, FontSubsetOptions(extra_chars="中"))
        epub.save()
    with Epub(epub_path) as epub:
        assert ord("中") in _cmap(epub.read_file("OEBPS/fonts/test.ttf"))


# ── Format i idempotencja ─────────────────────────────────────────────────────


def test_format_preserved_woff(tmp_path: Path) -> None:
    """Subset zachowuje format pliku (woff → woff)."""
    epub_path = _build_epub(
        tmp_path,
        _build_font(_all_codepoints(), flavor="woff"),
        font_href="fonts/test.woff",
        font_media="font/woff",
    )
    with Epub(epub_path) as epub:
        subset_fonts(epub, FontSubsetOptions())
        epub.save()
    with Epub(epub_path) as epub:
        font = TTFont(io.BytesIO(epub.read_file("OEBPS/fonts/test.woff")))
        assert font.flavor == "woff"


def test_larger_result_leaves_original_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gdy subset nie zmniejsza pliku, oryginał zostaje nietknięty (jak w Etapie 20)."""
    original_font = _build_font(_all_codepoints())
    epub_path = _build_epub(tmp_path, original_font)
    # Symulujemy „większy wynik": subsetter zwraca dane większe niż oryginał.
    monkeypatch.setattr(fonts_module, "_subset_one", lambda *a, **k: original_font + b"\x00" * 64)

    with Epub(epub_path) as epub:
        report = subset_fonts(epub, FontSubsetOptions())
        assert epub.pending_changes().modified == {}  # nic nie zapisano do bufora

    assert report.changed_files == []
    assert epub_path.read_bytes()  # plik istnieje
    with Epub(epub_path) as epub:
        assert epub.read_file("OEBPS/fonts/test.ttf") == original_font


# ── unicode-range i WOFF2/brotli ─────────────────────────────────────────────


def test_unicode_range_font_skipped(tmp_path: Path) -> None:
    """Font z @font-face zawierającym unicode-range jest pomijany (bezpieczniej)."""
    original_font = _build_font(_all_codepoints())
    epub_path = _build_epub(tmp_path, original_font, unicode_range=True)
    with Epub(epub_path) as epub:
        report = subset_fonts(epub, FontSubsetOptions())
        epub.save()

    assert report.changed_files == []
    assert any("unicode-range" in result.note for result in report.results)
    with Epub(epub_path) as epub:
        assert epub.read_file("OEBPS/fonts/test.ttf") == original_font


def test_woff2_without_brotli_warns_and_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bez brotli plik .woff2 jest pomijany z ostrzeżeniem (nie wyjątkiem)."""
    # Font budujemy jako TTF, ale rejestrujemy pod rozszerzeniem .woff2 — subset
    # pomija go po sufiksie, zanim spróbuje odczytać (brotli udajemy jako brak).
    epub_path = _build_epub(
        tmp_path,
        _build_font(_all_codepoints()),
        font_href="fonts/test.woff2",
        font_media="font/woff2",
    )
    monkeypatch.setattr(
        fonts_module.importlib.util,
        "find_spec",
        lambda name: None if name == "brotli" else object(),
    )
    with Epub(epub_path) as epub:
        report = subset_fonts(epub, FontSubsetOptions())

    assert report.changed_files == []
    assert any("brotli" in warning for warning in report.warnings)
    assert any("brotli" in result.note for result in report.results)
