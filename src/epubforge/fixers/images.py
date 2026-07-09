"""Optymalizacja obrazów w EPUB — skalowanie, rekompresja, skala szarości.

Cel: odchudzenie EPUB-a pod czytniki e-ink. Pillow jest importowane **leniwie**
(extra ``[images]``), więc brak biblioteki nie psuje importu pakietu — dopiero
próba optymalizacji zgłasza czytelny błąd z instrukcją instalacji.

Zasady bezpieczeństwa (pułapki Etapu 20):
- **format pliku nigdy się nie zmienia** (jpg→jpg, png→png) — zmiana wymagałaby
  przepisania manifestu i wszystkich ``src`` w XHTML;
- **zapis tylko gdy wynik mniejszy** od oryginału (idempotentność, brak regresu
  dla już zoptymalizowanych plików);
- **okładka** rozpoznawana (EPUB 3 ``properties="cover-image"`` / EPUB 2
  ``<meta name="cover">``) i pomijana przy ``skip_cover``;
- **PNG z alfą** zachowuje kanał alfa; **paleta** (tryb ``P``) zostaje paletą;
- **SVG** pomijane (to tekst, nie raster).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urldefrag

from epubforge.core import Epub, ManifestItem
from epubforge.core._xml_safe import parse_untrusted
from epubforge.i18n import _

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

_OPF_NS = "http://www.idpf.org/2007/opf"

_JPEG_SUFFIXES = {".jpg", ".jpeg"}
_PNG_SUFFIXES = {".png"}
_JPEG_MEDIA_TYPES = {"image/jpeg", "image/jpg"}
_PNG_MEDIA_TYPES = {"image/png"}
_DEFAULT_FORMATS = frozenset({".jpg", ".jpeg", ".png"})


class ImageOptimizationError(RuntimeError):
    """Błąd optymalizacji obrazów (np. brak biblioteki Pillow)."""


@dataclass
class ImageFixOptions:
    """Opcje optymalizacji obrazów w EPUB.

    Attributes:
        max_px: maksymalny dłuższy bok w pikselach; ``None`` = bez skalowania.
        jpeg_quality: jakość zapisu JPEG (1-95).
        grayscale: konwersja do skali szarości (pod e-ink) — tylko na żądanie.
        strip_metadata: zapis bez EXIF/ICC (mniejszy plik).
        skip_cover: pomiń okładkę (zostaw w pełnej jakości).
        formats: rozszerzenia plików brane pod uwagę (małe litery, z kropką).
    """

    max_px: int | None = 1200
    jpeg_quality: int = 75
    grayscale: bool = False
    strip_metadata: bool = True
    skip_cover: bool = True
    formats: set[str] = field(default_factory=lambda: set(_DEFAULT_FORMATS))


@dataclass(frozen=True)
class ImageResult:
    """Wynik optymalizacji jednego obrazu."""

    internal_path: str
    size_before: int
    size_after: int
    changed: bool


@dataclass
class ImageReport:
    """Zbiorczy raport optymalizacji obrazów."""

    results: list[ImageResult] = field(default_factory=list)

    def record(self, result: ImageResult) -> None:
        """Dodaje wynik pojedynczego pliku do raportu."""
        self.results.append(result)

    @property
    def total_before(self) -> int:
        """Sumaryczny rozmiar przetworzonych obrazów przed optymalizacją."""
        return sum(result.size_before for result in self.results)

    @property
    def total_after(self) -> int:
        """Sumaryczny rozmiar przetworzonych obrazów po optymalizacji."""
        return sum(result.size_after for result in self.results)

    @property
    def saved_bytes(self) -> int:
        """Liczba zaoszczędzonych bajtów (≥ 0)."""
        return self.total_before - self.total_after

    @property
    def saved_percent(self) -> float:
        """Procent oszczędności względem rozmiaru wejściowego (0 gdy brak danych)."""
        before = self.total_before
        if before <= 0:
            return 0.0
        return round(self.saved_bytes / before * 100, 1)

    @property
    def changed_files(self) -> list[str]:
        """Ścieżki plików faktycznie zmniejszonych."""
        return [result.internal_path for result in self.results if result.changed]


def optimize_images(epub: Epub, options: ImageFixOptions) -> ImageReport:
    """Optymalizuje obrazy JPEG/PNG w otwartym EPUB-ie.

    Args:
        epub: otwarty plik EPUB (zmiany trafiają do bufora ``write_file``).
        options: parametry optymalizacji.

    Returns:
        :class:`ImageReport` z rozmiarami przed/po dla każdego przetworzonego pliku.

    Raises:
        ImageOptimizationError: gdy Pillow nie jest zainstalowane.
    """
    image = _load_pillow()  # wczesny, czytelny błąd gdy brak Pillow
    report = ImageReport()
    cover_paths = _cover_paths(epub) if options.skip_cover else set()
    formats = {suffix.lower() for suffix in options.formats}

    for item in _image_items(epub, formats):
        internal_path = _manifest_path(epub, item)
        if internal_path in cover_paths:
            continue
        suffix = _href_suffix(item.href)
        original = epub.read_file(internal_path)
        optimized = _optimize_bytes(image, original, suffix, options)
        if optimized is not None and len(optimized) < len(original):
            epub.write_file(internal_path, optimized)
            report.record(ImageResult(internal_path, len(original), len(optimized), changed=True))
        else:
            report.record(ImageResult(internal_path, len(original), len(original), changed=False))
    return report


def _load_pillow() -> Any:
    """Zwraca moduł ``PIL.Image`` albo zgłasza czytelny błąd z instrukcją instalacji."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - zależne od środowiska
        raise ImageOptimizationError(
            _(
                'Optymalizacja obrazów wymaga biblioteki Pillow. Zainstaluj: pip install "epubforge[images]"'
            )
        ) from exc
    return Image


