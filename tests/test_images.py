"""Testy optymalizacji obrazów w EPUB (fixtures generowane Pillow)."""

from __future__ import annotations

import builtins
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

# Cały moduł zależy od Pillow — bez niego pomijamy (extra [images] opcjonalne).
pytest.importorskip("PIL")
from PIL import Image

from epubforge.core import Epub
from epubforge.fixers import ImageFixOptions, ImageOptimizationError, optimize_images

_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


# ── Generatory obrazów ───────────────────────────────────────────────────────


def _gradient(size: tuple[int, int]) -> Image.Image:
    """Obraz z gradientem (treść do skalowania) — budowany operacjami PIL (szybko)."""
    band = Image.linear_gradient("L").resize(size)  # pionowy gradient 0..255
    return Image.merge("RGB", (band, band.rotate(90), band.rotate(180)))


def _jpeg_bytes(size: tuple[int, int] = (1500, 1500), exif: bytes | None = None) -> bytes:
    buffer = BytesIO()
    kwargs: dict[str, object] = {"quality": 95}
    if exif is not None:
        kwargs["exif"] = exif
    _gradient(size).save(buffer, format="JPEG", **kwargs)
    return buffer.getvalue()


def _png_rgba_bytes(size: tuple[int, int] = (1500, 1500)) -> bytes:
    width, height = size
    img = _gradient(size).convert("RGBA")
    alpha = Image.new("L", size)
    alpha_px = alpha.load()
    for y in range(height):
        for x in range(width):
            alpha_px[x, y] = (x * 255) // width
    img.putalpha(alpha)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _png_palette_bytes(size: tuple[int, int] = (1500, 1500)) -> bytes:
    buffer = BytesIO()
    _gradient(size).convert("P", palette=Image.Palette.ADAPTIVE).save(buffer, format="PNG")
    return buffer.getvalue()


# ── Budowa EPUB ──────────────────────────────────────────────────────────────


def _build_epub(
    tmp_path: Path,
    images: dict[str, bytes],
    *,
    cover_href: str | None = None,
    cover_mode: str = "epub3",
) -> Path:
    """Tworzy EPUB z podanymi obrazami; opcjonalnie oznacza jeden jako okładkę."""
    epub_path = tmp_path / "book.epub"
    container_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )

    items: list[str] = [
        '<item id="chapter1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>'
    ]
    for index, (href, _data) in enumerate(images.items()):
        suffix = Path(href).suffix.lower()
        item_id = f"img{index}"
        props = ""
        if cover_href == href and cover_mode == "epub3":
            props = ' properties="cover-image"'
            item_id = "cover-image"
        elif cover_href == href and cover_mode == "epub2":
            item_id = "cover-id"
        items.append(
            f'<item id="{item_id}" href="{href}" media-type="{_MEDIA_TYPES[suffix]}"{props}/>'
        )

    meta = ""
    if cover_href is not None and cover_mode == "epub2":
        meta = '<meta name="cover" content="cover-id"/>'

    content_opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">id</dc:identifier><dc:title>t</dc:title>'
        f"<dc:language>pl</dc:language>{meta}</metadata>"
        f"<manifest>{''.join(items)}</manifest>"
        '<spine><itemref idref="chapter1"/></spine></package>'
    )
    chapter = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        "<body><p>Test</p></body></html>"
    )

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", content_opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", chapter.encode(), zipfile.ZIP_DEFLATED)
        for href, data in images.items():
            zf.writestr(f"OEBPS/{href}", data, zipfile.ZIP_STORED)
    return epub_path


def _reopen(epub: Epub, href: str) -> Image.Image:
    """Otwiera obraz z bufora EPUB-a jako obiekt Pillow (do sprawdzenia round-tripu)."""
    return Image.open(BytesIO(epub.read_file(f"OEBPS/{href}")))


# ── Testy ────────────────────────────────────────────────────────────────────


def test_jpeg_optimized_and_renders(tmp_path: Path) -> None:
    """JPEG jest zmniejszany, zostaje JPEG i wciąż się otwiera."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes()})
    with Epub(path) as epub:
        report = optimize_images(epub, ImageFixOptions(max_px=1200))
        result = report.results[0]
        assert result.changed and result.size_after < result.size_before
        image = _reopen(epub, "images/a.jpg")
        assert image.format == "JPEG"
        assert max(image.size) <= 1200


def test_png_alpha_preserved(tmp_path: Path) -> None:
    """PNG z kanałem alfa zachowuje przezroczystość po optymalizacji."""
    path = _build_epub(tmp_path, {"images/a.png": _png_rgba_bytes()})
    with Epub(path) as epub:
        optimize_images(epub, ImageFixOptions(max_px=1000))
        image = _reopen(epub, "images/a.png")
        assert image.format == "PNG"
        assert image.mode == "RGBA"


def test_png_palette_preserved(tmp_path: Path) -> None:
    """PNG w trybie palety (P) pozostaje paletą i formatem PNG."""
    path = _build_epub(tmp_path, {"images/a.png": _png_palette_bytes()})
    with Epub(path) as epub:
        optimize_images(epub, ImageFixOptions(max_px=1000))
        image = _reopen(epub, "images/a.png")
        assert image.format == "PNG"
        assert image.mode == "P"


def test_second_pass_is_noop(tmp_path: Path) -> None:
    """Idempotentność: drugi przebieg nie zmniejsza już zoptymalizowanego pliku."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes()})
    with Epub(path) as epub:
        optimize_images(epub, ImageFixOptions(max_px=1200))
        second = optimize_images(epub, ImageFixOptions(max_px=1200))
        assert second.changed_files == []


