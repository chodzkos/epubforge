"""Testy generatora, writera/readera i naprawy spisu treści (na fixture toc_epub)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from epubforge.core import Epub
from epubforge.toc import (
    TocEntry,
    generate_toc,
    iter_entries,
    read_toc,
    repair_toc,
    validate_toc,
    write_toc,
)

_CONTAINER = b"""<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>"""


def _write_minimal_toc_epub(
    path: Path,
    *,
    manifest: str,
    members: dict[str, bytes],
) -> Path:
    """Buduje mały EPUB do testów uszkodzonych odwołań TOC."""
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test</dc:title><dc:identifier>id</dc:identifier></metadata>"
        f"<manifest>{manifest}</manifest><spine/></package>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER)
        archive.writestr("OEBPS/content.opf", opf)
        for internal_path, data in members.items():
            archive.writestr(internal_path, data)
    return path


# ── Generator ─────────────────────────────────────────────────────────────--


def test_generate_tree_structure(toc_epub: Path) -> None:
    """h1 to korzeń, h2 to dzieci; osierocony h3 podciągnięty pod h1; ch3 pominięty."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
    assert [e.title for e in entries] == ["Rozdział pierwszy", "Rozdział drugi"]
    assert [c.title for c in entries[0].children] == ["Wstęp do tematu", "Rozdział drugi akt"]
    # ch2: osierocony h3 staje się dzieckiem h1 (poziom wyżej).
    assert [c.title for c in entries[1].children] == ["Podrozdział osierocony"]


def test_generate_title_joins_em_and_keeps_polish(toc_epub: Path) -> None:
    """Tytuł z <em> jest sklejony i zachowuje polskie znaki."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
    assert entries[0].children[1].title == "Rozdział drugi akt"
    assert entries[0].title == "Rozdział pierwszy"


def test_generate_first_heading_without_fragment(toc_epub: Path) -> None:
    """Pierwszy nagłówek pliku linkuje bez fragmentu, kolejne z fragmentem."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
    assert entries[0].href == "OEBPS/text/ch1.xhtml"
    assert "#" in entries[0].children[0].href


def test_generate_injects_unique_ids(toc_epub: Path) -> None:
    """Brakujące id są wstrzykiwane i unikalne w obrębie pliku."""
    with Epub(toc_epub) as epub:
        generate_toc(epub, max_level=3)
        ch1 = epub.read_file("OEBPS/text/ch1.xhtml").decode("utf-8")
    assert ch1.count('id="efh-0001"') == 1
    assert 'id="efh-0002"' in ch1


def test_generate_is_idempotent(toc_epub: Path) -> None:
    """Drugi przebieg nie modyfikuje już plików (id istnieją)."""
    with Epub(toc_epub) as epub:
        generate_toc(epub, max_level=3)
        first = epub.read_file("OEBPS/text/ch1.xhtml")
        generate_toc(epub, max_level=3)
        second = epub.read_file("OEBPS/text/ch1.xhtml")
    assert first == second


def test_generate_preserves_doctype(toc_epub: Path) -> None:
    """Po wstrzyknięciu id zachowana jest deklaracja XML i DOCTYPE."""
    with Epub(toc_epub) as epub:
        generate_toc(epub, max_level=3)
        ch1 = epub.read_file("OEBPS/text/ch1.xhtml").decode("utf-8")
    assert ch1.startswith("<?xml")
    assert "<!DOCTYPE html>" in ch1


def test_generate_skips_files_without_headings(toc_epub: Path) -> None:
    """Plik bez nagłówków (ch3) nie pojawia się w spisie."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
    hrefs = [e.href for e in iter_entries(entries)]
    assert all("ch3" not in href for href in hrefs)


# ── Writer → Reader roundtrip ─────────────────────────────────────────────--


def test_roundtrip_nav_and_ncx(toc_epub: Path) -> None:
    """Po write_toc + save spis czyta się z powrotem identycznie (nav)."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
        write_toc(epub, entries)
        epub.save()
    with Epub(toc_epub) as epub:
        read_entries, source = read_toc(epub)
    assert source == "nav"
    assert [e.title for e in read_entries] == ["Rozdział pierwszy", "Rozdział drugi"]
    assert [c.title for c in read_entries[0].children] == ["Wstęp do tematu", "Rozdział drugi akt"]


