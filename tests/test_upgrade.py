"""Testy modernizacji EPUB 2 → EPUB 3 (``converters.upgrade``).

Zakres jednostkowy pokrywa wszystkie 7 transformacji, no-op dla EPUB 3,
``--drop-ncx`` i idempotentność. Test integracyjny (marker ``integration``)
sprawdza EpubCheck i jest pomijany bez Javy/jara.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epubforge.cli.main import main
from epubforge.converters import upgrade_to_epub3
from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted
from epubforge.core.detection import Tools
from epubforge.toc import read_toc
from epubforge.validators import Severity, run_epubcheck

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
FIXED_NOW = datetime(2026, 7, 10, 12, 30, 45, tzinfo=timezone.utc)

_CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)
_NCX = (
    '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
    '<head><meta name="dtb:uid" content="u"/></head><docTitle><text>T</text></docTitle>'
    '<navMap><navPoint id="n1" playOrder="1"><navLabel><text>Rozdział 1</text></navLabel>'
    '<content src="text/ch1.xhtml"/></navPoint></navMap></ncx>'
)
_CH = (
    '<?xml version="1.0"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
    "<head><title>c</title></head><body><h1>C</h1><p>x</p></body></html>"
)


def _build_epub2(tmp_path: Path, opf: str, *, name: str = "b.epub") -> Path:
    """Buduje minimalny EPUB 2 z podanym OPF (NCX + jeden rozdział)."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", _NCX)
        zf.writestr("OEBPS/text/ch1.xhtml", _CH)
    return path


def _opf(metadata: str = "", manifest_extra: str = "", spine: str = "", guide: str = "") -> str:
    """Składa OPF 2.0 z wstrzykiwanymi fragmentami (do testów gałęzi)."""
    meta = metadata or (
        '<dc:identifier id="bookid">urn:uuid:x</dc:identifier>'
        "<dc:title>T</dc:title><dc:language>pl</dc:language>"
    )
    spine_body = spine or '<itemref idref="ch1"/>'
    return (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:opf="http://www.idpf.org/2007/opf">{meta}</metadata>'
        '<manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        '<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        f"{manifest_extra}</manifest>"
        f'<spine toc="ncx">{spine_body}</spine>{guide}</package>'
    )


# ── Pełny zakres na fixture EPUB 2 ────────────────────────────────────────────


def test_full_scope_upgrade(epub2_epub: Path) -> None:
    """Fixture EPUB 2 przechodzi komplet transformacji do EPUB 3."""
    with Epub(epub2_epub) as epub:
        cover_before = epub.read_file("OEBPS/cover.xhtml")
        report = upgrade_to_epub3(epub, keep_ncx=True, now=FIXED_NOW)
        epub.save()

    assert report.already_epub3 is False
    with Epub(epub2_epub) as epub:
        root = parse_untrusted(epub.read_file(epub.opf_path))
        opf = epub.read_file(epub.opf_path)
        # 1. wersja pakietu
        assert root.get("version") == "3.0"
        # 2. nav.xhtml z properties="nav"
        nav = next(it for it in epub.manifest if "nav" in (it.properties or "").split())
        entries, source = read_toc(epub)
        assert source == "nav"
        assert [e.title for e in entries] == ["Rozdział pierwszy", "Rozdział drugi"]
        # 3. landmarks z guide
        nav_xml = epub.read_file("OEBPS/nav.xhtml")
        assert b'epub:type="landmarks"' in nav_xml
        assert b'epub:type="cover"' in nav_xml
        assert b'epub:type="bodymatter"' in nav_xml
        # 4. dcterms:modified (dokładny format UTC)
        assert b"2026-07-10T12:30:45Z" in opf
        assert b"dcterms:modified" in opf
        # 6. dc:date bez opf:event, tylko publikacja
        dates = root.findall(f".//{{{DC_NS}}}date")
        assert len(dates) == 1
        assert dates[0].get(f"{{{OPF_NS}}}event") is None
        assert dates[0].text == "2019-03-15"
        # guide usunięte
        assert root.find(f"{{{OPF_NS}}}guide") is None
        # NCX zostaje
        assert "OEBPS/toc.ncx" in epub.list_files()
        assert nav.href == "nav.xhtml"
        # treść nietknięta
        assert epub.read_file("OEBPS/cover.xhtml") == cover_before


