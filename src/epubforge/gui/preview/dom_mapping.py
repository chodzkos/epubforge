"""Stabilna mapa elementów kopii renderowanej do źródła XHTML."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted_document

NODE_ATTRIBUTE = "data-epubforge-node-id"
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceNode:
    """Opis elementu źródłowego dostępny wyłącznie w pamięci sesji."""

    node_id: str
    internal_path: str
    sourceline: int | None
    approximate_anchor: str
    tag: str
    element_id: str | None
    classes: tuple[str, ...]
    text_fingerprint: str
    depth: int

    @property
    def short_label(self) -> str:
        """Zwraca krótką etykietę tag#id.class bez treści książki."""
        identifier = f"#{self.element_id}" if self.element_id else ""
        classes = "".join(f".{name}" for name in self.classes[:3])
        return f"{self.tag}{identifier}{classes}"


@dataclass(frozen=True)
class SourceLocation:
    """Bezpieczny cel przejścia z podglądu do edytora."""

    node_id: str
    internal_path: str
    line: int | None
    label: str
    element_exact: bool
    position_approximate: bool = True
    recovery_method: str = "node"


def build_source_map(data: bytes, internal_path: str) -> dict[str, SourceNode]:
    """Buduje mapę elementów z linii oryginalnego dokumentu, bez jego modyfikacji."""
    root, _doctype = parse_untrusted_document(data)
    return map_tree(root, internal_path, assign_attributes=False)


def assign_render_node_ids(root: etree._Element, internal_path: str) -> None:
    """Dodaje techniczne identyfikatory wyłącznie do drzewa kopii renderowanej."""
    map_tree(root, internal_path, assign_attributes=True)


def map_tree(
    root: etree._Element,
    internal_path: str,
    *,
    assign_attributes: bool,
) -> dict[str, SourceNode]:
    """Mapuje elementy istniejącego drzewa; komentarze nie zmieniają numerów linii."""
    tree = root.getroottree()
    result: dict[str, SourceNode] = {}
    for element in root.iter():
        tag_value = cast(object, element.tag)
        if not isinstance(tag_value, str):
            continue
        path = tree.getpath(element)
        node_id = _node_id(internal_path, element.get("id"), path)
        if assign_attributes:
            element.set(NODE_ATTRIBUTE, node_id)
        tag = etree.QName(tag_value).localname.lower()
        classes = tuple(part for part in element.get("class", "").split() if part)
        text_value = _normalized_text("".join(cast(str, part) for part in element.itertext()))
        anchor = element.get("id") or text_value[:80] or tag
        result[node_id] = SourceNode(
            node_id=node_id,
            internal_path=internal_path,
            sourceline=cast(int | None, element.sourceline),
            approximate_anchor=anchor,
            tag=tag,
            element_id=element.get("id"),
            classes=classes,
            text_fingerprint=hashlib.blake2s(
                text_value[:500].encode("utf-8"), digest_size=12
            ).hexdigest(),
            depth=sum(1 for _ancestor in element.iterancestors()),
        )
    return result


def nearest_node_for_line(
    node_map: Mapping[str, SourceNode], internal_path: str, line: int
) -> SourceNode | None:
    """Wybiera najgłębszy element zaczynający się najbliżej pozycji kursora."""
    candidates = [
        node
        for node in node_map.values()
        if node.internal_path == internal_path and node.sourceline is not None
    ]
    if not candidates:
        return None
    before = [node for node in candidates if (node.sourceline or 0) <= line]
    if before:
        return max(before, key=lambda node: (node.sourceline or 0, node.depth))
    return min(candidates, key=lambda node: (abs((node.sourceline or line) - line), -node.depth))


def source_location(node: SourceNode, *, recovery_method: str = "node") -> SourceLocation:
    """Tworzy jawnie oznaczoną przybliżoną lokalizację początku elementu."""
    return SourceLocation(
        node_id=node.node_id,
        internal_path=node.internal_path,
        line=node.sourceline,
        label=node.short_label,
        element_exact=recovery_method in {"node", "id", "path", "cursor"},
        position_approximate=True,
        recovery_method=recovery_method,
    )


def _node_id(internal_path: str, element_id: str | None, dom_path: str) -> str:
    """Wylicza deterministyczny identyfikator z danych niewrażliwych na serializację."""
    key = f"{internal_path}:{element_id or ''}:{dom_path}"
    return hashlib.blake2s(key.encode("utf-8"), digest_size=8).hexdigest()


def _normalized_text(value: str) -> str:
    """Normalizuje biały znak do fingerprintu, bez ujawniania treści poza pamięć."""
    return _SPACE_RE.sub(" ", value).strip()
