"""Testy czystych funkcji tokenizacji podświetlania (import wymaga PySide6).

Same ``xml_spans``/``css_spans`` działają na ``re`` (bez Qt), ale mieszkają w
module ``gui.widgets.syntax_highlight``, który importuje PySide6 — dlatego testy
biegają w torze GUI.
"""

from __future__ import annotations

import pytest

from epubforge.gui.widgets.syntax_highlight import css_spans, xml_spans

pytestmark = pytest.mark.gui


def test_xml_spans_kinds() -> None:
    """xml_spans rozpoznaje tag, atrybut, wartość i encję."""
    kinds = {kind for _s, _l, kind in xml_spans('<p class="a">&amp;</p>')}
    assert {"tag", "attribute", "value", "entity"} <= kinds


def test_css_spans_kinds() -> None:
    """css_spans rozpoznaje selektor, właściwość, wartość, @-regułę i !important."""
    kinds = {kind for _s, _l, kind in css_spans("@media{body{color:red !important;}}")}
    assert "atrule" in kinds
    assert "property" in kinds
    assert "important" in kinds