def test_noop_on_epub3(sample_epub: Path) -> None:
    """Upgrade na EPUB 3 to no-op — brak zmian w buforze."""
    with Epub(sample_epub) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        pending = epub.pending_changes()

    assert report.already_epub3 is True
    assert report.transformations == []
    assert pending.modified == {}
    assert pending.deleted == frozenset()


def test_drop_ncx_cleans_manifest_and_spine(epub2_epub: Path) -> None:
    """``keep_ncx=False`` usuwa plik NCX, wpis manifestu i atrybut ``spine@toc``."""
    with Epub(epub2_epub) as epub:
        report = upgrade_to_epub3(epub, keep_ncx=False, now=FIXED_NOW)
        epub.save()

    assert any("NCX" in t for t in report.transformations)
    with Epub(epub2_epub) as epub:
        assert "OEBPS/toc.ncx" not in epub.list_files()
        root = parse_untrusted(epub.read_file(epub.opf_path))
        ncx = [it for it in epub.manifest if it.media_type == "application/x-dtbncx+xml"]
        assert ncx == []
        spine = root.find(f"{{{OPF_NS}}}spine")
        assert spine is not None
        assert spine.get("toc") is None


def test_idempotent_second_run_is_noop(epub2_epub: Path) -> None:
    """Drugi upgrade nie zmienia już pliku (wejście jest EPUB 3)."""
    with Epub(epub2_epub) as epub:
        upgrade_to_epub3(epub, now=FIXED_NOW)
        epub.save()
    first = epub2_epub.read_bytes()

    with Epub(epub2_epub) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        epub.save()
    assert report.already_epub3 is True
    assert epub2_epub.read_bytes() == first


# ── Gałęzie transformacji (inline OPF) ────────────────────────────────────────


def test_dcterms_modified_format(tmp_path: Path) -> None:
    """``dcterms:modified`` ma format ``CCYY-MM-DDThh:mm:ssZ`` (UTC, bez mikrosekund)."""
    path = _build_epub2(tmp_path, _opf())
    naive = datetime(2030, 1, 2, 3, 4, 5)  # bez tz → traktowane jako UTC
    with Epub(path) as epub:
        upgrade_to_epub3(epub, now=naive)
        opf = epub.read_file(epub.opf_path).decode()
    match = re.search(r'property="dcterms:modified">(.*?)<', opf)
    assert match is not None
    assert match.group(1) == "2030-01-02T03:04:05Z"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", match.group(1))


def test_unknown_guide_type_skipped(tmp_path: Path) -> None:
    """Nieznany typ guide jest pomijany z notą, znane trafiają do landmarks."""
    guide = (
        "<guide>"
        '<reference type="text" title="Start" href="text/ch1.xhtml"/>'
        '<reference type="wymyslony" title="X" href="text/ch1.xhtml"/>'
        "</guide>"
    )
    path = _build_epub2(tmp_path, _opf(guide=guide))
    with Epub(path) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        nav_xml = epub.read_file("OEBPS/nav.xhtml")

    assert any("wymyslony" in note for note in report.skipped)
    assert b'epub:type="bodymatter"' in nav_xml
    assert b"wymyslony" not in nav_xml


def test_unique_identifier_repaired(tmp_path: Path) -> None:
    """Gdy ``unique-identifier`` nie wskazuje id, dc:identifier dostaje id i atrybut jest naprawiony."""
    meta = (
        "<dc:identifier>urn:uuid:no-id</dc:identifier>"
        "<dc:title>T</dc:title><dc:language>pl</dc:language>"
    )
    # unique-identifier="bookid", ale dc:identifier nie ma żadnego id.
    path = _build_epub2(tmp_path, _opf(metadata=meta))
    with Epub(path) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        root = parse_untrusted(epub.read_file(epub.opf_path))

    uid = root.get("unique-identifier")
    ident = root.find(f".//{{{DC_NS}}}identifier")
    assert ident is not None
    assert ident.get("id") == uid  # atrybut wskazuje istniejący id
    assert any("unique-identifier" in t for t in report.transformations)


