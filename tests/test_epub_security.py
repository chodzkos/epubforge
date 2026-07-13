"""Testy bezpiecznego modelu niezaufanego EPUB-a (walidacja archiwum + strumień).

Pokrywają: bombę ZIP i wysoki współczynnik kompresji, zbyt wiele wpisów, duplikaty,
traversal/niekanoniczne nazwy, zaszyfrowany wpis, zbyt duży pojedynczy wpis i sumę,
limit XML/tekstu, poprawny duży EPUB oraz dwa kryteria: odrzucenie PRZED dekompresją
i stały narzut pamięci przy zapisie (kopia strumieniowa).
"""

from __future__ import annotations

import tracemalloc
import warnings
import zipfile
from pathlib import Path

import pytest

from epubforge.core._archive import ArchiveLimits, validate_archive
from epubforge.core.epub import Epub
from epubforge.core.exceptions import ResourceLimitError

_CONTAINER_XML = (
    b'<?xml version="1.0"?>\n'
    b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    b'  <rootfiles><rootfile full-path="OEBPS/content.opf"'
    b' media-type="application/oebps-package+xml"/></rootfiles>\n'
    b"</container>\n"
)
_OPF = (
    b'<?xml version="1.0"?>\n'
    b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">\n'
    b'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b'<dc:title>T</dc:title><dc:identifier id="id">x</dc:identifier></metadata>\n'
    b'  <manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>\n'
    b'  <spine><itemref idref="c1"/></spine>\n'
    b"</package>\n"
)
_CHAPTER = b"<html><body><p>Ala ma kota.</p></body></html>"

Entry = tuple[str, bytes, int]


