"""Testy realistycznych zasobów i snapshotów niezapisanych zmian (Prompt 3)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from epubforge.core import Epub
from epubforge.gui.preview import controller as controller_module
from epubforge.gui.preview.backend import DiagnosticCategory
from epubforge.gui.preview.controller import PreviewController
from epubforge.gui.preview.reader import LayoutMode
from epubforge.gui.preview.registry import PreviewGenerationRegistry
from epubforge.gui.preview.resources import SnapshotResourceProvider
from epubforge.gui.preview.rewrite import rewrite_css, rewrite_svg, rewrite_xhtml
from epubforge.gui.preview.session import PreviewSession


def _make_resource_epub(path: Path) -> Path:
    """Buduje mały EPUB z CSS, obrazami i fontem bez rozpakowywania publikacji."""
    opf = b"""<?xml version="1.0" encoding="utf-8"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="id">urn:test</dc:identifier><dc:title>Test</dc:title>
        <dc:language>pl</dc:language>
      </metadata>
      <manifest>
        <item id="ch" href="text/ch.xhtml" media-type="application/xhtml+xml"/>
        <item id="css" href="styles/base.css" media-type="text/css"/>
        <item id="extra" href="styles/extra.css" media-type="text/css"/>
        <item id="png" href="images/p.png" media-type="image/png"/>
        <item id="webp" href="images/bg.webp" media-type="image/webp"/>
        <item id="svg" href="images/icon.svg" media-type="image/svg+xml"/>
        <item id="font" href="fonts/book.woff2" media-type="font/woff2"/>
      </manifest><spine><itemref idref="ch"/></spine>
    </package>"""
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head>
      <link rel="stylesheet" href="../styles/base.css"/></head><body>
      <p id="anchor">Tekst</p><img src="../images/p.png"/><img src="../images/icon.svg"/>
      <div xml:base="../images/"><img src="p.png"/></div>
      <svg xmlns="http://www.w3.org/2000/svg"><image href="../images/p.png"/></svg>
    </body></html>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf"
            media-type="application/oebps-package+xml"/></rootfiles></container>""",
        )
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/text/ch.xhtml", chapter)
        archive.writestr(
            "OEBPS/styles/base.css",
            '@import "extra.css"; @font-face{font-family:Book;src:url("../fonts/book.woff2")} '
            'body{background:url("../images/bg.webp")}',
        )
        archive.writestr("OEBPS/styles/extra.css", '@import "base.css"; p{color:navy}')
        archive.writestr("OEBPS/images/p.png", b"\x89PNG\r\n\x1a\n")
        archive.writestr("OEBPS/images/bg.webp", b"RIFF\x00\x00\x00\x00WEBP")
        archive.writestr("OEBPS/fonts/book.woff2", b"wOF2fixture")
        archive.writestr(
            "OEBPS/images/icon.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" onload="bad()">'
            '<script>bad()</script><image href="https://example.test/x.png"/>'
            "</svg>",
        )
    return path


