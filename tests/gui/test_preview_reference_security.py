"""Regresje fail-closed dla aktywnych referencji dokładnego podglądu."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree
from tests.gui.test_preview_realistic_resources import _make_resource_epub

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted
from epubforge.gui.preview.rewrite import rewrite_svg, rewrite_xhtml
from epubforge.gui.preview.sanitize import sanitize_xhtml
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.srcset import parse_srcset


def _rewrite_security_case(tmp_path: Path, chapter: bytes) -> tuple[Epub, bytes]:
    """Przepuszcza dokument przez ten sam rewrite, którego używa handler WebEngine."""
    chapter_path = "OEBPS/text/ch.xhtml"
    epub = Epub(_make_resource_epub(tmp_path / "rewrite-security.epub"))
    epub.open()
    epub.write_file("OEBPS/images/cover.jpg", b"synthetic-cover")
    session = PreviewSession.create(epub)
    generation = session.advance(epub, chapter_path, {chapter_path: chapter})
    return epub, rewrite_xhtml(chapter, generation, chapter_path)


def test_sanitizer_removes_base_element() -> None:
    """Dokument nie może zmienić bazy URL przeglądarki przez ``base``."""
    source = b"""<html><head><base href="https://evil.example/"/></head><body/></html>"""

    rendered = sanitize_xhtml(source)

    assert b"<base" not in rendered.lower()
    assert b"https://evil.example/" not in rendered


def test_sanitizer_replaces_active_root_element() -> None:
    """Aktywny element jako korzeń fragmentu także jest usuwany fail-closed."""
    rendered = sanitize_xhtml(
        b'<form action="https://evil.example/"><input formaction="javascript:x"/></form>'
    )

    assert b"<form" not in rendered.lower()
    assert b"javascript:" not in rendered.lower()
    assert b"https://evil.example/" not in rendered


@pytest.mark.parametrize("http_equiv", ("refresh", "content-security-policy"))
def test_sanitizer_replaces_active_root_meta(http_equiv: str) -> None:
    """Aktywne root meta nie omija usunięcia tylko dlatego, że nie ma rodzica."""
    source = (
        f'<meta http-equiv="{http_equiv}" content="0;url=https://evil.example/;script-src *"/>'
    ).encode()

    rendered = sanitize_xhtml(source)

    root = parse_untrusted(rendered)
    assert etree.QName(root).localname.lower() == "html"
    assert b"https://evil.example/" not in rendered
    assert rendered.count(b"Content-Security-Policy") == 1


def test_xhtml_removes_javascript_href(tmp_path: Path) -> None:
    """Niedozwolony schemat nie przeżywa jako aktywny ``href``."""
    epub, rendered = _rewrite_security_case(
        tmp_path, b'<html><body><a href="javascript:alert(1)">x</a></body></html>'
    )

    assert b"javascript:" not in rendered.lower()
    link = parse_untrusted(rendered).find(".//a")
    assert link is not None and "href" not in link.attrib
    epub.close()


def test_xhtml_removes_remote_src(tmp_path: Path) -> None:
    """Zewnętrzny obraz nie pozostaje aktywnym ``src``."""
    epub, rendered = _rewrite_security_case(
        tmp_path, b'<html><body><img src="https://evil.example/x.png"/></body></html>'
    )

    assert b"https://evil.example/" not in rendered
    image = parse_untrusted(rendered).find(".//img")
    assert image is not None and "src" not in image.attrib
    epub.close()


def test_xhtml_srcset_keeps_only_safe_local_candidate(tmp_path: Path) -> None:
    """Każdy kandydat ``srcset`` przechodzi osobne rozwiązanie w publikacji."""
    source = (
        b'<html><body><img srcset="https://evil.example/a.png 1x, '
        b'../images/cover.jpg 2x"/></body></html>'
    )
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"https://evil.example/" not in rendered
    image = parse_untrusted(rendered).find(".//img")
    assert image is not None
    assert image.get("srcset", "").startswith("epub-preview://")
    assert image.get("srcset", "").endswith(" 2x")
    epub.close()


def test_xhtml_removes_srcset_when_no_safe_candidate_remains(tmp_path: Path) -> None:
    """Pusty po filtracji ``srcset`` jest usuwany, nie pozostawiany z remote URL-em."""
    epub, rendered = _rewrite_security_case(
        tmp_path,
        b'<html><body><img srcset="https://evil.example/a.png 1x"/></body></html>',
    )

    image = parse_untrusted(rendered).find(".//img")
    assert image is not None and "srcset" not in image.attrib
    assert b"https://evil.example/" not in rendered
    epub.close()


def test_xhtml_imagesrcset_keeps_only_safe_local_candidate(tmp_path: Path) -> None:
    """Preload obrazów nie omija polityki przez osobny atrybut ``imagesrcset``."""
    source = (
        b'<html><head><link rel="preload" as="image" '
        b'imagesrcset="https://evil.example/a.png 1x, ../images/cover.jpg 2x"/>'
        b"</head><body/></html>"
    )
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"https://evil.example/" not in rendered
    link = parse_untrusted(rendered).find(".//link")
    assert link is not None
    assert link.get("imagesrcset", "").startswith("epub-preview://")
    assert link.get("imagesrcset", "").endswith(" 2x")
    epub.close()


def test_xhtml_drops_original_reference_when_resolution_fails(tmp_path: Path) -> None:
    """Nierozwiązywalny URL nie może przeżyć jako oryginalny aktywny atrybut."""
    epub, rendered = _rewrite_security_case(
        tmp_path, b'<html><body><a href="missing.xhtml">missing</a></body></html>'
    )

    link = parse_untrusted(rendered).find(".//a")
    assert link is not None and "href" not in link.attrib
    assert b"missing.xhtml" not in rendered
    epub.close()


def test_xhtml_removes_javascript_xlink_href(tmp_path: Path) -> None:
    """SVG osadzone w XHTML nie zachowuje aktywnego ``xlink:href``."""
    source = b"""<html xmlns:xlink="http://www.w3.org/1999/xlink"><body><svg>
      <a xlink:href="javascript:alert(1)"/></svg></body></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"javascript:" not in rendered.lower()
    root = parse_untrusted(rendered)
    svg_link = next(
        element for element in root.iter() if etree.QName(element).localname.lower() == "a"
    )
    assert not any(
        etree.QName(attribute).localname.lower() == "href" for attribute in svg_link.attrib
    )
    epub.close()