def _make_epub(path: Path, extra: list[Entry] | None = None) -> Path:
    """Buduje minimalny, poprawny EPUB; ``extra`` dokłada wpisy ``(nazwa, dane, compress)``."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/ch1.xhtml", _CHAPTER)
        for name, data, compress in extra or []:
            info = zipfile.ZipInfo(name)
            info.compress_type = compress
            zf.writestr(info, data)
    return path


def _open_zip_with_entry(path: Path, name: str, data: bytes, compress: int) -> None:
    """Zapisuje ZIP z jednym jawnie nazwanym wpisem (do testów niekanonicznych nazw)."""
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo(name)
        info.compress_type = compress
        zf.writestr(info, data)


class _FakeZip:
    """Atrapa ``ZipFile`` zwracająca spreparowane ``infolist`` — dla wpisów, których
    prawdziwe ``zipfile.writestr`` nie odtwarza wiernie (NUL w nazwie, flaga szyfrowania)."""

    def __init__(self, infos: list[zipfile.ZipInfo]) -> None:
        self._infos = infos

    def infolist(self) -> list[zipfile.ZipInfo]:
        return self._infos


def _info(
    name: str, *, file_size: int = 10, compress_size: int = 10, encrypted: bool = False
) -> zipfile.ZipInfo:
    """Buduje ``ZipInfo`` z jawnymi rozmiarami/flagą (walidacja patrzy tylko na metadane)."""
    info = zipfile.ZipInfo(name)
    info.file_size = file_size
    info.compress_size = compress_size
    if encrypted:
        info.flag_bits |= 0x1
    return info


# ── Walidacja: budżety ──────────────────────────────────────────────────────


def test_valid_epub_passes_validation(tmp_path: Path) -> None:
    """Poprawny EPUB przechodzi walidację i otwiera się normalnie."""
    path = _make_epub(tmp_path / "ok.epub")
    with Epub(path) as epub:
        assert epub.opf_path == "OEBPS/content.opf"
        assert epub.metadata.title == "T"


def test_too_many_entries_rejected(tmp_path: Path) -> None:
    """Liczba wpisów powyżej ``max_entries`` → ResourceLimitError."""
    path = _make_epub(
        tmp_path / "many.epub", extra=[(f"OEBPS/f{i}.txt", b"x", 0) for i in range(4)]
    )
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        validate_archive(zf, ArchiveLimits(max_entries=5))


def test_total_uncompressed_budget_rejected(tmp_path: Path) -> None:
    """Suma rozmiarów nieskompresowanych powyżej limitu → ResourceLimitError."""
    path = _make_epub(tmp_path / "big.epub", extra=[("OEBPS/big.bin", b"A" * 4096, 0)])
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match="Suma rozmiarów"):
        validate_archive(zf, ArchiveLimits(max_total_uncompressed=2048))


def test_single_entry_size_rejected(tmp_path: Path) -> None:
    """Pojedynczy wpis powyżej ``max_entry_size`` → ResourceLimitError."""
    path = _make_epub(tmp_path / "img.epub", extra=[("OEBPS/big.png", b"P" * 8192, 0)])
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match="limit rozmiaru"):
        validate_archive(zf, ArchiveLimits(max_entry_size=4096))


def test_high_compression_ratio_rejected(tmp_path: Path) -> None:
    """Ekstremalny współczynnik kompresji (bomba ZIP) → ResourceLimitError."""
    bomb = b"\x00" * (1024 * 1024)  # 1 MiB zer → kompresuje się ~1000x
    path = _make_epub(
        tmp_path / "bomb.epub", extra=[("OEBPS/bomb.bin", bomb, zipfile.ZIP_DEFLATED)]
    )
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match="bomba ZIP"):
        validate_archive(zf, ArchiveLimits(max_compression_ratio=50))


def test_encrypted_entry_rejected() -> None:
    """Wpis oznaczony jako zaszyfrowany (bit flagi) → ResourceLimitError.

    ``writestr`` przelicza ``flag_bits`` przy zapisie, więc flagę szyfrowania
    testujemy na spreparowanym ``ZipInfo`` (walidacja i tak patrzy tylko na metadane).
    """
    fake = _FakeZip([_info("OEBPS/secret.xhtml", encrypted=True)])
    with pytest.raises(ResourceLimitError, match="Zaszyfrowany"):
        validate_archive(fake)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("filename", "match"),
    [
        ("bad\x00name.xhtml", "NUL"),  # ZipInfo ucina nazwę na NUL
        ("OEBPS\\win.xhtml", "backslash"),  # ZipInfo/zipfile zamienia os.sep '\\' → '/'
    ],
)
def test_unsafe_name_via_metadata_rejected(filename: str, match: str) -> None:
    """Nazwy, których realny ZIP normalizuje (NUL, backslash), testujemy na metadanych.

    ``ZipInfo(...)`` i ``writestr`` sanityzują te znaki (m.in. na Windows ``\\`` → ``/``),
    więc ustawiamy ``filename`` wprost — walidacja i tak patrzy tylko na metadane.
    """
    info = _info("placeholder.xhtml")
    info.filename = filename
    with pytest.raises(ResourceLimitError, match=match):
        validate_archive(_FakeZip([info]))  # type: ignore[arg-type]


# ── Walidacja: nazwy ────────────────────────────────────────────────────────


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    """Zdublowana nazwa wpisu → ResourceLimitError."""
    path = tmp_path / "dup.epub"
    with zipfile.ZipFile(path, "w") as zf, warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # duplikat jest celowy
        zf.writestr("OEBPS/a.xhtml", b"1")
        zf.writestr("OEBPS/a.xhtml", b"2")
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match="Zdublowana"):
        validate_archive(zf)


@pytest.mark.parametrize(
    ("name", "match"),
    [
        ("../evil.xhtml", "poza archiwum"),
        ("OEBPS/../../etc/passwd", "poza archiwum"),
        ("/abs/path.xhtml", "absolutna"),
        ("C:/win/path.xhtml", "absolutna"),
        ("OEBPS/./x.xhtml", "segment '.'"),
        ("OEBPS//x.xhtml", "pusty segment"),
    ],
)
def test_noncanonical_names_rejected(tmp_path: Path, name: str, match: str) -> None:
    """Niekanoniczne/niebezpieczne nazwy wpisów są odrzucane."""
    path = tmp_path / "bad.epub"
    _open_zip_with_entry(path, name, b"data", zipfile.ZIP_STORED)
    with zipfile.ZipFile(path) as zf, pytest.raises(ResourceLimitError, match=match):
        validate_archive(zf)


def test_directory_entry_trailing_slash_allowed(tmp_path: Path) -> None:
    """Wpis-katalog z końcowym ``/`` jest dozwolony (pusty segment tylko końcowy)."""
    path = tmp_path / "dir.epub"
    _open_zip_with_entry(path, "OEBPS/", b"", zipfile.ZIP_STORED)
    with zipfile.ZipFile(path) as zf:
        validate_archive(zf)  # nie rzuca


# ── Kryteria z audytu ───────────────────────────────────────────────────────


def test_rejection_happens_before_decompression(tmp_path: Path) -> None:
    """Odrzucenie następuje na metadanych — walidacja nie czyta/dekompresuje wpisów."""
    bomb = b"\x00" * (2 * 1024 * 1024)
    path = _make_epub(tmp_path / "bomb2.epub", extra=[("OEBPS/b.bin", bomb, zipfile.ZIP_DEFLATED)])
    with zipfile.ZipFile(path) as zf:

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("walidacja zdekompresowała wpis przed odrzuceniem!")

        zf.read = _boom  # type: ignore[method-assign]
        zf.open = _boom  # type: ignore[method-assign]
        with pytest.raises(ResourceLimitError):
            validate_archive(zf, ArchiveLimits(max_compression_ratio=50))


def test_save_peak_memory_independent_of_largest_entry(tmp_path: Path) -> None:
    """Pamięć szczytowa zapisu nie rośnie z rozmiarem największego niezmienionego wpisu.

    Duży (16 MiB), nieściśliwy, niezmieniony wpis kopiujemy strumieniowo (bufor 1 MiB).
    Szczyt alokacji Pythona przy ``save`` musi być znacznie mniejszy niż rozmiar wpisu
    (dawny ``zin.read`` alokował cały wpis → szczyt ~16 MiB).
    """
    import os

    big = os.urandom(16 * 1024 * 1024)  # nieściśliwy → STORED, ratio ~1, przechodzi walidację
    src = _make_epub(tmp_path / "big.epub", extra=[("OEBPS/big.bin", big, zipfile.ZIP_STORED)])
    out = tmp_path / "out.epub"

    with Epub(src) as epub:
        epub.write_file("OEBPS/ch1.xhtml", b"<html><body><p>zmiana</p></body></html>")
        tracemalloc.start()
        epub.save(output_path=out)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    assert peak < 4 * 1024 * 1024, f"szczyt {peak} B — kopia nie jest strumieniowa"
    # Wynik jest nadal poprawnym EPUB-em z zachowanym dużym wpisem.
    with Epub(out) as epub:
        assert epub.read_file("OEBPS/big.bin") == big
        assert b"zmiana" in epub.read_file("OEBPS/ch1.xhtml")


# ── Integracja przez Epub ───────────────────────────────────────────────────


def test_open_rejects_bomb_epub(tmp_path: Path) -> None:
    """``Epub.open`` odrzuca bombę ZIP przez ResourceLimitError (przed odczytem treści)."""
    bomb = b"\x00" * (1024 * 1024)
    path = _make_epub(tmp_path / "b.epub", extra=[("OEBPS/b.bin", bomb, zipfile.ZIP_DEFLATED)])
    with pytest.raises(ResourceLimitError):
        Epub(path, limits=ArchiveLimits(max_compression_ratio=50)).open()


def test_raised_limits_allow_large_entry(tmp_path: Path) -> None:
    """Świadome podniesienie limitów przepuszcza duży (ale niezłośliwy) wpis."""
    payload = b"P" * (256 * 1024)
    path = _make_epub(
        tmp_path / "large.epub", extra=[("OEBPS/big.png", payload, zipfile.ZIP_STORED)]
    )
    # Domyślnie OK; przy sztucznie zaniżonym limicie — odrzucone; po podniesieniu — znowu OK.
    with pytest.raises(ResourceLimitError):
        Epub(path, limits=ArchiveLimits(max_entry_size=1024)).open()
    with Epub(path, limits=ArchiveLimits(max_entry_size=1024 * 1024)) as epub:
        assert len(epub.read_file("OEBPS/big.png")) == len(payload)


def test_oversized_xml_rejected_on_parse(tmp_path: Path) -> None:
    """Odczyt OPF-a większego niż ``max_text_size`` → ResourceLimitError przy parsowaniu."""
    path = _make_epub(tmp_path / "xml.epub")
    # Limit tekstu poniżej rozmiaru OPF-a; wpis mieści się w max_entry_size, więc open() OK,
    # ale próba parsowania metadanych czyta OPF z limitem tekstu.
    with (
        Epub(path, limits=ArchiveLimits(max_text_size=16)) as epub,
        pytest.raises(ResourceLimitError, match="XML/tekst"),
    ):
        _ = epub.metadata
