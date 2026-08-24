"""Testy biblioteki presetów CSS (F11)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from epubforge.cli.main import main as cli_main
from epubforge.core import Epub
from epubforge.core.exceptions import MissingPublicationMemberError
from epubforge.fixers import (
    PresetError,
    apply_preset,
    get_preset,
    import_user_preset,
    list_presets,
)
from epubforge.fixers.css_presets import PRESET_ITEM_ID

_XHTML_NS = "http://www.w3.org/1999/xhtml"
_OPF_NS = "http://www.idpf.org/2007/opf"
_FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"


# ── Pomocnicze ──────────────────────────────────────────────────────────────


def _copy_fixture(tmp_path: Path) -> Path:
    """Kopiuje sample.epub do katalogu tymczasowego (do modyfikacji)."""
    target = tmp_path / "book.epub"
    target.write_bytes(_FIXTURE.read_bytes())
    return target


def _write_epub(path: Path, files: dict[str, bytes]) -> None:
    """Zapisuje minimalny EPUB (mimetype pierwszy i nieskompresowany)."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def _epub_with_existing_css(path: Path) -> None:
    """Buduje EPUB z istniejącym arkuszem ``old.css`` (do testów replace)."""
    container = (
        b'<?xml version="1.0"?>'
        b'<container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        b'unique-identifier="bookid">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="bookid">id</dc:identifier><dc:title>T</dc:title>'
        b"</metadata>"
        b"<manifest>"
        b'<item id="css" href="style/old.css" media-type="text/css"/>'
        b'<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        b"</manifest>"
        b'<spine><itemref idref="ch1"/></spine></package>'
    )
    chapter = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
        b'<link rel="stylesheet" type="text/css" href="../style/old.css"/>'
        b"</head><body><p>x</p></body></html>"
    )
    _write_epub(
        path,
        {
            "META-INF/container.xml": container,
            "OEBPS/content.opf": opf,
            "OEBPS/style/old.css": b"body { color: red; }",
            "OEBPS/text/ch1.xhtml": chapter,
        },
    )


def _head_children(xhtml: bytes) -> list[etree._Element]:
    """Zwraca dzieci ``<head>`` z pliku XHTML."""
    root = etree.fromstring(xhtml)
    head = root.find(f"{{{_XHTML_NS}}}head")
    assert head is not None
    return list(head)


# ── list / get ───────────────────────────────────────────────────────────────


def test_list_presets_has_builtins() -> None:
    """Wbudowanych presetów jest co najmniej 4."""
    presets = list_presets()
    ids = {preset.id for preset in presets}
    assert {"reader-friendly", "print-like", "dark-oled", "manga-rtl"} <= ids
    assert len(presets) >= 4


def test_get_preset_unknown_raises() -> None:
    """Nieznany preset → PresetError."""
    with pytest.raises(PresetError):
        get_preset("does-not-exist")


# ── apply: append ─────────────────────────────────────────────────────────────


def test_apply_append_adds_css_manifest_and_link(tmp_path: Path) -> None:
    """append: arkusz w archiwum, wpis w manifeście, link OSTATNI w head spine."""
    book = _copy_fixture(tmp_path)
    with Epub(book) as epub:
        apply_preset(epub, get_preset("reader-friendly"), mode="append")
        epub.save()

    with zipfile.ZipFile(book) as zf:
        names = zf.namelist()
        assert "OEBPS/styles/epubforge-preset.css" in names
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert PRESET_ITEM_ID in opf
        children = _head_children(zf.read("OEBPS/text/chapter1.xhtml"))
        last = children[-1]
        assert last.tag == f"{{{_XHTML_NS}}}link"
        assert last.get("href") == "../styles/epubforge-preset.css"


def test_apply_append_is_idempotent(tmp_path: Path) -> None:
    """Ponowna aplikacja nie dubluje wpisu w manifeście ani linku."""
    book = _copy_fixture(tmp_path)
    with Epub(book) as epub:
        apply_preset(epub, get_preset("reader-friendly"), mode="append")
        apply_preset(epub, get_preset("reader-friendly"), mode="append")
        epub.save()

    with zipfile.ZipFile(book) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert opf.count(PRESET_ITEM_ID) == 1
        chapter = zf.read("OEBPS/text/chapter1.xhtml").decode("utf-8")
        assert chapter.count("epubforge-preset.css") == 1