def test_xhtml_neutralizes_remote_css_import_and_url(tmp_path: Path) -> None:
    """Remote ``@import`` i ``url()`` nie pozostają w aktywnym arkuszu dokumentu."""
    source = b"""<html><head><style>
      @import url("https://evil.example/x.css");
      body { background:url("https://evil.example/x.png"); }
      </style></head><body/></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"@import" not in rendered.lower()
    assert b"https://evil.example/" not in rendered
    epub.close()


def test_svg_neutralizes_remote_css_import_and_url(tmp_path: Path) -> None:
    """Arkusz osadzonego SVG przechodzi tę samą politykę URL co XHTML i CSS."""
    svg_path = "OEBPS/images/test.svg"
    source = b"""<svg xmlns="http://www.w3.org/2000/svg"><style>
      @import url("https://evil.example/x.css");
      rect { fill:url("https://evil.example/x.svg"); }
      </style><rect/></svg>"""
    epub = Epub(_make_resource_epub(tmp_path / "svg-style-security.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(epub, "OEBPS/text/ch.xhtml", {svg_path: source})

    rendered = rewrite_svg(source, generation, svg_path)

    assert b"@import" not in rendered.lower()
    assert b"https://evil.example/" not in rendered
    epub.close()


def test_svg_replaces_active_root_element(tmp_path: Path) -> None:
    """Aktywny korzeń zasobu SVG nie przeżywa z powodu braku rodzica w DOM."""
    svg_path = "OEBPS/images/test.svg"
    source = b'<script xmlns="http://www.w3.org/2000/svg">alert(1)</script>'
    epub = Epub(_make_resource_epub(tmp_path / "svg-root-security.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(epub, "OEBPS/text/ch.xhtml", {svg_path: source})

    rendered = rewrite_svg(source, generation, svg_path)

    assert b"<script" not in rendered.lower()
    assert b"alert(1)" not in rendered
    epub.close()


def test_svg_neutralizes_presentation_attribute_urls(tmp_path: Path) -> None:
    """CSS-owe ``url()`` w atrybutach prezentacji SVG także są fail-closed."""
    svg_path = "OEBPS/images/test.svg"
    source = b"""<svg xmlns="http://www.w3.org/2000/svg"><defs>
      <linearGradient id="paint"/></defs><rect
      fill="url(https://evil.example/fill.svg)"
      filter="url(data:image/svg+xml,x)" stroke="url(#paint)"/></svg>"""
    epub = Epub(_make_resource_epub(tmp_path / "svg-presentation-security.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    generation = session.advance(epub, "OEBPS/text/ch.xhtml", {svg_path: source})

    rendered = rewrite_svg(source, generation, svg_path)

    assert b"https://evil.example/" not in rendered
    assert b"data:image/svg+xml" not in rendered
    assert b"/OEBPS/images/test.svg?gen=1&amp;rev=" in rendered
    epub.close()


def test_xhtml_inline_svg_neutralizes_presentation_attribute_urls(tmp_path: Path) -> None:
    """Inline SVG w XHTML nie omija polityki przez atrybut prezentacji."""
    source = b"""<html><body><svg xmlns="http://www.w3.org/2000/svg">
      <rect fill="url(https://evil.example/fill.svg)"/></svg></body></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"https://evil.example/" not in rendered
    epub.close()


