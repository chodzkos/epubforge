"""Testy fixera typografii (:mod:`epubforge.fixers.typography`)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from epubforge.cli.main import main
from epubforge.core import Epub
from epubforge.fixers import TypographyOptions, fix_typography

NBSP = " "
_CHAPTER_PATH = "OEBPS/text/chapter1.xhtml"


def _build_epub(tmp_path: Path, body: str, *, doctype: str = "") -> Path:
    """Tworzy minimalny EPUB z jednym XHTML (opcjonalnie z DOCTYPE)."""
    epub_path = tmp_path / "book.epub"
    container = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><manifest>'
        b'<item id="chapter1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>'
        b'</manifest><spine><itemref idref="chapter1"/></spine></package>'
    )
    chapter = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}'
        f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head>'
        f"<body>{body}</body></html>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        zf.writestr(_CHAPTER_PATH, chapter.encode(), zipfile.ZIP_DEFLATED)
    return epub_path


def _fix(tmp_path: Path, body: str, options: TypographyOptions, *, doctype: str = "") -> str:
    """Uruchamia fixer na jednym akapicie i zwraca zawartość ``<body>``."""
    epub_path = _build_epub(tmp_path, body, doctype=doctype)
    with Epub(epub_path) as epub:
        fix_typography(epub, options)
        html = epub.read_file(_CHAPTER_PATH).decode()
    return html.split("<body>", 1)[1].split("</body>", 1)[0]


# ── Cudzysłowy ────────────────────────────────────────────────────────────────


def test_quotes_polish(tmp_path: Path) -> None:
    """Proste cudzysłowy → polska para „…”."""
    body = _fix(
        tmp_path,
        '<p>Powiedział "cześć".</p>',
        TypographyOptions(fix_dashes=False, fix_ellipsis=False, nbsp_single_letters=False),
    )
    assert body == "<p>Powiedział „cześć”.</p>"


def test_quotes_english(tmp_path: Path) -> None:
    """Wariant en → “…”."""
    body = _fix(
        tmp_path,
        '<p>He said "hi".</p>',
        TypographyOptions(language="en", nbsp_single_letters=False),
    )
    assert body == "<p>He said “hi”.</p>"


def test_quotes_german(tmp_path: Path) -> None:
    """Wariant de → „…“ (zamykający to lewy górny)."""
    body = _fix(
        tmp_path,
        '<p>Er sagte "ja".</p>',
        TypographyOptions(language="de", nbsp_single_letters=False),
    )
    assert body == "<p>Er sagte „ja“.</p>"


def test_quotes_pair_across_em(tmp_path: Path) -> None:
    """Para cudzysłowów domyka się przez granicę ``<em>`` (stan przez tagi)."""
    body = _fix(
        tmp_path,
        '<p>Rzekł "<em>cześć</em>" i poszedł.</p>',
        TypographyOptions(fix_dashes=False, nbsp_single_letters=False),
    )
    assert body == "<p>Rzekł „<em>cześć</em>” i poszedł.</p>"


def test_single_quote_apostrophe(tmp_path: Path) -> None:
    """Apostrof w słowie (kontekst zamykający) → prawy pojedynczy ’."""
    body = _fix(
        tmp_path,
        "<p>It's fine.</p>",
        TypographyOptions(language="en", nbsp_single_letters=False),
    )
    assert body == "<p>It’s fine.</p>"


# ── Pauzy / dywizy ────────────────────────────────────────────────────────────


def test_dialog_dash_at_paragraph_start(tmp_path: Path) -> None:
    """Dywiz na początku akapitu → pauza dialogowa „— "."""
    body = _fix(
        tmp_path,
        "<p>- Cześć.</p>",
        TypographyOptions(fix_quotes=False, nbsp_single_letters=False),
    )
    assert body == "<p>— Cześć.</p>"


