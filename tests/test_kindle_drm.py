"""Testy detektora DRM Kindle — syntetyczne nagłówki (żadnych prawdziwych mobi)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from epubforge.converters.kindle_drm import has_kindle_drm


def _make_mobi(encryption: int, *, with_magic: bool = True, num_records: int = 1) -> bytes:
    """Buduje minimalny nagłówek PalmDB + rekord 0 MOBI z danym typem szyfrowania."""
    header = bytearray(78)
    struct.pack_into(">H", header, 76, num_records)  # liczba rekordów
    # Zawsze dokładamy jeden wpis listy rekordów (8 bajtów), nawet gdy
    # num_records=0 — detektor i tak odrzuci plik na liczbie rekordów < 1.
    record0_offset = 78 + 8 * max(num_records, 1)
    entry = struct.pack(">I", record0_offset) + b"\x00\x00\x00\x00"  # offset + atrybuty/uid
    record0 = bytearray(20)
    struct.pack_into(">H", record0, 12, encryption)  # typ szyfrowania
    if with_magic:
        record0[16:20] = b"MOBI"
    padding = bytes(record0_offset - (78 + len(entry)))  # wyrównanie do offsetu rekordu 0
    return bytes(header) + entry + padding + bytes(record0)


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(("encryption", "expected"), [(0, False), (1, True), (2, True)])
def test_encryption_type_detected(tmp_path: Path, encryption: int, expected: bool) -> None:
    """Typ szyfrowania 0 = brak DRM; 1/2 = DRM."""
    book = _write(tmp_path, "b.mobi", _make_mobi(encryption))
    assert has_kindle_drm(book) is expected


def test_too_short_file_is_not_drm(tmp_path: Path) -> None:
    """Plik krótszy niż nagłówek PalmDB → False (niech zdecyduje Calibre)."""
    book = _write(tmp_path, "s.mobi", b"0123456789")
    assert has_kindle_drm(book) is False


def test_missing_mobi_magic_is_not_drm(tmp_path: Path) -> None:
    """Brak magicu MOBI w rekordzie 0 → False, nawet przy typie szyfrowania 1."""
    book = _write(tmp_path, "nm.mobi", _make_mobi(1, with_magic=False))
    assert has_kindle_drm(book) is False


def test_zero_records_is_not_drm(tmp_path: Path) -> None:
    """Nagłówek deklarujący 0 rekordów → False."""
    book = _write(tmp_path, "z.mobi", _make_mobi(1, num_records=0))
    assert has_kindle_drm(book) is False


def test_missing_file_is_not_drm(tmp_path: Path) -> None:
    """Nieistniejący plik → False (błąd odczytu nie jest DRM)."""
    assert has_kindle_drm(tmp_path / "nope.mobi") is False
