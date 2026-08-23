"""Testy realistycznych zasobów i snapshotów niezapisanych zmian (Prompt 3)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from epubforge.core import Epub
from epubforge.gui.preview.backend import DiagnosticCategory
from epubforge.gui.preview.controller import PreviewController
from epubforge.gui.preview.registry import PreviewGenerationRegistry
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
