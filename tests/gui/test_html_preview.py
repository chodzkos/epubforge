"""Testy podglądu XHTML: czysta funkcja inline_images + integracja w EditorTab."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor
from pytestqt.qtbot import QtBot

from epubforge.core import Epub, Tool
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.tabs import editor_preview
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.tabs.editor_preview import _PAGE_HTML
from epubforge.gui.widgets.html_preview import _PAPER_BG, _epub_image_resolver, inline_images

pytestmark = pytest.mark.gui

# 1x1 PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f9b0000000049454e44ae426082"
)


def _bmp(width: int, height: int) -> bytes:
    """Buduje mały poprawny raster BMP o kontrolowanym koszcie dekodu."""
    pixel_bytes = width * height * 4
    header_size = 14 + 40
    file_header = b"BM" + struct.pack("<IHHI", header_size + pixel_bytes, 0, 0, header_size)
    dib_header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0, pixel_bytes, 0, 0, 0, 0)
    return file_header + dib_header + b"\x00" * pixel_bytes


# ── inline_images (czyste) ──────────────────────────────────────────────────--


def test_inline_images_embeds_small_image_as_data_uri() -> None:
    """Mały obrazek o względnym src trafia jako data: URI z bajtów."""
    out = inline_images('<html><body><img src="img/p.png"/></body></html>', lambda _s: _PNG)
    assert "data:image/png;base64," in out
    assert "img/p.png" not in out


def test_inline_images_oversized_becomes_placeholder() -> None:
    """Obraz > limitu jest zastępowany placeholderem z nazwą, nie base64."""
    big = b"Y" * (4 * 1024 * 1024)
    out = inline_images(
        '<html><body><img src="img/big.png"/></body></html>', lambda _s: big, max_bytes=3_000_000
    )
    assert "data:" not in out
    assert "big.png" in out


def test_inline_images_rejects_small_encoded_huge_raster() -> None:
    """Fallback nie przekazuje QTextDocument małego pliku deklarującego 81 MP."""
    header_size = 54
    bmp = (
        b"BM"
        + struct.pack("<IHHI", header_size, 0, 0, header_size)
        + struct.pack("<IiiHHIIiiII", 40, 9_000, 9_000, 1, 32, 0, 0, 0, 0, 0, 0)
    )
    out = inline_images('<html><body><img src="img/huge.bmp"/></body></html>', lambda _s: bmp)
    assert "data:" not in out
    assert "huge.bmp" in out


def test_inline_images_degrades_when_distinct_images_exceed_aggregate_budget() -> None:
    """Dwa legalne rastry nie mogą łącznie przekroczyć budżetu dokumentu fallback."""
    images = {"a.bmp": _bmp(2, 1), "b.bmp": _bmp(2, 1)}
    out = inline_images(
        '<html><body><img src="a.bmp"/><img src="b.bmp"/></body></html>',
        images.__getitem__,
        max_decoded_bytes=8,
    )

    assert out.count("data:image/bmp;base64,") == 1
    assert "[obraz: b.bmp]" in out


def test_inline_images_accepts_single_legal_image_at_aggregate_limit() -> None:
    """Budżet agregatu nie obniża istniejącego guarda pojedynczego obrazu."""
    out = inline_images(
        '<html><body><img src="a.bmp"/></body></html>',
        lambda _src: _bmp(2, 1),
        max_decoded_bytes=8,
    )

    assert out.count("data:image/bmp;base64,") == 1


def test_inline_images_accepts_distinct_images_below_aggregate_budget() -> None:
    """Dwa unikalne rastry mieszczące się w sumie są osadzane."""
    images = {"a.bmp": _bmp(1, 1), "b.bmp": _bmp(1, 1)}
    out = inline_images(
        '<html><body><img src="a.bmp"/><img src="b.bmp"/></body></html>',
        images.__getitem__,
        max_decoded_bytes=8,
    )

    assert out.count("data:image/bmp;base64,") == 2


def test_inline_images_counts_duplicate_and_alias_references_once() -> None:
    """Surowe aliasy tego samego membera rezerwują jeden zdekodowany raster."""
    calls: list[str] = []

    def resolve(src: str) -> bytes:
        calls.append(src)
        return _bmp(2, 1)

    out = inline_images(
        '<html><body><img src="img.bmp"/><img src="./img.bmp"/>'
        '<img src="folder/../img.bmp"/></body></html>',
        resolve,
        max_decoded_bytes=8,
    )

    assert out.count("data:image/bmp;base64,") == 3
    assert calls == ["img.bmp"]


def test_inline_images_uses_provider_member_identity_for_unicode_aliases(tmp_path: Path) -> None:
    """NFC/NFD wskazujące ten sam member rezerwują jeden raster fallbacku."""
    book = tmp_path / "fallback-unicode-alias.epub"
    _make_html_epub(book)
    nfd_path = "OEBPS/img/cafe\u0301.bmp"
    nfc_path = "OEBPS/img/café.bmp"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(nfd_path, _bmp(2, 1))
    with Epub(book) as epub:
        generation = PreviewSession.create(epub).advance(epub, "OEBPS/ch.xhtml", {})
        provider = generation.resource_provider
        calls: list[str] = []
        base_resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)

        def resolve(src: str) -> bytes | None:
            calls.append(src)
            return base_resolver(src)

        out = inline_images(
            f'<html><body><img src="img/{nfc_path.rsplit("/", 1)[-1]}"/>'
            f'<img src="img/{nfd_path.rsplit("/", 1)[-1]}"/></body></html>',
            resolve,
            base_path="OEBPS/ch.xhtml",
            max_decoded_bytes=8,
            identity_resolver=provider.canonical_path,
        )

    assert out.count("data:image/bmp;base64,") == 2
    assert calls == [f"img/{nfc_path.rsplit('/', 1)[-1]}"]


def test_inline_images_keeps_two_exact_unicode_members_distinct(tmp_path: Path) -> None:
    """Exact NFC i NFD istniejące równocześnie mają osobne rezerwacje budżetu."""
    book = tmp_path / "fallback-unicode-distinct.epub"
    _make_html_epub(book)
    nfc_path = "OEBPS/img/café.bmp"
    nfd_path = "OEBPS/img/cafe\u0301.bmp"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(nfc_path, _bmp(2, 1))
        archive.writestr(nfd_path, _bmp(1, 2))
    with Epub(book) as epub:
        generation = PreviewSession.create(epub).advance(epub, "OEBPS/ch.xhtml", {})
        provider = generation.resource_provider
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)
        out = inline_images(
            '<html><body><img src="img/café.bmp"/><img src="img/cafe\u0301.bmp"/></body></html>',
            resolver,
            base_path="OEBPS/ch.xhtml",
            max_decoded_bytes=8,
            identity_resolver=provider.canonical_path,
        )

    assert out.count("data:image/bmp;base64,") == 1
    assert "[obraz: café.bmp]" in out


def test_inline_images_budget_resets_for_each_document_generation() -> None:
    """Nowy render nie dziedziczy rezerwacji poprzedniego QTextDocument."""
    html = '<html><body><img src="img.bmp"/></body></html>'

    first = inline_images(html, lambda _src: _bmp(2, 1), max_decoded_bytes=8)
    second = inline_images(html, lambda _src: _bmp(2, 1), max_decoded_bytes=8)

    assert "data:image/bmp;base64," in first
    assert "data:image/bmp;base64," in second


def test_generation_resolver_uses_dirty_image_instead_of_pending_or_source(tmp_path: Path) -> None:
    """Fallback liczy i osadza winnera dirty, bez doliczania starszych wersji."""
    book = tmp_path / "fallback-overlay.epub"
    _make_html_epub(book)
    image_path = "OEBPS/img/overlay.bmp"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(image_path, _bmp(3, 1))
    with Epub(book) as epub:
        epub.write_file(image_path, _bmp(2, 1))
        pending = epub.pending_changes()
        generation = PreviewSession.create(epub).advance(
            epub,
            "OEBPS/ch.xhtml",
            {image_path: _bmp(1, 1)},
            pending=pending,
        )
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)
        out = inline_images(
            '<html><body><img src="img/overlay.bmp"/></body></html>',
            resolver,
            base_path="OEBPS/ch.xhtml",
            max_decoded_bytes=4,
        )

    assert "data:image/bmp;base64," in out


def test_generation_resolver_uses_frozen_pending_image(tmp_path: Path) -> None:
    """Pending winner jest zamrożony w generacji i nie zmienia się po późniejszym write."""
    book = tmp_path / "fallback-pending.epub"
    _make_html_epub(book)
    image_path = "OEBPS/img/pending.bmp"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(image_path, _bmp(3, 1))
    with Epub(book) as epub:
        epub.write_file(image_path, _bmp(1, 1))
        generation = PreviewSession.create(epub).advance(
            epub,
            "OEBPS/ch.xhtml",
            {},
            pending=epub.pending_changes(),
        )
        epub.write_file(image_path, _bmp(2, 1))
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)
        out = inline_images(
            '<html><body><img src="img/pending.bmp"/></body></html>',
            resolver,
            base_path="OEBPS/ch.xhtml",
            max_decoded_bytes=4,
        )

    assert "data:image/bmp;base64," in out


def test_generation_resolver_excludes_deleted_image(tmp_path: Path) -> None:
    """Usunięty member nie rezerwuje budżetu i nie wraca ze źródłowego ZIP-a."""
    book = tmp_path / "fallback-deleted.epub"
    _make_html_epub(book)
    image_path = "OEBPS/img/deleted.bmp"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(image_path, _bmp(1, 1))
    with Epub(book) as epub:
        epub.delete_file(image_path)
        generation = PreviewSession.create(epub).advance(
            epub,
            "OEBPS/ch.xhtml",
            {},
            pending=epub.pending_changes(),
        )
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)
        out = inline_images(
            '<html><body><img src="img/deleted.bmp"/></body></html>',
            resolver,
            base_path="OEBPS/ch.xhtml",
            max_decoded_bytes=4,
        )

    assert "data:" not in out
    assert "deleted.bmp" not in out


def test_generation_resolver_rejects_oversized_source_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider fallbacku zachowuje 3 MiB guard źródła przed materializacją ZIP."""
    book = tmp_path / "fallback-generation-limit.epub"
    _make_html_epub(book)
    with Epub(book) as epub:
        session = PreviewSession.create(epub)
        generation = session.advance(epub, "OEBPS/ch.xhtml", {})
        provider = generation.resource_provider
        session.clear_cache()
        monkeypatch.setattr(provider, "_sizes", {"OEBPS/img/p.png": 3 * 1024 * 1024 + 1})
        monkeypatch.setattr(
            provider,
            "_read_source",
            lambda _path: pytest.fail("oversized source nie może być odczytany"),
        )
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml", generation)

        assert resolver("img/p.png") is None


