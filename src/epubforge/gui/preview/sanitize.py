"""Sanityzacja kopii XHTML renderowanej przez WebEngine i restrykcyjny CSP."""

from __future__ import annotations

from typing import cast

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted_document, serialize_document

CSP_POLICY = "; ".join(
    (
        "default-src 'none'",
        "img-src epub-preview: data:",
        "style-src epub-preview: 'unsafe-inline'",
        "font-src epub-preview:",
        "connect-src 'none'",
        "frame-src 'none'",
        "object-src 'none'",
        "worker-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    )
)

_DROP_ELEMENTS = frozenset(
    {
        "script",
        "iframe",
        "object",
        "embed",
        "form",
        "base",
        "audio",
        "video",
        "source",
        "track",
    }
)
_DROP_META_HTTP_EQUIV = frozenset({"refresh", "content-security-policy"})


def sanitize_xhtml(data: bytes) -> bytes:
    """Tworzy bezpieczną kopię XHTML; nigdy nie modyfikuje bufora :class:`Epub`."""
    root, doctype = parse_untrusted_document(data)
    root_tag = cast(object, root.tag)
    root_local_name = etree.QName(root_tag).localname.lower() if isinstance(root_tag, str) else ""
    root_is_active_meta = (
        root_local_name == "meta"
        and root.get("http-equiv", "").strip().lower() in _DROP_META_HTTP_EQUIV
    )
    if root_local_name in _DROP_ELEMENTS or root_is_active_meta:
        namespace = etree.QName(cast(str, root_tag)).namespace
        root = etree.Element(f"{{{namespace}}}html" if namespace else "html")
        doctype = ""
    for element in list(root.iter()):
        tag = cast(object, element.tag)
        if not isinstance(tag, str):
            continue
        local_name = etree.QName(tag).localname.lower()
        if local_name in _DROP_ELEMENTS:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
            continue
        if (
            local_name == "meta"
            and element.get("http-equiv", "").strip().lower() in _DROP_META_HTTP_EQUIV
        ):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
            continue
        for attribute in list(element.attrib):
            if etree.QName(attribute).localname.lower().startswith("on"):
                del element.attrib[attribute]
    _insert_csp(root)
    return serialize_document(root, doctype)


def _insert_csp(root: etree._Element) -> None:
    """Wstawia CSP jako pierwszy element ``head`` z zachowaniem namespace XHTML."""
    namespace = etree.QName(root).namespace
    head_tag = f"{{{namespace}}}head" if namespace else "head"
    meta_tag = f"{{{namespace}}}meta" if namespace else "meta"
    head = root.find(head_tag)
    if head is None:
        head = etree.Element(head_tag)
        root.insert(0, head)
    meta = etree.Element(meta_tag)
    meta.set("http-equiv", "Content-Security-Policy")
    meta.set("content", CSP_POLICY)
    head.insert(0, meta)