def test_xhtml_removes_ping_url_list(tmp_path: Path) -> None:
    """Kliknięcie linku nie zachowuje osobnego kanału requestów przez ``ping``."""
    source = b"""<html><body><a href="chapter.xhtml"
      ping="https://evil.example/a https://evil.example/b">x</a></body></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    link = parse_untrusted(rendered).find(".//a")
    assert link is not None and "ping" not in link.attrib
    assert b"https://evil.example/" not in rendered
    epub.close()


def test_xhtml_rewrites_safe_css_import_url_function(tmp_path: Path) -> None:
    """Legalny ``@import url(...)`` nadal ładuje arkusz z publikacji."""
    source = b"""<html><head><style>
      @import url("../styles/base.css");
      </style></head><body/></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"@import" in rendered.lower()
    assert b"/OEBPS/styles/base.css?gen=1&amp;rev=" in rendered
    epub.close()


def test_xhtml_srcset_supports_width_and_density_descriptors(tmp_path: Path) -> None:
    """Tokenizer obsługuje whitespace, ``300w`` i ``2x`` dla wielu kandydatów."""
    source = (
        b'<html><body><img srcset="  ../images/cover.jpg 300w,  '
        b'../images/p.png 2x  "/></body></html>'
    )
    epub, rendered = _rewrite_security_case(tmp_path, source)

    image = parse_untrusted(rendered).find(".//img")
    assert image is not None
    srcset = image.get("srcset", "")
    assert "OEBPS/images/cover.jpg" in srcset and srcset.endswith(" 2x")
    assert " 300w," in srcset
    epub.close()


@pytest.mark.parametrize(
    "source",
    (
        ", image.png 1x",
        "image.png 1x 2x",
        "image.png 0w",
        "image.png 0x",
        "image.png 1x,, other.png 2x",
    ),
)
def test_srcset_parser_rejects_malformed_candidates(source: str) -> None:
    """Wadliwa składnia srcset jest odrzucana bez częściowego przepuszczenia."""
    assert parse_srcset(source) is None


def test_srcset_parser_preserves_comma_inside_url() -> None:
    """Przecinek wewnątrz URL-a nie jest naiwnie traktowany jak separator."""
    assert parse_srcset("images/a,b.png 1x, image.png 2x") == [
        ("images/a,b.png", "1x"),
        ("image.png", "2x"),
    ]


def test_xhtml_neutralizes_remote_css_style_attribute(tmp_path: Path) -> None:
    """Remote ``url()`` w atrybucie style jest neutralizowany przez tinycss2."""
    source = b"""<html><body><p
      style="background:url(https://evil.example/x.png);color:red">x</p></body></html>"""
    epub, rendered = _rewrite_security_case(tmp_path, source)

    assert b"https://evil.example/" not in rendered
    paragraph = parse_untrusted(rendered).find(".//p")
    assert paragraph is not None and 'url("")' in paragraph.get("style", "")
    epub.close()


def test_xhtml_keeps_legal_parent_relative_reference(tmp_path: Path) -> None:
    """Legalne ``../images/cover.jpg`` nadal wskazuje zasób bieżącej generacji."""
    epub, rendered = _rewrite_security_case(
        tmp_path, b'<html><body><img src="../images/cover.jpg"/></body></html>'
    )

    assert b"/OEBPS/images/cover.jpg?gen=1&amp;rev=" in rendered
    epub.close()


def test_xhtml_keeps_safe_encoded_dot_reference(tmp_path: Path) -> None:
    """Zachowanie #182: bezpieczna zakodowana kropka pozostaje obsługiwana."""
    epub, rendered = _rewrite_security_case(
        tmp_path, b'<html><body><img src="../images/cover%2Ejpg"/></body></html>'
    )

    assert b"/OEBPS/images/cover.jpg?gen=1&amp;rev=" in rendered
    epub.close()