def test_writer_adds_nav_property_and_spine_toc(toc_epub: Path) -> None:
    """nav ma properties=nav w manifeście; ncx jest wpięty przez spine@toc."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
        write_toc(epub, entries)
        epub.save()
    with Epub(toc_epub) as epub:
        nav_item = next(i for i in epub.manifest if "nav" in (i.properties or "").split())
        assert nav_item is not None
        ncx_item = next(i for i in epub.manifest if i.media_type == "application/x-dtbncx+xml")
        opf = epub.read_file(epub.opf_path).decode("utf-8")
    assert ncx_item is not None
    spine_open_tag = opf.split("<spine", 1)[1].split(">", 1)[0]
    assert "toc=" in spine_open_tag


def test_writer_creates_nav_when_absent(toc_epub: Path) -> None:
    """Gdy nav nie istnieje, writer tworzy nowy dokument + wpis properties=nav."""
    from epubforge.toc import TocEntry

    with Epub(toc_epub) as epub:
        # Usuń istniejący nav (plik + wpis manifestu), by wymusić utworzenie nowego.
        epub.delete_file("OEBPS/nav.xhtml")
        opf = (
            epub.read_file(epub.opf_path)
            .decode("utf-8")
            .replace(
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                "",
            )
        )
        epub.write_file(epub.opf_path, opf.encode("utf-8"))
        write_toc(epub, [TocEntry("Rozdział", "OEBPS/text/ch1.xhtml")], write_ncx=False)
        epub.save()
    with Epub(toc_epub) as epub:
        nav_item = next(i for i in epub.manifest if "nav" in (i.properties or "").split())
        entries, source = read_toc(epub)
    assert nav_item is not None
    assert source == "nav"
    assert [e.title for e in entries] == ["Rozdział"]


def test_saved_epub_is_healthy(toc_epub: Path) -> None:
    """Po zapisie mimetype jest pierwszy i nieskompresowany (ZIP_STORED)."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
        write_toc(epub, entries)
        epub.save()
    with zipfile.ZipFile(toc_epub) as zf:
        infos = zf.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


def test_ncx_only_roundtrip(toc_epub: Path) -> None:
    """Gdy nav nie istnieje, spis czyta się z ncx (fallback)."""
    with Epub(toc_epub) as epub:
        entries = generate_toc(epub, max_level=3)
        write_toc(epub, entries, write_nav=False, write_ncx=True)
        # usuń wpis nav z manifestu + plik, żeby wymusić fallback do ncx
        epub.delete_file("OEBPS/nav.xhtml")
        opf = epub.read_file(epub.opf_path).decode("utf-8")
        opf = opf.replace(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            "",
        )
        epub.write_file(epub.opf_path, opf.encode("utf-8"))
        epub.save()
    with Epub(toc_epub) as epub:
        read_entries, source = read_toc(epub)
    assert source == "ncx"
    assert [e.title for e in read_entries] == ["Rozdział pierwszy", "Rozdział drugi"]


def test_nav_fragment_only_targets_navigation_document(tmp_path: Path) -> None:
    """Sam fragment w nav wskazuje nav.xhtml, a nie jego katalog."""
    nav = b"""<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"><body>
      <nav id="chapter" epub:type="toc"><ol><li>
      <a href="#chapter">Tutaj</a>
      </li></ol></nav></body></html>"""
    path = _write_minimal_toc_epub(
        tmp_path / "nav-fragment.epub",
        manifest=(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        ),
        members={"OEBPS/nav.xhtml": nav},
    )

    with Epub(path) as epub:
        entries, source = read_toc(epub)
        problems = validate_toc(epub, entries)

    assert source == "nav"
    assert [entry.href for entry in entries] == ["OEBPS/nav.xhtml#chapter"]
    assert problems == []