def test_xhtml_and_css_references_use_resource_revisions(tmp_path: Path) -> None:
    """Link CSS, obrazy, SVG, @import, font i CSS url dostają izolowane URL-e."""
    epub = Epub(_make_resource_epub(tmp_path / "resources.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(epub, "OEBPS/text/ch.xhtml", {})
    chapter = generation.resource_provider.read("OEBPS/text/ch.xhtml", generation.generation_id)
    css = generation.resource_provider.read("OEBPS/styles/base.css", generation.generation_id)
    assert chapter is not None and css is not None

    rendered = rewrite_xhtml(chapter, generation, "OEBPS/text/ch.xhtml").decode()
    rendered_css = rewrite_css(css, generation, "OEBPS/styles/base.css").decode()

    assert "OEBPS/styles/base.css?gen=1&amp;rev=" in rendered
    assert rendered.count("OEBPS/images/p.png?gen=1&amp;rev=") == 3
    assert "OEBPS/images/icon.svg?gen=1&amp;rev=" in rendered
    assert 'data-epubforge-path="OEBPS/styles/base.css"' in rendered
    assert "data-epubforge-node-id" in rendered
    assert "OEBPS/styles/extra.css?gen=1&rev=" in rendered_css
    assert "OEBPS/fonts/book.woff2?gen=1&rev=" in rendered_css
    assert "OEBPS/images/bg.webp?gen=1&rev=" in rendered_css
    extra = generation.resource_provider.read("OEBPS/styles/extra.css", 1)
    assert extra is not None
    assert (
        "OEBPS/styles/base.css?gen=1&rev="
        in rewrite_css(extra, generation, "OEBPS/styles/extra.css").decode()
    )
    assert generation.resource_provider.media_type("OEBPS/fonts/book.woff2") == "font/woff2"
    svg = generation.resource_provider.read("OEBPS/images/icon.svg", generation.generation_id)
    assert svg is not None
    svg_events = []
    safe_svg = rewrite_svg(svg, generation, "OEBPS/images/icon.svg", svg_events.append)
    assert b"<script" not in safe_svg and b"onload" not in safe_svg
    assert [event.problem_kind for event in svg_events] == ["zablokowany_url"]
    epub.close()


def test_provider_retains_only_dirty_winner_for_pending_overlap(tmp_path: Path) -> None:
    """Pending przegrany przez dirty nie zajmuje drugiego bufora providera."""
    epub = Epub(_make_resource_epub(tmp_path / "overlap.epub"))
    epub.open()
    path = "OEBPS/styles/base.css"
    epub.write_file(path, b"pending-old")
    pending = epub.pending_changes()
    session = PreviewSession.create(epub)

    generation = session.advance(
        epub,
        "OEBPS/text/ch.xhtml",
        {path: b"dirty-wins"},
        pending=pending,
    )

    provider = generation.resource_provider
    assert isinstance(provider, SnapshotResourceProvider)
    assert provider.read(path, generation.generation_id) == b"dirty-wins"
    assert path not in provider._buffered
    assert provider.resident_bytes == len(b"dirty-wins")
    session.close()
    epub.close()


def test_xhtml_rewrites_percent_encoded_dot_inside_resource_name(tmp_path: Path) -> None:
    """Zakodowana kropka w nazwie obrazu wskazuje kanoniczny zasób publikacji."""
    epub = Epub(_make_resource_epub(tmp_path / "encoded-dot.epub"))
    epub.open()
    chapter_path = "OEBPS/text/ch.xhtml"
    cover_path = "OEBPS/images/cover.jpg"
    chapter = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        b'<img src="../images/cover%2Ejpg"/></body></html>'
    )
    epub.write_file(cover_path, b"synthetic-cover")
    session = PreviewSession.create(epub)
    generation = session.advance(epub, chapter_path, {chapter_path: chapter})

    rendered = rewrite_xhtml(chapter, generation, chapter_path).decode()

    assert f"/{cover_path}?gen=1&amp;rev=" in rendered
    epub.close()


def test_xhtml_named_entity_nodes_do_not_break_preview_rewrite(tmp_path: Path) -> None:
    """Nierozwinięte encje XHTML nie są elementami i nie mogą trafić do ``QName``."""
    epub = Epub(_make_resource_epub(tmp_path / "named-entity.epub"))
    epub.open()
    chapter_path = "OEBPS/text/ch.xhtml"
    chapter = b"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
      "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
      <html xmlns="http://www.w3.org/1999/xhtml"><head></head>
      <body><p>Przed&nbsp;po</p></body></html>"""
    session = PreviewSession.create(epub)
    generation = session.advance(epub, chapter_path, {chapter_path: chapter})

    rendered = rewrite_xhtml(chapter, generation, chapter_path)

    assert b"&nbsp;" in rendered
    assert b"data-epubforge-node-id" in rendered
    epub.close()


def test_current_editor_and_dirty_css_are_snapshotted(tmp_path: Path) -> None:
    """Bieżący CodeEditor wygrywa z dirty, a niezapisany CSS tworzy nową generację."""
    epub = Epub(_make_resource_epub(tmp_path / "snapshot.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    controller = PreviewController()
    current = '<html xmlns="http://www.w3.org/1999/xhtml"><body>NOWE</body></html>'
    first = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text=current,
        dirty={"OEBPS/text/ch.xhtml": "<html><body>STARE</body></html>"},
        media_types={"OEBPS/text/ch.xhtml": "application/xhtml+xml"},
    )
    assert first.snapshot is not None and first.snapshot.generation is not None
    provider = first.snapshot.generation.resource_provider
    assert b"NOWE" in (provider.read("OEBPS/text/ch.xhtml", 1) or b"")

    second = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/styles/base.css",
        current_text="body{color:rgb(1,2,3)}",
        dirty={},
        media_types={"OEBPS/styles/base.css": "text/css"},
    )
    assert second.snapshot is not None and second.snapshot.css_only
    assert second.snapshot.generation_id == 2
    assert b"rgb(1,2,3)" in (
        second.snapshot.generation.resource_provider.read("OEBPS/styles/base.css", 2)
        if second.snapshot.generation is not None
        else b""
    )
    epub.close()


def test_stale_generation_cannot_resolve_after_css_update(tmp_path: Path) -> None:
    """Wynik wcześniejszej generacji nie może zostać podany po nowszej zmianie."""
    epub = Epub(_make_resource_epub(tmp_path / "stale.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    first = session.advance(epub, "OEBPS/text/ch.xhtml", {})
    second = session.advance(
        epub, "OEBPS/text/ch.xhtml", {"OEBPS/styles/base.css": "body{color:red}"}
    )
    registry = PreviewGenerationRegistry()
    registry.activate(first)
    old_url = first.document_url
    assert registry.resolve_url(old_url) is not None
    registry.activate(second)
    assert registry.resolve_url(old_url) is None
    assert registry.resolve_url(second.document_url) is not None
    epub.close()


def test_invalid_xhtml_keeps_last_document_for_css(tmp_path: Path) -> None:
    """Niepoprawny XHTML nie zastępuje ostatniej poprawnej wersji kontrolera."""
    epub = Epub(_make_resource_epub(tmp_path / "invalid.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    controller = PreviewController()
    good = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text='<html xmlns="http://www.w3.org/1999/xhtml"><body>DOBRY</body></html>',
        dirty={},
        media_types={},
    )
    bad = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text="<html><body>",
        dirty={},
        media_types={},
    )
    css = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/styles/base.css",
        current_text="body{color:green}",
        dirty={},
        media_types={"OEBPS/styles/base.css": "text/css"},
    )
    assert good.snapshot is not None
    assert bad.snapshot is None and bad.diagnostic is not None
    assert bad.diagnostic.category is DiagnosticCategory.BOOK_ERROR
    assert css.snapshot is not None and "DOBRY" in css.snapshot.xhtml
    epub.close()


def test_missing_and_external_resources_report_safe_diagnostics(tmp_path: Path) -> None:
    """Diagnostyka podaje URL, internal path i requester bez ścieżki użytkownika."""
    epub = Epub(_make_resource_epub(tmp_path / "diagnostics.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(
        epub,
        "OEBPS/text/ch.xhtml",
        {
            "OEBPS/text/ch.xhtml": (
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                '<img src="../images/missing.png"/><img src="file:///sekret.png"/>'
                "</body></html>"
            )
        },
    )
    events = []
    data = generation.resource_provider.read("OEBPS/text/ch.xhtml", generation.generation_id)
    assert data is not None
    rewrite_xhtml(data, generation, "OEBPS/text/ch.xhtml", events.append)
    assert {event.problem_kind for event in events} == {"brak_zasobu", "zablokowany_url"}
    missing = next(event for event in events if event.problem_kind == "brak_zasobu")
    assert missing.internal_path == "OEBPS/images/missing.png"
    assert missing.requester == "OEBPS/text/ch.xhtml"
    blocked = next(event for event in events if event.problem_kind == "zablokowany_url")
    assert blocked.source_url == "file:[ukryto]"
    assert str(tmp_path) not in repr(events)
    epub.close()


def test_controller_rejects_oversized_xhtml_before_xml_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Core pipeline podglądu ma własny guard przed parse/source map/overlay."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-limit.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    controller = PreviewController()
    monkeypatch.setattr(controller_module, "MAX_MAIN_PREVIEW_BYTES", 64)
    monkeypatch.setattr(
        controller_module,
        "parse_untrusted",
        lambda _data: pytest.fail("oversized XHTML nie może trafić do parsera"),
    )
    source = "<p>" + "x" * 58 + "</p>"  # dokładnie limit + 1 bajt UTF-8

    result = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text=source,
        dirty={},
        media_types={"OEBPS/text/ch.xhtml": "application/xhtml+xml"},
    )

    assert result.snapshot is None
    assert result.diagnostic is not None
    assert result.diagnostic.category is DiagnosticCategory.PREVIEW_LIMIT
    assert source not in result.diagnostic.message
    epub.close()


def test_controller_rejects_oversized_css_before_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSS ma skalibrowany hard ceiling zanim powstaną kopie overlay/provider."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-css-limit.epub"))
    epub.open()
    controller = PreviewController()
    monkeypatch.setattr(controller_module, "MAX_PREVIEW_CSS_BYTES", 64)

    result = controller.build(
        epub=epub,
        session=PreviewSession.create(epub),
        current_path="OEBPS/styles/base.css",
        current_text="x" * 65,
        dirty={},
        media_types={"OEBPS/styles/base.css": "text/css"},
    )

    assert result.snapshot is None
    assert result.diagnostic is not None
    assert result.diagnostic.category is DiagnosticCategory.PREVIEW_LIMIT
    assert result.diagnostic.problem_kind == "zbyt_duzy_arkusz_css"
    epub.close()


@pytest.mark.parametrize(
    ("path", "media_type", "limit_name"),
    [
        ("OEBPS/styles/dirty.css", "text/css", "MAX_PREVIEW_CSS_BYTES"),
        ("OEBPS/text/dirty.xhtml", "application/xhtml+xml", "MAX_MAIN_PREVIEW_BYTES"),
    ],
)
def test_controller_rejects_oversized_dirty_text_before_overlay_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    media_type: str,
    limit_name: str,
) -> None:
    """Defense in depth kontrolera sprawdza cały dirty mapping przed dict()."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-dirty-limit.epub"))
    epub.open()
    monkeypatch.setattr(controller_module, limit_name, 64)

    result = PreviewController().build(
        epub=epub,
        session=PreviewSession.create(epub),
        current_path="OEBPS/text/ch.xhtml",
        current_text="<html><body>small</body></html>",
        dirty={path: "x" * 65},
        media_types={path: media_type},
    )

    assert result.snapshot is None
    assert result.diagnostic is not None
    assert result.diagnostic.category is DiagnosticCategory.PREVIEW_LIMIT
    epub.close()