def test_interword_dash(tmp_path: Path) -> None:
    """Dywiz między słowami (ze spacjami) → pauza; spacje zachowane."""
    body = _fix(
        tmp_path,
        "<p>tak - nie</p>",
        TypographyOptions(fix_quotes=False, nbsp_single_letters=False),
    )
    assert body == "<p>tak — nie</p>"


def test_dash_inside_word_untouched(tmp_path: Path) -> None:
    """Łącznik wewnątrz słowa (biało-czerwony) NIE jest ruszany."""
    body = _fix(
        tmp_path,
        "<p>flaga biało-czerwona</p>",
        TypographyOptions(fix_quotes=False, nbsp_single_letters=False),
    )
    assert body == "<p>flaga biało-czerwona</p>"


# ── Wielokropek ───────────────────────────────────────────────────────────────


def test_ellipsis(tmp_path: Path) -> None:
    """Trzy (i więcej) kropki → jeden znak wielokropka."""
    body = _fix(
        tmp_path,
        "<p>No... i coś..... tam</p>",
        TypographyOptions(fix_quotes=False, fix_dashes=False, nbsp_single_letters=False),
    )
    assert body == "<p>No… i coś… tam</p>"


# ── Twarde spacje ─────────────────────────────────────────────────────────────


def test_nbsp_single_letters(tmp_path: Path) -> None:
    """pl: samotne spójniki dostają twardą spację; dłuższe słowa nie."""
    body = _fix(
        tmp_path,
        "<p>Idę z Adamem i do domu</p>",
        TypographyOptions(fix_quotes=False, fix_dashes=False),
    )
    assert body == f"<p>Idę z{NBSP}Adamem i{NBSP}do domu</p>"


def test_nbsp_single_letters_skipped_for_non_polish(tmp_path: Path) -> None:
    """Reguła sierot działa tylko dla pl — dla en jest pomijana."""
    body = _fix(
        tmp_path,
        "<p>a to jest test</p>",
        TypographyOptions(language="en", fix_quotes=False, fix_dashes=False),
    )
    assert NBSP not in body


def test_nbsp_numbers_units_off_by_default(tmp_path: Path) -> None:
    """Domyślnie liczby+jednostki NIE dostają twardej spacji."""
    body = _fix(
        tmp_path,
        "<p>10 km stąd</p>",
        TypographyOptions(fix_quotes=False, fix_dashes=False, nbsp_single_letters=False),
    )
    assert body == "<p>10 km stąd</p>"


def test_nbsp_numbers_units_when_enabled(tmp_path: Path) -> None:
    """Po włączeniu: liczba+jednostka i „XX w." dostają twardą spację."""
    body = _fix(
        tmp_path,
        "<p>10 km w XX w.</p>",
        TypographyOptions(
            fix_quotes=False,
            fix_dashes=False,
            nbsp_single_letters=False,
            nbsp_numbers_units=True,
        ),
    )
    assert body == f"<p>10{NBSP}km w XX{NBSP}w.</p>"


# ── Nietykalne obszary ────────────────────────────────────────────────────────


def test_code_and_pre_untouched(tmp_path: Path) -> None:
    """Zawartość ``code``/``pre`` (i atrybuty) nie jest modyfikowana."""
    body = _fix(
        tmp_path,
        '<p title="a - b">Kod <code>x - y "z"</code> i <pre>a... b</pre></p>',
        TypographyOptions(),
    )
    assert '<code>x - y "z"</code>' in body
    assert "<pre>a... b</pre>" in body
    assert 'title="a - b"' in body  # atrybut nietknięty


def test_style_tag_untouched(tmp_path: Path) -> None:
    """Zawartość ``<style>`` nie jest ruszana (nie psujemy CSS)."""
    epub_path = _build_epub(
        tmp_path,
        '<p>"tekst"</p>',
    )
    # dołóż <style> ze znakami, które fixer mógłby zepsuć
    with Epub(epub_path) as epub:
        raw = epub.read_file(_CHAPTER_PATH).decode()
        raw = raw.replace("<head>", '<head><style>p::after{content:"..."}</style>')
        epub.write_file(_CHAPTER_PATH, raw.encode())
        epub.save()
    with Epub(epub_path) as epub:
        fix_typography(epub, TypographyOptions(nbsp_single_letters=False))
        html = epub.read_file(_CHAPTER_PATH).decode()
    assert 'content:"..."' in html  # CSS nietknięty
    assert "„tekst”" in html  # ale tekst poprawiony


