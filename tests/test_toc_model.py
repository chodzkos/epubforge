"""Testy czystego modelu spisu treści (move_entry + nawigacja po drzewie)."""

from __future__ import annotations

import pytest

from epubforge.toc import TocEntry, move_entry, parent_of, siblings_of


def _tree() -> list[TocEntry]:
    """Buduje proste drzewo: A(>A1, A2), B."""
    a1 = TocEntry("A1", "a1.xhtml")
    a2 = TocEntry("A2", "a2.xhtml")
    a = TocEntry("A", "a.xhtml", [a1, a2])
    b = TocEntry("B", "b.xhtml")
    return [a, b]


def _titles(entries: list[TocEntry]) -> list[object]:
    """Zwraca zagnieżdżoną listę tytułów do porównań w testach."""
    return [(e.title, _titles(e.children)) if e.children else e.title for e in entries]


def test_move_before_sibling() -> None:
    """before: B przed A na najwyższym poziomie."""
    tree = _tree()
    a, b = tree[0], tree[1]
    move_entry(tree, b, a, "before")
    assert [e.title for e in tree] == ["B", "A"]


def test_move_after_sibling() -> None:
    """after: A1 trafia po A2 wewnątrz A."""
    tree = _tree()
    a = tree[0]
    a1, a2 = a.children[0], a.children[1]
    move_entry(tree, a1, a2, "after")
    assert [c.title for c in a.children] == ["A2", "A1"]


def test_move_into_makes_child() -> None:
    """into: B staje się dzieckiem A (na końcu jego dzieci)."""
    tree = _tree()
    a, b = tree[0], tree[1]
    move_entry(tree, b, a, "into")
    assert [e.title for e in tree] == ["A"]
    assert [c.title for c in a.children] == ["A1", "A2", "B"]


def test_move_into_own_descendant_raises() -> None:
    """Zakaz przeniesienia wpisu do własnego potomka."""
    tree = _tree()
    a = tree[0]
    a1 = a.children[0]
    with pytest.raises(ValueError, match="potomka"):
        move_entry(tree, a, a1, "into")


def test_move_onto_self_raises() -> None:
    """Przeniesienie na samego siebie jest błędem."""
    tree = _tree()
    a = tree[0]
    with pytest.raises(ValueError):
        move_entry(tree, a, a, "after")


def test_siblings_and_parent() -> None:
    """siblings_of i parent_of zwracają poprawne położenie węzła."""
    tree = _tree()
    a = tree[0]
    a2 = a.children[1]
    siblings = siblings_of(tree, a2)
    assert siblings is not None
    items, index = siblings
    assert items is a.children
    assert index == 1
    assert parent_of(tree, a2) is a
    assert parent_of(tree, a) is None  # najwyższy poziom
