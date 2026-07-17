"""Testy dostępności WebEngine, pre-init, backendu tekstowego i widoku dzielonego."""

from __future__ import annotations

import importlib.util

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.preview import availability, preinit
from epubforge.gui.preview.backend import PreviewSnapshot, PreviewState
from epubforge.gui.preview.text_backend import TextDocumentPreviewBackend

pytestmark = pytest.mark.gui


def test_probe_unavailable_when_spec_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak modułu (find_spec → None) daje available=False z powodem."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    probe = availability.probe_webengine()
    assert probe.available is False
    assert probe.reason


def test_probe_unavailable_on_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd wyszukiwania modułu jest łapany, nie propagowany."""

    def _raise(_name: str) -> object:
        raise ModuleNotFoundError("PySide6")

    monkeypatch.setattr(importlib.util, "find_spec", _raise)
    assert availability.probe_webengine().available is False


def test_preinit_is_noop_and_idempotent_without_webengine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bez WebEngine pre-init jest no-opem i można go wołać wielokrotnie."""
    monkeypatch.setattr(preinit, "_registered", False)
    monkeypatch.setattr(
        preinit, "probe_webengine", lambda: availability.WebEngineProbe(False, "brak")
    )
    assert preinit.preinit_webengine() is False
    assert preinit.preinit_webengine() is False  # idempotentne, bez wyjątku


def test_text_backend_capture_restore_roundtrip(qtbot: QtBot) -> None:
    """Backend tekstowy zapisuje i odtwarza pozycję scrolla bez błędu."""
    backend = TextDocumentPreviewBackend()
    qtbot.addWidget(backend)
    backend.render(PreviewSnapshot("<html><body><p>a</p></body></html>", None, None))
    state = backend.capture_state()
    assert isinstance(state, PreviewState)
    backend.restore_state(state)  # nie może rzucić


def test_split_view_reparents_and_persists(qtbot: QtBot, tmp_path: object) -> None:
    """Włączenie/wyłączenie podziału przenosi podgląd i zapisuje preferencję."""
    from epubforge.core import ConfigStore
    from epubforge.gui.preview.settings import SPLIT_VIEW_KEY
    from epubforge.gui.tabs.editor import EditorTab
    from epubforge.gui.tabs.editor_preview import _PAGE_HTML

    store = ConfigStore("epubforge", path=tmp_path / "config.json")  # type: ignore[operator]
    tab = EditorTab(config=store)
    qtbot.addWidget(tab)

    assert tab.stack.indexOf(tab.book_preview) == _PAGE_HTML
    tab.split_view_button.setChecked(True)
    assert tab._split_active is True
    assert tab.stack.indexOf(tab.book_preview) == -1  # przeniesiony obok
    assert store[SPLIT_VIEW_KEY] is True

    tab.split_view_button.setChecked(False)
    assert tab._split_active is False
    assert tab.stack.indexOf(tab.book_preview) == _PAGE_HTML  # wraca na stronę stosu
    assert store[SPLIT_VIEW_KEY] is False


def test_split_preview_hidden_for_non_html(qtbot: QtBot, tmp_path: object) -> None:
    """W trybie dzielonym podgląd obok jest widoczny dla HTML, ukryty dla obrazu."""
    import zipfile
    from pathlib import Path

    from epubforge.gui.tabs.editor import EditorTab

    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f9b0000000049454e44ae426082"
    )
    book = Path(str(tmp_path)) / "b.epub"
    with zipfile.ZipFile(book, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0"?><container version="1.0" '
            b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            b'<rootfile full-path="OEBPS/content.opf" '
            b'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr(
            "OEBPS/content.opf",
            b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
            b'version="3.0" unique-identifier="i"><metadata '
            b'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
            b'<manifest><item id="h" href="ch.xhtml" media-type="application/xhtml+xml"/>'
            b'<item id="img" href="img/p.png" media-type="image/png"/></manifest>'
            b'<spine><itemref idref="h"/></spine></package>',
        )
        zf.writestr(
            "OEBPS/ch.xhtml",
            b'<?xml version="1.0" encoding="UTF-8"?><html '
            b'xmlns="http://www.w3.org/1999/xhtml"><head><title>R</title></head>'
            b"<body><p>x</p></body></html>",
        )
        zf.writestr("OEBPS/img/p.png", png)

    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab.split_view_button.setChecked(True)

    tab._select_path("OEBPS/ch.xhtml")
    assert not tab.book_preview.isHidden()  # HTML → podgląd obok widoczny
    tab._select_path("OEBPS/img/p.png")
    assert tab.book_preview.isHidden()  # obraz → podgląd obok ukryty