def test_controller_rejects_oversized_pending_css_before_session_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense in depth kontrolera sprawdza pending sizes przed providerem."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-pending-limit.epub"))
    epub.open()
    path = "OEBPS/styles/pending.css"
    epub.write_file(path, b"x" * 65)
    monkeypatch.setattr(controller_module, "MAX_PREVIEW_CSS_BYTES", 64)

    result = PreviewController().build(
        epub=epub,
        session=PreviewSession.create(epub),
        current_path="OEBPS/text/ch.xhtml",
        current_text="<html><body>small</body></html>",
        dirty={},
        media_types={path: "text/css"},
    )

    assert result.snapshot is None
    assert result.diagnostic is not None
    assert result.diagnostic.problem_kind == "zbyt_duzy_arkusz_css"
    epub.close()


def test_controller_uses_same_pending_snapshot_for_validation_and_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutacja pending po guardzie nie może wejść do providera bieżącej generacji."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-pending-race.epub"))
    epub.open()
    late_path = "OEBPS/styles/late.css"

    def mutate_after_snapshot(**_kwargs: object) -> None:
        epub.write_file(late_path, b"x" * 65)
        return None

    monkeypatch.setattr(controller_module, "find_preview_text_violation", mutate_after_snapshot)
    result = PreviewController().build(
        epub=epub,
        session=PreviewSession.create(epub),
        current_path="OEBPS/text/ch.xhtml",
        current_text="<html><body>small</body></html>",
        dirty={},
        media_types={late_path: "text/css"},
    )

    assert result.snapshot is not None and result.snapshot.generation is not None
    provider = result.snapshot.generation.resource_provider
    assert provider.read(late_path, result.snapshot.generation_id) is None
    assert epub.get_file_size(late_path) == 65
    epub.close()