def _optimize_bytes(
    image: Any,
    data: bytes,
    suffix: str,
    options: ImageFixOptions,
) -> bytes | None:
    """Rekompresuje obraz z zachowaniem formatu; ``None`` gdy pliku nie da się otworzyć."""
    fmt = "JPEG" if suffix in _JPEG_SUFFIXES else "PNG"
    try:
        with image.open(BytesIO(data)) as img:
            img.load()
            transformed = _transform(image, img, fmt, options)
            return _encode(transformed, fmt, options)
    except (OSError, ValueError):  # nieczytelny/uszkodzony obraz — pomiń bezpiecznie
        return None


def _transform(image: Any, img: PILImage, fmt: str, options: ImageFixOptions) -> PILImage:
    """Skaluje i (opcjonalnie) konwertuje tryb obrazu, zachowując alfę i paletę."""
    if options.max_px is not None:
        img = _resize(image, img, options.max_px)
    if options.grayscale:
        # Skala szarości na wyraźne żądanie — zachowujemy alfę jako „LA".
        return img.convert("LA" if _has_alpha(img) else "L")
    if fmt == "JPEG" and img.mode in {"RGBA", "LA", "P"}:
        # JPEG nie obsługuje alfy/palety — spłaszczamy do RGB.
        return img.convert("RGB")
    # PNG: zostawiamy tryb bez zmian (RGBA/P/L…), by nie zgubić alfy ani palety.
    return img


def _resize(image: Any, img: PILImage, max_px: int) -> PILImage:
    """Skaluje obraz tak, by dłuższy bok nie przekraczał ``max_px`` (LANCZOS)."""
    width, height = img.size
    longest = max(width, height)
    if longest <= max_px:
        return img
    scale = max_px / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return img.resize(new_size, image.Resampling.LANCZOS)


def _encode(img: PILImage, fmt: str, options: ImageFixOptions) -> bytes:
    """Zapisuje obraz do bajtów w tym samym formacie, respektując strip_metadata."""
    buffer = BytesIO()
    save_kwargs: dict[str, Any] = {"optimize": True}
    if fmt == "JPEG":
        save_kwargs["quality"] = options.jpeg_quality
        save_kwargs["progressive"] = True
    if not options.strip_metadata:
        exif = img.info.get("exif")
        icc = img.info.get("icc_profile")
        if exif:
            save_kwargs["exif"] = exif
        if icc:
            save_kwargs["icc_profile"] = icc
    if fmt == "PNG" and img.mode == "P" and "transparency" in img.info:
        save_kwargs["transparency"] = img.info["transparency"]
    img.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def _has_alpha(img: PILImage) -> bool:
    """Czy obraz ma kanał alfa (RGBA/LA lub paleta z przezroczystością)."""
    if img.mode in {"RGBA", "LA"}:
        return True
    return img.mode == "P" and "transparency" in img.info


def _cover_paths(epub: Epub) -> set[str]:
    """Zwraca wewnętrzne ścieżki okładek (EPUB 3 properties + EPUB 2 meta name=cover)."""
    paths: set[str] = set()
    cover_ids: set[str] = set()
    for item in epub.manifest:
        if item.properties and "cover-image" in item.properties.split():
            paths.add(_manifest_path(epub, item))

    root = parse_untrusted(epub.read_file(epub.opf_path))
    for meta in root.iterfind(f"{{{_OPF_NS}}}metadata/{{{_OPF_NS}}}meta"):
        if meta.get("name") == "cover":
            content = meta.get("content")
            if content:
                cover_ids.add(content)
    if cover_ids:
        for item in epub.manifest:
            if item.id in cover_ids:
                paths.add(_manifest_path(epub, item))
    return paths


def _image_items(epub: Epub, formats: set[str]) -> list[ManifestItem]:
    """Zwraca wpisy manifestu wskazujące obrazy JPEG/PNG objęte optymalizacją."""
    allowed_media = _JPEG_MEDIA_TYPES | _PNG_MEDIA_TYPES
    items: list[ManifestItem] = []
    for item in epub.manifest:
        suffix = _href_suffix(item.href)
        if suffix not in formats:
            continue
        if suffix in _JPEG_SUFFIXES or suffix in _PNG_SUFFIXES or item.media_type in allowed_media:
            items.append(item)
    return items


def _href_suffix(href: str) -> str:
    """Zwraca rozszerzenie href (bez fragmentu URL), małymi literami."""
    path, _fragment = urldefrag(href)
    return Path(unquote(path)).suffix.lower()


def _manifest_path(epub: Epub, item: ManifestItem) -> str:
    """Rozwiązuje ``manifest href`` względem katalogu OPF (wzorzec z css_fixer)."""
    href, _fragment = urldefrag(item.href)
    href = unquote(href)
    if href.startswith("/"):
        return posixpath.normpath(href.lstrip("/"))
    base = epub.opf_dir()
    if not base:
        return posixpath.normpath(href)
    return posixpath.normpath(posixpath.join(base, href))