def test_inline_images_skips_external_and_missing() -> None:
    """Zewnętrzne (http) i nierozwiązane src są usuwane fail-closed."""
    external = inline_images(
        '<html><body><img src="http://x/y.png"/></body></html>', lambda _s: _PNG
    )
    assert "http://x/y.png" not in external and "data:" not in external
    missing = inline_images('<html><body><img src="gone.png"/></body></html>', lambda _s: None)
    assert "gone.png" not in missing and "data:" not in missing


def test_fallback_image_resolver_rejects_before_full_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Obraz ponad 3 MiB odpada na ZipInfo przed materializacją fallbacku."""
    book = tmp_path / "fallback-large-image.epub"
    _make_html_epub(book)
    internal = "OEBPS/images/large.png"
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(internal, b"x" * (3 * 1024 * 1024 + 1), zipfile.ZIP_STORED)
    with Epub(book) as epub:
        original_read = epub.read_file

        def guarded_read(path: str) -> bytes:
            if path == internal:
                pytest.fail("fallback nie może materializować obrazu ponad limit encoded")
            return original_read(path)

        monkeypatch.setattr(epub, "read_file", guarded_read)
        resolver = _epub_image_resolver(epub, "OEBPS/ch.xhtml")
        assert resolver("images/large.png") is None


# ── Integracja w EditorTab ──────────────────────────────────────────────────--


def _make_html_epub(path: Path) -> None:
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        b'version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="h" href="ch.xhtml" media-type="application/xhtml+xml"/>'
        b'<item id="img" href="img/p.png" media-type="image/png"/></manifest>'
        b'<spine><itemref idref="h"/></spine></package>'
    )
    chapter = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>R</title></head>'
        b'<body><h1>Rozdzial PODGLAD</h1><img src="img/p.png"/></body></html>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch.xhtml", chapter)
        zf.writestr("OEBPS/img/p.png", _PNG)


def _open_html(qtbot: QtBot, tmp_path: Path, **kwargs: object) -> EditorTab:
    book = tmp_path / "b.epub"
    _make_html_epub(book)
    tab = EditorTab(**kwargs)  # type: ignore[arg-type]
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab._select_path("OEBPS/ch.xhtml")
    return tab


def test_view_switch_visible_for_html(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla HTML widoczny jest przełącznik Kod/Podgląd, domyślnie Kod."""
    tab = _open_html(qtbot, tmp_path)
    assert not tab.view_switch.isHidden()
    assert tab.code_view_button.isChecked() is True
    assert tab.stack.currentIndex() != _PAGE_HTML