def test_ncx_fragment_only_targets_ncx_document(tmp_path: Path) -> None:
    """Sam fragment w NCX wskazuje toc.ncx, a nie jego katalog."""
    ncx = b"""<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
      <navMap><navPoint id="chapter"><navLabel><text>Tutaj</text></navLabel>
      <content src="#chapter"/></navPoint></navMap></ncx>"""
    path = _write_minimal_toc_epub(
        tmp_path / "ncx-fragment.epub",
        manifest=('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'),
        members={"OEBPS/toc.ncx": ncx},
    )

    with Epub(path) as epub:
        entries, source = read_toc(epub)
        problems = validate_toc(epub, entries)

    assert source == "ncx"
    assert [entry.href for entry in entries] == ["OEBPS/toc.ncx#chapter"]
    assert problems == []


def test_write_toc_recreates_dangling_manifest_nav(tmp_path: Path) -> None:
    """Zapis TOC naprawia brakujący nav zamiast ujawniać surowy KeyError."""
    path = _write_minimal_toc_epub(
        tmp_path / "missing-nav.epub",
        manifest=(
            '<item id="chapter" href="text/ch.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        ),
        members={"OEBPS/text/ch.xhtml": b'<html xmlns="http://www.w3.org/1999/xhtml"/>'},
    )

    with Epub(path) as epub:
        write_toc(
            epub,
            [TocEntry("Rozdział", "OEBPS/text/ch.xhtml")],
            write_ncx=False,
        )
        entries, source = read_toc(epub)
        nav_items = [item for item in epub.manifest if "nav" in (item.properties or "").split()]
        pending = epub.pending_changes()

    assert source == "nav"
    assert [entry.href for entry in entries] == ["OEBPS/text/ch.xhtml"]
    assert [item.id for item in nav_items] == ["nav"]
    assert "OEBPS/nav.xhtml" in pending.modified


def test_write_toc_recreates_logically_deleted_nav(tmp_path: Path) -> None:
    """Nav usunięty w overlayu nie jest uznawany za istniejący przez source ZIP."""
    nav = b"""<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"><body>
      <nav epub:type="toc"><ol/></nav></body></html>"""
    path = _write_minimal_toc_epub(
        tmp_path / "deleted-nav.epub",
        manifest=(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        ),
        members={"OEBPS/nav.xhtml": nav},
    )

    with Epub(path) as epub:
        epub.delete_file("OEBPS/nav.xhtml")
        write_toc(epub, [], write_ncx=False)
        pending = epub.pending_changes()

    assert "OEBPS/nav.xhtml" in pending.modified
    assert "OEBPS/nav.xhtml" not in pending.deleted


# ── Repair ────────────────────────────────────────────────────────────────--


def test_validate_detects_dead_href(toc_epub: Path) -> None:
    """validate_toc wykrywa martwy plik docelowy w istniejącym nav."""
    with Epub(toc_epub) as epub:
        entries, _source = read_toc(epub)
        problems = validate_toc(epub, entries)
    assert any("missing.xhtml" in p.href for p in problems)


def test_validate_detects_bad_fragment(toc_epub: Path) -> None:
    """validate_toc wykrywa nieistniejący fragment przy poprawnym pliku."""
    from epubforge.toc import TocEntry

    entries = [TocEntry("Zły fragment", "OEBPS/text/ch1.xhtml#nie-ma")]
    with Epub(toc_epub) as epub:
        problems = validate_toc(epub, entries)
    assert len(problems) == 1
    assert "Fragment" in problems[0].reason


def test_repair_removes_dead_and_pulls_children(toc_epub: Path) -> None:
    """repair_toc usuwa martwy wpis i podciąga jego dzieci na miejsce rodzica."""
    from epubforge.toc import TocEntry

    child = TocEntry("Żywe dziecko", "OEBPS/text/ch1.xhtml")
    dead = TocEntry("Martwy", "OEBPS/text/missing.xhtml", [child])
    entries = [dead]
    with Epub(toc_epub) as epub:
        repaired, removed = repair_toc(epub, entries)
    assert [e.title for e in removed] == ["Martwy"]
    assert [e.title for e in repaired] == ["Żywe dziecko"]  # dziecko podciągnięte