def test_unique_identifier_untouched_when_valid(tmp_path: Path) -> None:
    """Poprawny ``unique-identifier`` nie generuje transformacji identyfikatora."""
    path = _build_epub2(tmp_path, _opf())
    with Epub(path) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
    assert not any("unique-identifier" in t for t in report.transformations)


def test_fallback_nav_without_ncx(tmp_path: Path) -> None:
    """Bez NCX/nav upgrade tworzy awaryjny nav z pierwszego dokumentu spine."""
    path = tmp_path / "no-ncx.epub"
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="bookid">urn:uuid:x</dc:identifier>'
        "<dc:title>Bez NCX</dc:title><dc:language>pl</dc:language></metadata>"
        '<manifest><item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="ch1"/></spine></package>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/text/ch1.xhtml", _CH)

    with Epub(path) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        entries, source = read_toc(epub)

    assert report.already_epub3 is False
    assert source == "nav"
    assert [e.title for e in entries] == ["Bez NCX"]


def test_no_guide_no_landmarks(tmp_path: Path) -> None:
    """Brak ``<guide>`` → brak landmarks i brak not o pominięciach."""
    path = _build_epub2(tmp_path, _opf())  # _opf bez guide
    with Epub(path) as epub:
        report = upgrade_to_epub3(epub, now=FIXED_NOW)
        nav_xml = epub.read_file("OEBPS/nav.xhtml")
    assert report.skipped == []
    assert b"landmarks" not in nav_xml
    assert not any("landmarks" in t for t in report.transformations)


def test_content_documents_untouched(tmp_path: Path) -> None:
    """Dokumenty treści nie są modyfikowane przez upgrade."""
    path = _build_epub2(tmp_path, _opf())
    with Epub(path) as epub:
        before = epub.read_file("OEBPS/text/ch1.xhtml")
        upgrade_to_epub3(epub, now=FIXED_NOW)
        after = epub.read_file("OEBPS/text/ch1.xhtml")
    assert before == after


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_dry_run_shows_plan_without_writing(
    epub2_epub: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``upgrade --dry-run`` drukuje plan i nie zapisuje pliku."""
    before = epub2_epub.read_bytes()
    exit_code = main(["upgrade", str(epub2_epub), "--dry-run"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Plan modernizacji" in out
    assert "nav.xhtml" in out
    assert epub2_epub.read_bytes() == before  # brak zapisu


def test_cli_writes_to_output(epub2_epub: Path, tmp_path: Path) -> None:
    """``upgrade -o`` zapisuje wynik do nowego pliku (EPUB 3)."""
    out_path = tmp_path / "out.epub"
    exit_code = main(["upgrade", str(epub2_epub), "--drop-ncx", "-o", str(out_path)])
    assert exit_code == 0
    with Epub(out_path) as epub:
        root = parse_untrusted(epub.read_file(epub.opf_path))
        assert root.get("version") == "3.0"


def test_cli_already_epub3(sample_epub: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``upgrade`` na EPUB 3 wypisuje komunikat no-op."""
    exit_code = main(["upgrade", str(sample_epub)])
    assert exit_code == 0
    assert "już w formacie EPUB 3" in capsys.readouterr().out


# ── Integracja: EpubCheck (pomijana bez Javy/jara) ────────────────────────────

_JAVA = Tools.java()
_JAR = Tools.epubcheck()


@pytest.mark.integration
@pytest.mark.skipif(
    not (_JAVA.available and _JAR.available and _JAVA.path and _JAR.path),
    reason="brak Javy lub epubcheck.jar",
)
def test_epubcheck_clean_after_upgrade(epub2_epub: Path) -> None:
    """Po upgrade EpubCheck nie zgłasza błędów (warningi dopuszczalne)."""
    assert _JAVA.path is not None and _JAR.path is not None
    with Epub(epub2_epub) as epub:
        upgrade_to_epub3(epub, now=FIXED_NOW)
        epub.save()
    report = run_epubcheck(epub2_epub, _JAVA.path, _JAR.path)
    blocking = [m for m in report.messages if m.severity in (Severity.ERROR, Severity.FATAL)]
    assert blocking == [], [f"{m.code}: {m.message}" for m in blocking]
