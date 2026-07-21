"""Skrypty i konwersja stanu DOM współdzielone przez dokładny backend."""

from __future__ import annotations

from typing import Any

from epubforge.gui.preview.backend import PreviewState

APP_WORLD = 1

CAPTURE_SCRIPT = r"""
(() => {
  const selection = window.getSelection();
  let node = selection && selection.anchorNode;
  if (node && node.nodeType !== Node.ELEMENT_NODE) node = node.parentElement;
  if (!node) node = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
  const path = (element) => {
    const parts = [];
    while (element && element !== document.documentElement) {
      const siblings = Array.from(element.parentElement ? element.parentElement.children : []);
      parts.unshift(element.localName + ':nth-child(' + (siblings.indexOf(element) + 1) + ')');
      element = element.parentElement;
    }
    return parts.join(' > ');
  };
  const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
  return {
    scroll_ratio: scrollY / max,
    active_fragment: location.hash ? location.hash.slice(1) : null,
    node_id: node ? node.getAttribute('data-epubforge-node-id') : null,
    original_id: node ? node.id || null : null,
    dom_path: node ? path(node) : null,
    text_fragment: node ? (node.textContent || '').trim().slice(0, 120) : null
  };
})()
"""

READER_STATE_SCRIPT = r"""
(() => {
  const selected = document.querySelector('[data-epubforge-active-node]');
  const pageWidth = Math.max(1, innerWidth);
  const horizontal = Math.max(0, document.documentElement.scrollWidth - pageWidth);
  const pages = Math.max(1, Math.ceil(document.documentElement.scrollWidth / pageWidth));
  const current = Math.min(pages, 1 + Math.round(Math.abs(scrollX) / pageWidth));
  const style = selected ? getComputedStyle(selected) : null;
  const families = style ? style.fontFamily.split(',').map(x => x.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean) : [];
  const faces = [];
  if (document.fonts && families.length) document.fonts.forEach(face => {
    if ((face.family || '').replace(/^['"]|['"]$/g, '') === families[0]) faces.push(face.status);
  });
  return {
    page: current, pages, horizontal_extent: horizontal,
    node_id: selected ? selected.getAttribute('data-epubforge-node-id') : null,
    font: style ? {family: families[0] || style.fontFamily, size: style.fontSize,
      line_height: style.lineHeight, fallbacks: families.slice(1),
      status: faces.length ? ('osadzony: ' + faces.join(', ')) : 'font systemowy lub fallback'} : null
  };
})()
"""


def state_from_js(value: Any, fallback: PreviewState) -> PreviewState:
    """Konwertuje wynik ApplicationWorld bez zaufania jego typom."""
    if not isinstance(value, dict):
        return fallback
    ratio = value.get("scroll_ratio", fallback.scroll_ratio)
    return PreviewState(
        scroll_ratio=float(ratio) if isinstance(ratio, (int, float)) else fallback.scroll_ratio,
        active_fragment=_optional_text(value.get("active_fragment")),
        node_id=_optional_text(value.get("node_id")),
        original_id=_optional_text(value.get("original_id")),
        dom_path=_optional_text(value.get("dom_path")),
        text_fragment=_optional_text(value.get("text_fragment")),
    )


def _optional_text(value: Any) -> str | None:
    return value[:240] if isinstance(value, str) and value else None