# ── apply: replace ─────────────────────────────────────────────────────────────


def test_apply_replace_removes_existing_stylesheets(tmp_path: Path) -> None:
    """replace: usuwa stary arkusz (plik + manifest + link) i wstawia preset."""
    book = tmp_path / "old.epub"
    _epub_with_existing_css(book)
    with Epub(book) as epub:
        apply_preset(epub, get_preset("print-like"), mode="replace")
        epub.save()

    with zipfile.ZipFile(book) as zf:
        names = zf.namelist()
        assert "OEBPS/style/old.css" not in names
        assert "OEBPS/styles/epubforge-preset.css" in names
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "old.css" not in opf
        assert PRESET_ITEM_ID in opf
        chapter = zf.read("OEBPS/text/ch1.xhtml").decode("utf-8")
        assert "old.css" not in chapter
        assert "epubforge-preset.css" in chapter


# ── zapis EPUB ─────────────────────────────────────────────────────────────────


def test_saved_epub_has_valid_structure(tmp_path: Path) -> None:
    """Po save() EPUB otwiera się, a mimetype jest pierwszy i nieskompresowany."""
    book = _copy_fixture(tmp_path)
    with Epub(book) as epub:
        apply_preset(epub, get_preset("dark-oled"), mode="append")
        epub.save()

    with zipfile.ZipFile(book) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    # Otwiera się ponownie bez błędu i ma spójny manifest.
    with Epub(book) as epub:
        assert any(item.id == PRESET_ITEM_ID for item in epub.manifest)


# ── import presetów użytkownika ───────────────────────────────────────────────


def test_import_user_preset_copies_and_lists(tmp_path: Path) -> None:
    """import kopiuje plik i pokazuje preset w list_presets(user_dir=...)."""
    user_dir = tmp_path / "presets"
    source = tmp_path / "moj-styl.css"
    source.write_text("p { line-height: 2; }", encoding="utf-8")

    preset = import_user_preset(source, user_dir=user_dir)
    assert (user_dir / "moj-styl.css").is_file()
    assert preset.id == "moj-styl"
    assert not preset.builtin

    ids = {p.id for p in list_presets(user_dir=user_dir)}
    assert "moj-styl" in ids
    assert get_preset("moj-styl", user_dir=user_dir).id == "moj-styl"


def test_import_user_preset_rejects_garbage(tmp_path: Path) -> None:
    """Plik bez poprawnego CSS (pusty / sam błąd) → PresetError."""
    user_dir = tmp_path / "presets"
    empty = tmp_path / "empty.css"
    empty.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(PresetError):
        import_user_preset(empty, user_dir=user_dir)


# ── CLI ────────────────────────────────────────────────────────────────────────


def test_cli_presets_list(capsys: pytest.CaptureFixture[str]) -> None:
    """`presets list` wypisuje wbudowane presety."""
    code = cli_main(["presets", "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "reader-friendly" in out
    assert "print-like" in out


def test_cli_fix_with_preset(tmp_path: Path) -> None:
    """`fix --preset` dokłada arkusz presetu do kopii pliku."""
    book = _copy_fixture(tmp_path)
    code = cli_main(["fix", str(book), "--preset", "reader-friendly"])
    assert code == 0
    with zipfile.ZipFile(book) as zf:
        assert "OEBPS/styles/epubforge-preset.css" in zf.namelist()


def test_apply_preset_missing_spine_member_is_not_raw_keyerror(tmp_path: Path) -> None:
    """Wiszący dokument spine nie wychodzi z apply_preset jako surowy KeyError."""
    book = tmp_path / "missing-spine.epub"
    container = (
        b'<?xml version="1.0"?>'
        b'<container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        b"<manifest>"
        b'<item id="ch1" href="text/missing.xhtml" media-type="application/xhtml+xml"/>'
        b"</manifest>"
        b'<spine><itemref idref="ch1"/></spine></package>'
    )
    _write_epub(
        book,
        {
            "META-INF/container.xml": container,
            "OEBPS/content.opf": opf,
        },
    )

    with Epub(book) as epub, pytest.raises(MissingPublicationMemberError) as caught:
        apply_preset(epub, get_preset("reader-friendly"), mode="append")

    assert not isinstance(caught.value, KeyError)
    assert "There is no item named" not in str(caught.value)