def test_preview_toggle_renders_content(qtbot: QtBot, tmp_path: Path) -> None:
    """Przełączenie na Podgląd pokazuje stronę HTML z treścią rozdziału."""
    tab = _open_html(qtbot, tmp_path)
    tab.preview_view_button.setChecked(True)
    assert tab.stack.currentIndex() == _PAGE_HTML
    qtbot.waitUntil(lambda: "PODGLAD" in tab.html_preview.view.toPlainText(), timeout=2_000)


def test_preview_reflects_edits(qtbot: QtBot, tmp_path: Path) -> None:
    """Edycja kodu i przełączenie na Podgląd pokazuje niezapisaną zmianę."""
    tab = _open_html(qtbot, tmp_path)
    tab.edit_toggle.setChecked(True)
    cursor = tab.code_editor.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<p>NOWA TRESC EDYCJI</p></body></html>"
    )
    tab.preview_view_button.setChecked(True)
    qtbot.waitUntil(
        lambda: "NOWA TRESC EDYCJI" in tab.html_preview.view.toPlainText(), timeout=2_000
    )


def test_external_button_launches_with_current_epub(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przyciski Sigil/Calibre wołają launch_tool z bieżącym plikiem EPUB."""
    calls: list[tuple[object, Path]] = []
    monkeypatch.setattr(
        editor_preview, "launch_tool", lambda tool, target: calls.append((tool, target))
    )
    tools = {"sigil": Tool("sigil", Path("/bin/sigil"), "", True)}
    tab = _open_html(qtbot, tmp_path, tools=tools)
    tab._launch_external_tool("sigil")
    assert calls == [(tools["sigil"], tab._epub_path)]


def test_preview_paper_is_theme_independent(qtbot: QtBot, tmp_path: Path) -> None:
    """Tło podglądu pozostaje białe niezależnie od motywu aplikacji."""
    from chodzkos_gui_kit.palette import DARK, LIGHT

    tab = _open_html(qtbot, tmp_path)
    tab.set_theme(DARK)
    assert _PAPER_BG in tab.html_preview.view.styleSheet()
    tab.set_theme(LIGHT)
    assert _PAPER_BG in tab.html_preview.view.styleSheet()
