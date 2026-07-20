"""Testy stabilnego mapowania DOM kopii renderowanej do źródła XHTML."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted_document
from epubforge.gui.preview.backend import PreviewSnapshot
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.dom_mapping import (
    NODE_ATTRIBUTE,
    SourceLocation,
    SourceNode,
    assign_render_node_ids,
    build_source_map,
    nearest_node_for_line,
)
from epubforge.gui.preview.rewrite import rewrite_xhtml
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.tabs.editor_preview import _PAGE_EDITOR

pytestmark = pytest.mark.gui

_CHAPTER = "OEBPS/text/chapter1.xhtml"
_SOURCE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>
    <section id="part" class="chapter lead">
      <p id="target">Akapit <em>wyróżniony</em>.</p>
    </section>
  </body>
</html>""".encode()
_HOSTILE = b"""<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body>
<script>document.body.dataset.bad = '1'</script>
<p id="after-script" class="lead">Bezpieczny akapit</p>
</body>
</html>"""


def _node_by_id(source_map: dict[str, SourceNode], element_id: str) -> SourceNode:
    return next(node for node in source_map.values() if node.element_id == element_id)


def test_mapping_is_deterministic_and_does_not_modify_source_tree() -> None:
    """Mapa i kopia dostają te same ID, lecz oryginalne drzewo pozostaje czyste."""
    source_map = build_source_map(_SOURCE, _CHAPTER)
    root, _doctype = parse_untrusted_document(_SOURCE)
    assert all(element.get(NODE_ATTRIBUTE) is None for element in root.iter())

    assign_render_node_ids(root, _CHAPTER)
    rendered_ids = {
        element.get(NODE_ATTRIBUTE) for element in root.iter() if isinstance(element.tag, str)
    }
    assert rendered_ids == set(source_map)
    target = _node_by_id(source_map, "target")
    assert target.short_label == "p#target"
    assert target.sourceline == 6


def test_nearest_line_prefers_the_deepest_element() -> None:
    """Linia z elementem zagnieżdżonym wskazuje najgłębszy dostępny węzeł."""
    source_map = build_source_map(_SOURCE, _CHAPTER)
    node = nearest_node_for_line(source_map, _CHAPTER, 6)
    assert node is not None
    assert node.tag == "em"


def test_sanitization_keeps_original_node_identity(sample_epub: Path) -> None:
    """Usunięty skrypt nie przesuwa ID elementu znajdującego się za nim."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    try:
        generation = session.advance(epub, _CHAPTER, {_CHAPTER: _HOSTILE})
        rendered = rewrite_xhtml(_HOSTILE, generation, _CHAPTER)
        root, _doctype = parse_untrusted_document(rendered)
        paragraph = root.xpath("//*[local-name()='p']")[0]
        source = _node_by_id(dict(generation.source_map), "after-script")
        assert paragraph.get(NODE_ATTRIBUTE) == source.node_id
        assert not root.xpath("//*[local-name()='script']")
        assert NODE_ATTRIBUTE.encode() not in _HOSTILE
    finally:
        session.close()
        epub.close()


def test_cursor_line_updates_session_selection(
    qtbot: QtBot, sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kursor wybiera element mapy bez renderowania nowej generacji."""
    settings = PreviewSettings()
    settings.backend = "text"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub)
    preview.set_session(session)
    generation = session.advance(epub, _CHAPTER, {_CHAPTER: _SOURCE})
    preview._last_snapshot = PreviewSnapshot(
        _SOURCE.decode(), epub, _CHAPTER, generation.generation_id, generation
    )
    focused: list[str] = []
    monkeypatch.setattr(preview._active, "focus_node", focused.append)

    preview.focus_source_line(_CHAPTER, 6)

    assert focused
    assert session.selection_state.element_key == focused[0]
    assert session.selection_state.internal_path == _CHAPTER
    session.close()
    epub.close()


def test_preview_location_switches_to_code_and_moves_cursor(
    qtbot: QtBot, sample_epub: Path
) -> None:
    """Kliknięty element przełącza pojedynczy widok na kod i ustawia linię."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(sample_epub)
    tab._select_path(_CHAPTER)
    tab.preview_view_button.setChecked(True)

    tab._on_preview_source_requested(
        SourceLocation(
            node_id="0123456789abcdef",
            internal_path=_CHAPTER,
            line=2,
            label="body",
            element_exact=True,
        )
    )

    assert tab.stack.currentIndex() == _PAGE_EDITOR
    assert tab.code_editor.editor.textCursor().blockNumber() == 1
    assert "body" in tab.info_bar.text()