# ── Kombinacje / idempotentność / raport ──────────────────────────────────────


def test_all_rules_combined(tmp_path: Path) -> None:
    """Wszystkie reguły naraz na jednym akapicie."""
    body = _fix(
        tmp_path,
        '<p>- Powiedział "cześć"... z Adamem - i poszedł.</p>',
        TypographyOptions(),
    )
    # „i" jest też samotnym spójnikiem → dostaje twardą spację.
    assert body == f"<p>— Powiedział „cześć”… z{NBSP}Adamem — i{NBSP}poszedł.</p>"


def test_idempotent(tmp_path: Path) -> None:
    """Drugi przebieg nie wprowadza żadnych zmian."""
    epub_path = _build_epub(tmp_path, '<p>- "cześć"... z Adamem - tak.</p>')
    options = TypographyOptions()
    with Epub(epub_path) as epub:
        first = fix_typography(epub, options)
        epub.save()
    with Epub(epub_path) as epub:
        second = fix_typography(epub, options)
    assert first.total_changes > 0
    assert second.total_changes == 0


def test_report_counts(tmp_path: Path) -> None:
    """Raport podaje liczby podmian per reguła i sumarycznie."""
    epub_path = _build_epub(tmp_path, '<p>- "a"... z Adamem</p>')
    with Epub(epub_path) as epub:
        report = fix_typography(epub, TypographyOptions())
    totals = report.totals()
    assert totals["fix_quotes"] == 2
    assert totals["fix_dashes"] == 1
    assert totals["fix_ellipsis"] == 1
    # „a" trafia w cudzysłów („a”) — po nim jest ”, nie spacja — więc bez nbsp;
    # twardą spację dostaje tylko „z Adamem".
    assert totals["nbsp_single_letters"] == 1
    assert report.total_changes == 5
    assert report.changed_files == [_CHAPTER_PATH]


def test_doctype_preserved_after_roundtrip(tmp_path: Path) -> None:
    """DOCTYPE przetrwa round-trip (parsowanie + serializacja)."""
    epub_path = _build_epub(tmp_path, '<p>"test"</p>', doctype="<!DOCTYPE html>")
    with Epub(epub_path) as epub:
        fix_typography(epub, TypographyOptions(nbsp_single_letters=False))
        html = epub.read_file(_CHAPTER_PATH).decode()
    assert "<!DOCTYPE html>" in html
    assert "„test”" in html


def test_no_changes_leaves_file_untouched(tmp_path: Path) -> None:
    """Brak podmian → plik nie jest przepisywany (raport pusty)."""
    epub_path = _build_epub(tmp_path, "<p>Czysty tekst bez typografii.</p>")
    original = _read_chapter(epub_path)
    with Epub(epub_path) as epub:
        report = fix_typography(epub, TypographyOptions())
        epub.save()
    assert report.total_changes == 0
    assert _read_chapter(epub_path) == original


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_typo(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """CLI ``epubforge typo`` poprawia plik i wypisuje raport."""
    epub_path = _build_epub(tmp_path, '<p>- "cześć"... z Adamem</p>')
    exit_code = main(["typo", str(epub_path), "--lang", "pl"])
    assert exit_code == 0
    with Epub(epub_path) as epub:
        html = epub.read_file(_CHAPTER_PATH).decode()
    assert "„cześć”" in html
    assert "—" in html
    captured = capsys.readouterr()
    assert "podmian" in captured.out


def _read_chapter(epub_path: Path) -> bytes:
    """Czyta surowe bajty rozdziału z EPUB-a."""
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(_CHAPTER_PATH)