def test_late_opf_pending_mutation_does_not_change_frozen_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Layout i provider korzystają z tej samej zamrożonej wersji OPF."""
    epub = Epub(_make_resource_epub(tmp_path / "controller-opf-race.epub"))
    epub.open()
    source_opf = epub.read_file(epub.opf_path)
    fixed_opf = source_opf.replace(
        b"</metadata>",
        b'<meta property="rendition:layout">pre-paginated</meta></metadata>',
    )

    def mutate_after_snapshot(**_kwargs: object) -> None:
        epub.write_file(epub.opf_path, fixed_opf)
        return None

    monkeypatch.setattr(controller_module, "find_preview_text_violation", mutate_after_snapshot)
    result = PreviewController().build(
        epub=epub,
        session=PreviewSession.create(epub),
        current_path="OEBPS/text/ch.xhtml",
        current_text="<html><body>small</body></html>",
        dirty={},
        media_types={},
    )

    assert result.snapshot is not None and result.snapshot.generation is not None
    assert result.snapshot.publication_layout.layout is LayoutMode.REFLOWABLE
    provider = result.snapshot.generation.resource_provider
    assert provider.read(epub.opf_path, result.snapshot.generation_id) == source_opf
    assert epub.read_file(epub.opf_path) == fixed_opf
    epub.close()
