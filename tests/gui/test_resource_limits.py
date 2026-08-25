"""Granice pamięci materializacji zasobów GUI."""

from __future__ import annotations

import struct

from epubforge.gui.resource_limits import (
    MAX_DECODED_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    RasterStatus,
    probe_raster,
    utf8_fits,
)


def _bmp_metadata(width: int, height: int) -> bytes:
    """Buduje mały nagłówek BMP ujawniający wymiary bez bufora pikseli."""
    header_size = 14 + 40
    file_header = b"BM" + struct.pack("<IHHI", header_size, 0, 0, header_size)
    dib_header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0, 0, 0, 0, 0, 0)
    return file_header + dib_header


def test_utf8_budget_allows_exact_bytes_and_rejects_one_more() -> None:
    assert utf8_fits("ą" * 4, 8)
    assert not utf8_fits("ą" * 4 + "x", 8)


def test_raster_exact_pixel_limit_is_allowed() -> None:
    probe = probe_raster(_bmp_metadata(8_000, 4_000))
    assert probe.status is RasterStatus.OK
    assert probe.pixels == MAX_IMAGE_PIXELS
    assert probe.decoded_bytes <= MAX_DECODED_IMAGE_BYTES


def test_raster_pixel_limit_plus_one_row_is_rejected() -> None:
    probe = probe_raster(_bmp_metadata(8_000, 4_001))
    assert probe.status is RasterStatus.TOO_LARGE
    assert probe.pixels > MAX_IMAGE_PIXELS


def test_small_encoded_raster_with_huge_dimensions_is_rejected() -> None:
    data = _bmp_metadata(9_000, 9_000)
    assert len(data) < 1_024
    probe = probe_raster(data)
    assert probe.status is RasterStatus.TOO_LARGE
    assert probe.decoded_bytes > MAX_DECODED_IMAGE_BYTES


def test_malformed_raster_has_controlled_status() -> None:
    probe = probe_raster(b"not-an-image")
    assert probe.status is RasterStatus.INVALID
    assert probe.width == probe.height == probe.pixels == probe.decoded_bytes == 0
