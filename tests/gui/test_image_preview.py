"""Regresje limitów dekodowania bezpośredniego podglądu obrazu."""

from __future__ import annotations

import struct

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.widgets import image_preview as image_preview_module
from epubforge.gui.widgets.image_preview import ImagePreview

pytestmark = pytest.mark.gui


def _bmp_metadata(width: int, height: int) -> bytes:
    """Mały nagłówek z wymiarami, bez kosztownego rastra."""
    header_size = 54
    return (
        b"BM"
        + struct.pack("<IHHI", header_size, 0, 0, header_size)
        + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0, 0, 0, 0, 0, 0)
    )


def test_oversized_dimensions_reject_before_qpixmap(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Małe encoded bytes z 81 MP odpadają przed utworzeniem/dekodem QPixmap."""

    class ForbiddenPixmap:
        def __init__(self) -> None:
            pytest.fail("QPixmap nie może powstać dla rastra ponad budżetem")

    monkeypatch.setattr(image_preview_module, "QPixmap", ForbiddenPixmap)
    preview = ImagePreview()
    qtbot.addWidget(preview)

    assert not preview.show_data(_bmp_metadata(9_000, 9_000))
    assert "zbyt duży" in preview._label.text().lower()


def test_malformed_image_is_controlled_failure(qtbot: QtBot) -> None:
    preview = ImagePreview()
    qtbot.addWidget(preview)
    assert not preview.show_data(b"not-an-image")
    assert "nie udało" in preview._label.text().lower()