def test_cover_skipped_epub3(tmp_path: Path) -> None:
    """Okładka EPUB 3 (properties=cover-image) jest pomijana przy skip_cover."""
    path = _build_epub(
        tmp_path,
        {"images/cover.jpg": _jpeg_bytes(), "images/body.jpg": _jpeg_bytes()},
        cover_href="images/cover.jpg",
        cover_mode="epub3",
    )
    with Epub(path) as epub:
        original_cover = epub.read_file("OEBPS/images/cover.jpg")
        report = optimize_images(epub, ImageFixOptions(max_px=1200, skip_cover=True))
        assert epub.read_file("OEBPS/images/cover.jpg") == original_cover
        assert "OEBPS/images/body.jpg" in report.changed_files
        assert "OEBPS/images/cover.jpg" not in report.changed_files


def test_cover_skipped_epub2(tmp_path: Path) -> None:
    """Okładka EPUB 2 (meta name=cover) jest pomijana przy skip_cover."""
    path = _build_epub(
        tmp_path,
        {"images/cover.jpg": _jpeg_bytes(), "images/body.jpg": _jpeg_bytes()},
        cover_href="images/cover.jpg",
        cover_mode="epub2",
    )
    with Epub(path) as epub:
        original_cover = epub.read_file("OEBPS/images/cover.jpg")
        optimize_images(epub, ImageFixOptions(max_px=1200, skip_cover=True))
        assert epub.read_file("OEBPS/images/cover.jpg") == original_cover


def test_cover_optimized_when_not_skipped(tmp_path: Path) -> None:
    """Przy skip_cover=False okładka też jest optymalizowana."""
    path = _build_epub(
        tmp_path,
        {"images/cover.jpg": _jpeg_bytes()},
        cover_href="images/cover.jpg",
        cover_mode="epub3",
    )
    with Epub(path) as epub:
        report = optimize_images(epub, ImageFixOptions(max_px=1200, skip_cover=False))
        assert "OEBPS/images/cover.jpg" in report.changed_files


def test_exif_stripped(tmp_path: Path) -> None:
    """Przy strip_metadata EXIF jest usuwany z wynikowego JPEG."""
    exif = Image.Exif()
    exif[271] = "EpubForgeTest"  # tag Make
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes(exif=exif.tobytes())})
    with Epub(path) as epub:
        optimize_images(epub, ImageFixOptions(max_px=1200, strip_metadata=True))
        assert len(_reopen(epub, "images/a.jpg").getexif()) == 0


def test_grayscale_converts_mode(tmp_path: Path) -> None:
    """Grayscale konwertuje obraz do skali szarości."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes()})
    with Epub(path) as epub:
        optimize_images(epub, ImageFixOptions(max_px=1200, grayscale=True))
        assert _reopen(epub, "images/a.jpg").mode == "L"


def test_svg_ignored(tmp_path: Path) -> None:
    """SVG (tekst) nie jest przetwarzany — brak w raporcie."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes()})
    # Dodaj SVG do EPUB-a poza obiegiem obrazów rastrowych.
    with Epub(path) as epub:
        epub.write_file("OEBPS/images/logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        report = optimize_images(epub, ImageFixOptions())
        assert all("logo.svg" not in result.internal_path for result in report.results)


def test_report_totals(tmp_path: Path) -> None:
    """Raport liczy sumy, oszczędność i procent poprawnie."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes()})
    with Epub(path) as epub:
        report = optimize_images(epub, ImageFixOptions(max_px=1200))
        assert report.saved_bytes == report.total_before - report.total_after
        assert report.saved_bytes > 0
        assert 0 < report.saved_percent <= 100
        assert report.changed_files == ["OEBPS/images/a.jpg"]


def test_missing_pillow_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak Pillow → czytelny ImageOptimizationError z instrukcją instalacji."""
    path = _build_epub(tmp_path, {"images/a.jpg": _jpeg_bytes((64, 64))})
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("Pillow intentionally unavailable")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with Epub(path) as epub, pytest.raises(ImageOptimizationError):
        optimize_images(epub, ImageFixOptions())
