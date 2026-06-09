"""Testy klasy :class:`epubforge.core.Epub`."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from epubforge.core import (
    Epub,
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"


@pytest.fixture
def epub_path(tmp_path: Path) -> Path:
    """Kopia fixture w katalogu tymczasowym (testy mogą ją modyfikować)."""
    target = tmp_path / "book.epub"
    shutil.copy2(FIXTURE, target)
    return target


# ── Odczyt ───────────────────────────────────────────────────────────────────


def test_opf_path_read_from_container(epub_path: Path) -> None:
    """opf_path pochodzi z container.xml, nie ze zgadywania."""
    with Epub(epub_path) as epub:
        assert epub.opf_path == "OEBPS/content.opf"


def test_list_files(epub_path: Path) -> None:
    """list_files zwraca wszystkie wpisy archiwum, z mimetype na pierwszym miejscu."""
    with Epub(epub_path) as epub:
        files = epub.list_files()
    assert files[0] == "mimetype"
    assert "OEBPS/content.opf" in files
    assert "OEBPS/text/chapter1.xhtml" in files


def test_read_file_content(epub_path: Path) -> None:
    """read_file zwraca surową zawartość pliku wewnętrznego."""
    with Epub(epub_path) as epub:
        data = epub.read_file("OEBPS/text/chapter1.xhtml")
    assert b"Rozdzia" in data
    assert "Zażółć gęślą jaźń".encode() in data


def test_manifest_parsing(epub_path: Path) -> None:
    """Manifest parsowany z OPF — id, href, media_type, properties."""
    with Epub(epub_path) as epub:
        manifest = epub.manifest
    ids = {item.id for item in manifest}
    assert ids == {"nav", "chapter1"}
    nav = next(item for item in manifest if item.id == "nav")
    assert nav.href == "nav.xhtml"
    assert nav.media_type == "application/xhtml+xml"
    assert nav.properties == "nav"
    chapter = next(item for item in manifest if item.id == "chapter1")
    assert chapter.properties is None


def test_spine_parsing(epub_path: Path) -> None:
    """Spine to lista idref w kolejności czytania."""
    with Epub(epub_path) as epub:
        assert epub.spine == ["chapter1"]


def test_opf_dir(epub_path: Path) -> None:
    """opf_dir zwraca katalog pliku OPF."""
    with Epub(epub_path) as epub:
        assert epub.opf_dir() == "OEBPS"


# ── Zapis i struktura ZIP ──────────────────────────────────────────────────────


def test_modify_and_save_in_place(epub_path: Path) -> None:
    """Modyfikacja pliku + save() nadpisuje oryginał nową zawartością."""
    new_html = b"<html><body><p>Zmieniono</p></body></html>"
    with Epub(epub_path) as epub:
        epub.write_file("OEBPS/text/chapter1.xhtml", new_html)
        result = epub.save()
    assert result == epub_path
    with Epub(epub_path) as epub:
        assert epub.read_file("OEBPS/text/chapter1.xhtml") == new_html


def test_saved_epub_mimetype_first_and_stored(epub_path: Path) -> None:
    """KRYTYCZNE: po zapisie mimetype jest pierwszy i nieskompresowany."""
    with Epub(epub_path) as epub:
        epub.write_file("OEBPS/text/chapter1.xhtml", b"<html/>")
        epub.save()
    with zipfile.ZipFile(epub_path) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"


def test_save_to_new_path_leaves_original(epub_path: Path, tmp_path: Path) -> None:
    """save(output_path) zapisuje kopię, nie ruszając oryginału."""
    out = tmp_path / "out.epub"
    with Epub(epub_path) as epub:
        epub.write_file("OEBPS/text/chapter1.xhtml", b"<html>nowe</html>")
        result = epub.save(out)
    assert result == out
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.read("OEBPS/text/chapter1.xhtml") == b"<html>nowe</html>"
    # Oryginalny plik niezmieniony.
    with Epub(epub_path) as epub:
        assert "Zażółć".encode() in epub.read_file("OEBPS/text/chapter1.xhtml")


def test_unchanged_files_copied_from_source(epub_path: Path) -> None:
    """Niezmienione wpisy są kopiowane ze źródła bez utraty zawartości."""
    with Epub(epub_path) as epub:
        original_opf = epub.read_file("OEBPS/content.opf")
        epub.write_file("OEBPS/text/chapter1.xhtml", b"<html/>")
        epub.save()
        assert epub.read_file("OEBPS/content.opf") == original_opf


def test_write_file_adds_new_entry(epub_path: Path) -> None:
    """write_file potrafi dodać plik, którego nie było w archiwum."""
    with Epub(epub_path) as epub:
        epub.write_file("OEBPS/text/chapter2.xhtml", b"<html>nowy</html>")
        assert "OEBPS/text/chapter2.xhtml" in epub.list_files()
        epub.save()
    with Epub(epub_path) as epub:
        assert epub.read_file("OEBPS/text/chapter2.xhtml") == b"<html>nowy</html>"


def test_save_creates_backup(epub_path: Path) -> None:
    """save() bez ścieżki tworzy backup .bak oryginału."""
    with Epub(epub_path) as epub:
        epub.write_file("OEBPS/text/chapter1.xhtml", b"<html/>")
        epub.save()
    assert epub_path.with_suffix(".epub.bak").is_file()


def test_backup_explicit(epub_path: Path) -> None:
    """backup() tworzy kopię o tej samej zawartości co oryginał."""
    with Epub(epub_path) as epub:
        backup = epub.backup()
    assert backup == epub_path.with_suffix(".epub.bak")
    assert backup.read_bytes() == epub_path.read_bytes()


def test_modifying_opf_invalidates_manifest_cache(epub_path: Path) -> None:
    """Po nadpisaniu OPF manifest jest parsowany na nowo."""
    new_opf = (
        b'<?xml version="1.0"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf">'
        b"<manifest>"
        b'<item id="only" href="x.xhtml" media-type="application/xhtml+xml"/>'
        b"</manifest><spine/></package>"
    )
    with Epub(epub_path) as epub:
        assert len(epub.manifest) == 2
        epub.write_file("OEBPS/content.opf", new_opf)
        assert [item.id for item in epub.manifest] == ["only"]


# ── Obsługa błędów ─────────────────────────────────────────────────────────────


def test_open_missing_file(tmp_path: Path) -> None:
    """Brak pliku → InvalidEpubError."""
    with pytest.raises(InvalidEpubError):
        Epub(tmp_path / "nie_ma.epub").open()


def test_open_corrupt_zip(tmp_path: Path) -> None:
    """Uszkodzony ZIP → InvalidEpubError."""
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"to nie jest zip")
    with pytest.raises(InvalidEpubError):
        Epub(bad).open()


def test_open_missing_container(tmp_path: Path) -> None:
    """ZIP bez META-INF/container.xml → OpfNotFoundError."""
    no_container = tmp_path / "no_container.epub"
    with zipfile.ZipFile(no_container, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip")
        zf.writestr("hello.txt", b"hi")
    with pytest.raises(OpfNotFoundError):
        Epub(no_container).open()


def test_invalid_container_xml(tmp_path: Path) -> None:
    """Niepoprawny container.xml → OpfNotFoundError przy odczycie opf_path."""
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip")
        zf.writestr("META-INF/container.xml", b"<container><bez></container>")
    with Epub(broken) as epub, pytest.raises(OpfNotFoundError):
        _ = epub.opf_path


def test_operations_require_open(epub_path: Path) -> None:
    """Operacje na zamkniętym EPUB-ie → EpubNotOpenError."""
    epub = Epub(epub_path)
    with pytest.raises(EpubNotOpenError):
        epub.read_file("mimetype")
    with pytest.raises(EpubNotOpenError):
        epub.write_file("a", b"b")
    with pytest.raises(EpubNotOpenError):
        epub.list_files()
    with pytest.raises(EpubNotOpenError):
        epub.save()


def test_open_and_close_idempotent(epub_path: Path) -> None:
    """Wielokrotne open()/close() nie rzuca i nie psuje stanu."""
    epub = Epub(epub_path)
    epub.open()
    epub.open()  # drugie wywołanie bez efektu
    assert epub.opf_path == "OEBPS/content.opf"
    epub.close()
    epub.close()  # bezpieczne na zamkniętym
