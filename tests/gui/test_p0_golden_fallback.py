"""P0 fallback QTextBrowser isolation and raster trust tests."""

from __future__ import annotations

import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtGui import QTextDocument
from pytestqt.qtbot import QtBot

from epubforge.core.epub import Epub
from epubforge.gui.widgets.html_preview import HtmlPreview, _epub_image_resolver, inline_images

pytestmark = [pytest.mark.gui, pytest.mark.security]

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c63f8cfc0f01f00050001ff89993d1d0000000049454e44ae426082"
)
_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///tmp/sentinel"/></svg>'


def _make_epub(path: Path) -> Path:
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="h" href="text/ch.xhtml" media-type="application/xhtml+xml"/>'
        b'<item id="img" href="images/p.png" media-type="image/png"/></manifest>'
        b'<spine><itemref idref="h"/></spine></package>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/text/ch.xhtml", b"<html/>")
        zf.writestr("OEBPS/images/p.png", _PNG)
    return path


def test_epub_resolver_accepts_internal_parent_and_rejects_escape() -> None:
    calls: list[str] = []

    class FakeEpub:
        def read_file_limited(self, path: str, max_bytes: int) -> bytes:
            assert max_bytes == 3 * 1024 * 1024
            calls.append(path)
            return _PNG

    resolver = _epub_image_resolver(FakeEpub(), "OEBPS/text/ch.xhtml")  # type: ignore[arg-type]
    assert resolver("../images/p.png") == _PNG
    assert resolver("../../../outside.png") is None
    assert resolver("file:///tmp/sentinel.png") is None
    assert resolver("%2e%2e/%2e%2e/outside.png") is None
    assert resolver("%2Ftmp/sentinel.png") is None
    assert resolver("bad%zz.png") is None
    assert resolver("image.png?redirect=file:///tmp/sentinel") is None
    assert resolver("C%3A/Windows/sentinel.png") is None
    assert resolver("%66ile%3A///tmp/sentinel.png") is None
    assert calls == ["OEBPS/images/p.png"]


@pytest.mark.parametrize("name", ["image.svg", "image.png"])
def test_svg_and_svg_disguised_as_raster_never_become_data_uri(name: str) -> None:
    out = inline_images(f'<html><body><img src="{name}"/></body></html>', lambda _src: _SVG)
    assert "data:" not in out
    assert name in out


def test_raw_untrusted_data_uri_is_not_allowlisted(qtbot: QtBot) -> None:
    raw = "data:image/png;base64," + "QQ=="
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    preview.set_content(f'<html><body><img src="{raw}"/></body></html>', None, None)
    assert raw not in preview.view.toHtml()
    loaded = preview.view.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(raw))
    assert isinstance(loaded, QByteArray)
    assert loaded.isEmpty()


def test_generated_raster_is_allowlisted_only_as_image(qtbot: QtBot, tmp_path: Path) -> None:
    book = _make_epub(tmp_path / "book.epub")
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    with Epub(book) as epub:
        preview.set_content(
            '<html><body><img src="../images/p.png"/></body></html>',
            epub,
            "OEBPS/text/ch.xhtml",
        )
        rendered = preview.view.toHtml()
        assert "data:image/png;base64," in rendered
        allowed = next(iter(preview.view._allowed_data_urls))
        assert preview.view.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl(allowed)
        )
        direct = preview.view.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(allowed))
        assert isinstance(direct, QByteArray)
        assert not direct.isEmpty()
        blocked = preview.view.loadResource(
            QTextDocument.ResourceType.StyleSheetResource, QUrl(allowed)
        )
        assert isinstance(blocked, QByteArray)
        assert blocked.isEmpty()


def test_previous_document_data_uri_is_revoked(qtbot: QtBot, tmp_path: Path) -> None:
    book = _make_epub(tmp_path / "book.epub")
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    with Epub(book) as epub:
        preview.set_content(
            '<html><body><img src="../images/p.png"/></body></html>',
            epub,
            "OEBPS/text/ch.xhtml",
        )
        old_url = next(iter(preview.view._allowed_data_urls))
        assert preview.view.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl(old_url)
        )
        preview.set_content("<html><body>next</body></html>", epub, "OEBPS/text/ch.xhtml")
    blocked = preview.view.document().resource(
        QTextDocument.ResourceType.ImageResource, QUrl(old_url)
    )
    assert not blocked


def test_previous_qtextdocument_is_released_on_generation_reset(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Zmiana generacji nie pozostawia starego cache zasobów jako child QTextBrowser."""
    book = _make_epub(tmp_path / "book.epub")
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    with Epub(book) as epub:
        preview.set_content(
            '<html><body><img src="../images/p.png"/></body></html>',
            epub,
            "OEBPS/text/ch.xhtml",
        )
        preview.set_content("<html><body>next</body></html>", epub, "OEBPS/text/ch.xhtml")

    assert len(preview.view.findChildren(QTextDocument)) == 1


@pytest.mark.parametrize("attribute", ["SRC", "Src", "x:src"])
def test_case_variant_and_namespaced_raw_data_src_is_removed(attribute: str) -> None:
    namespace = ' xmlns:x="urn:test"' if attribute.startswith("x:") else ""
    raw = "data:image/png;base64,QQ=="
    html = f'<html{namespace}><body><img {attribute}="{raw}"/></body></html>'
    assert raw not in inline_images(html, lambda _src: None)


def test_file_sentinel_loader_is_hard_boundary(qtbot: QtBot, tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.png"
    sentinel.write_bytes(_PNG)
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    loaded = preview.view.loadResource(
        QTextDocument.ResourceType.ImageResource, QUrl.fromLocalFile(str(sentinel))
    )
    assert isinstance(loaded, QByteArray)
    assert loaded.isEmpty()


def test_local_http_sentinel_receives_zero_requests(qtbot: QtBot) -> None:
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(_PNG)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/sentinel.png"
        preview.set_content(f'<html><body><img src="{url}"/></body></html>', None, None)
        loaded = preview.view.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(url))
        assert isinstance(loaded, QByteArray)
        assert loaded.isEmpty()
        qtbot.wait(200)
        assert hits == []
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_all_external_resource_surfaces_are_removed(qtbot: QtBot) -> None:
    preview = HtmlPreview()
    qtbot.addWidget(preview)
    html = """<html><head>
    <link href="https://example.invalid/a.css"/>
    <style>body { background: url(file:///tmp/sentinel); }</style></head><body>
    <img src="//example.invalid/a.png" srcset="http://127.0.0.1/a 2x"/>
    <video poster="ftp://example.invalid/a.png"/>
    <object data="file:///tmp/sentinel"/>
    <table background="/tmp/sentinel"><tr><td style="background:url(https://example.invalid/x)">x</td></tr></table>
    <a href="file:///tmp/sentinel">link</a></body></html>"""
    html = html.replace(
        "</style>",
        " x { background: u\\72l(file:///tmp/escaped); }"
        " @\\69mport 'https://example.invalid/escaped.css';</style>",
    )
    preview.set_content(html, None, None)
    rendered = inline_images(html, lambda _src: None).lower()
    for forbidden in ("file:", "http:", "https:", "ftp:", "//example.invalid", "/tmp/sentinel"):
        assert forbidden not in rendered


def test_parse_failure_does_not_fall_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        raise ValueError("synthetic parser rejection")

    monkeypatch.setattr("epubforge.gui.widgets.html_preview.parse_untrusted", reject)
    hostile = '<html><img src="file:///tmp/sentinel"/></html>'
    assert inline_images(hostile, lambda _src: None) == ""
