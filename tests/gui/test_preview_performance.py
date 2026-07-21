"""Budżety wydajności i pamięci kontrolowanego podglądu."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

from epubforge.core import Epub
from epubforge.gui.preview import session as session_module
from epubforge.gui.preview.cache import CacheLimits, ResourceByteCache, ResourceKind
from epubforge.gui.preview.controller import PreviewController
from epubforge.gui.preview.resources import SnapshotResourceProvider
from epubforge.gui.preview.session import PreviewSession

# Bazowy pomiar repozytorium (sample.epub, Linux): first 1,56 ms, next 0,58 ms,
# close 0,01 ms. Syntetyczny EPUB niżej ma kilka MiB; margines 100-500x chroni
# przed fałszywymi alarmami na współdzielonych runnerach, ale łapie blokujące regresje.
FIRST_RENDER_BUDGET_MS = 800.0
NEXT_RENDER_BUDGET_MS = 250.0
CSS_ONLY_BUDGET_MS = 200.0
CLOSE_BUDGET_MS = 50.0


def _large_epub(path: Path) -> Path:
    css = b"p{color:#123456;margin:1px}" * 8_000
    image = b"\x89PNG\r\n\x1a\n" + b"i" * (512 * 1024)
    font = b"wOF2" + b"f" * (512 * 1024)
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head>
    <link rel="stylesheet" href="../styles/a.css"/></head><body>
    <p style="color:red">tekst</p><img src="../images/a.png"/></body></html>"""
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Perf</dc:title>
    <dc:language>pl</dc:language></metadata><manifest>
    <item id="ch" href="text/ch.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="styles/a.css" media-type="text/css"/>
    <item id="img" href="images/a.png" media-type="image/png"/>
    <item id="font" href="fonts/a.woff2" media-type="font/woff2"/>
    </manifest><spine><itemref idref="ch"/></spine></package>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/text/ch.xhtml", chapter)
        archive.writestr("OEBPS/styles/a.css", css)
        archive.writestr("OEBPS/images/a.png", image)
        archive.writestr("OEBPS/fonts/a.woff2", font)
    return path


def test_cache_has_hard_total_and_per_kind_byte_limits() -> None:
    limits = CacheLimits(documents=10, css=8, images=12, fonts=14, other=4)
    cache = ResourceByteCache(limits)
    assert cache.put("a.xhtml", 1, ResourceKind.DOCUMENT, b"1234567890")
    assert cache.put("b.xhtml", 1, ResourceKind.DOCUMENT, b"abcdefghij")
    assert cache.put("a.css", 1, ResourceKind.CSS, b"12345678")
    assert not cache.put("huge.css", 1, ResourceKind.CSS, b"x" * 9)
    stats = cache.stats()
    assert stats.by_kind["documents"] <= limits.documents
    assert stats.by_kind["css"] <= limits.css
    assert stats.bytes <= limits.total
    assert stats.evictions == 1
    assert cache.remaining(ResourceKind.DOCUMENT) == 0


@pytest.mark.slow
def test_snapshot_budgets_cache_and_css_only_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = Epub(_large_epub(tmp_path / "performance.epub"))
    epub.open()
    session = PreviewSession.create(epub)
    controller = PreviewController()
    catalog_calls = 0
    original_catalog = session_module.build_resource_catalog

    def counted_catalog(value: Epub):
        nonlocal catalog_calls
        catalog_calls += 1
        return original_catalog(value)

    monkeypatch.setattr(session_module, "build_resource_catalog", counted_catalog)
    chapter = epub.read_file("OEBPS/text/ch.xhtml").decode()
    first = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text=chapter,
        dirty={},
        media_types={"OEBPS/text/ch.xhtml": "application/xhtml+xml"},
    )
    second = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/text/ch.xhtml",
        current_text=chapter.replace("tekst", "kolejny"),
        dirty={},
        media_types={"OEBPS/text/ch.xhtml": "application/xhtml+xml"},
    )
    css = controller.build(
        epub=epub,
        session=session,
        current_path="OEBPS/styles/a.css",
        current_text="p{color:navy!important}",
        dirty={},
        media_types={"OEBPS/styles/a.css": "text/css"},
    )
    assert first.snapshot and second.snapshot and css.snapshot and css.snapshot.css_only
    assert catalog_calls == 1
    metrics = session.performance
    assert metrics.first_render_ms is not None and metrics.first_render_ms < FIRST_RENDER_BUDGET_MS
    assert metrics.next_render_ms is not None and metrics.next_render_ms < NEXT_RENDER_BUDGET_MS
    assert (
        metrics.css_only_reload_ms is not None and metrics.css_only_reload_ms < CSS_ONLY_BUDGET_MS
    )
    stats = session.cache_stats()
    assert stats.bytes <= stats.limits.total
    assert all(stats.by_kind[kind.value] <= stats.limits.for_kind(kind) for kind in ResourceKind)

    provider = css.snapshot.generation.resource_provider if css.snapshot.generation else None
    assert isinstance(provider, SnapshotResourceProvider)
    monkeypatch.setattr(provider, "_read_source", lambda _path: pytest.fail("cache miss handlera"))
    generation_id = css.snapshot.generation_id
    assert provider.read_prepared("OEBPS/images/a.png", generation_id)
    assert provider.read_prepared("OEBPS/fonts/a.woff2", generation_id)

    started = time.perf_counter()
    session.close()
    measured_close = (time.perf_counter() - started) * 1000
    assert session.performance.close_ms is not None
    assert measured_close < CLOSE_BUDGET_MS
    assert session.cache_stats().bytes == 0
    epub.close()
