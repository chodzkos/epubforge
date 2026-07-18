"""Regresje niezmienności snapshotu, bezpiecznego MIME i kodowania URL."""

from __future__ import annotations

import os
from pathlib import Path

from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted
from epubforge.gui.preview.paths import build_preview_url, parse_preview_url
from epubforge.gui.preview.sanitize import sanitize_xhtml
from epubforge.gui.preview.session import PreviewSession


def test_provider_rejects_source_changed_during_generation(sample_epub: Path) -> None:
    """Generacja nie miesza danych, gdy źródłowy ZIP zmieni tożsamość na dysku."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, sample_epub)
    generation = session.advance(epub, "OEBPS/text/chapter1.xhtml", {})
    before = sample_epub.stat()
    os.utime(
        sample_epub,
        ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
    )
    assert generation.resource_provider.read("OEBPS/nav.xhtml", generation.generation_id) is None
    epub.close()


def test_executable_manifest_mime_falls_back_to_safe_extension(sample_epub: Path) -> None:
    """Manifest nie może zmienić XHTML w wykonywalny typ JavaScript."""
    epub = Epub(sample_epub)
    epub.open()
    opf = epub.read_file(epub.opf_path).replace(b"application/xhtml+xml", b"application/javascript")
    epub.write_file(epub.opf_path, opf)
    session = PreviewSession.create(epub, sample_epub)
    generation = session.advance(epub, "OEBPS/text/chapter1.xhtml", {})
    assert (
        generation.resource_provider.media_type("OEBPS/text/chapter1.xhtml")
        == "application/xhtml+xml"
    )
    epub.close()


def test_build_url_percent_encodes_unicode_fragment_and_query_characters() -> None:
    """Nazwa wpisu nie może przejąć fragmentu ani query generowanego URL-a."""
    session_id = "0123456789abcdef0123456789abcdef"
    path = "OEBPS/zażółć#rozdział?.xhtml"
    url = build_preview_url(session_id, path, 3)
    assert "%23" in url and "%3F" in url
    assert parse_preview_url(url).internal_path == path


def test_sanitizer_tolerates_comments_and_spaced_meta_refresh() -> None:
    """Komentarz XML nie przerywa sanityzacji, a refresh z odstępami znika."""
    rendered = sanitize_xhtml(
        b'<html><head><!--x--><meta http-equiv=" Refresh " content="0"/></head><body/></html>'
    )
    root = parse_untrusted(rendered)
    refresh = [
        element
        for element in root.iter()
        if isinstance(element.tag, str)
        and etree.QName(element).localname == "meta"
        and element.get("http-equiv", "").strip().lower() == "refresh"
    ]
    assert refresh == []
