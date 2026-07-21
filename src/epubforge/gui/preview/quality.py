"""Model i skrypt diagnostyki jakości aktywnego layoutu Chromium."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityIssue:
    """Ostrzeżenie powiązane z elementem DOM i, gdy możliwe, źródłem."""

    kind: str
    category: str
    message: str
    node_id: str | None = None
    value: str | None = None


def parse_quality_report(value: object) -> tuple[QualityIssue, ...]:
    """Waliduje nieufny raport JS bez ukrywania nieznanych rekordów."""
    if not isinstance(value, dict) or not isinstance(value.get("issues"), list):
        return ()
    result: list[QualityIssue] = []
    for raw in value["issues"]:
        if not isinstance(raw, dict):
            continue
        result.append(
            QualityIssue(
                kind=str(raw.get("kind", "unknown"))[:80],
                category=str(raw.get("category", "quality_warning"))[:80],
                message=str(raw.get("message", "Nierozpoznany problem jakości."))[:500],
                node_id=_text(raw.get("node_id"), 240),
                value=_text(raw.get("value"), 240),
            )
        )
    return tuple(result)


def _text(value: Any, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


# Nie dokonuje auto-fixów. Wartości geometrii i computed style pochodzą wyłącznie
# z WebEngine. Każde ostrzeżenie niesie techniczny node id do mapy źródłowej.
QUALITY_SCRIPT = r"""
((minimumFont, minimumLineHeight, accessibility) => {
  const issues = [];
  const id = element => element && element.getAttribute('data-epubforge-node-id');
  const add = (element, kind, category, message, value) => issues.push({
    node_id: id(element), kind, category, message, value: value == null ? null : String(value)
  });
  const viewport = document.documentElement.clientWidth || innerWidth;
  const paged = document.documentElement.dataset.epubforgeFlow === 'pages';
  const fixed = document.documentElement.dataset.epubforgeLayout === 'pre-paginated';
  const visible = element => {
    const style = getComputedStyle(element), rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const rgb = value => {
    const match = String(value).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/i);
    return match ? match.slice(1,4).map(Number) : null;
  };
  const luminance = color => {
    const channels = color.map(x => x / 255).map(x => x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4));
    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
  };
  if (!paged && !fixed && document.documentElement.scrollWidth > viewport + 1)
    add(document.body, 'horizontal_overflow', 'quality_warning', 'Dokument ma poziomy overflow.', document.documentElement.scrollWidth + 'px');
  for (const element of Array.from(document.body.querySelectorAll('*'))) {
    if (!visible(element)) continue;
    const style = getComputedStyle(element), rect = element.getBoundingClientRect();
    const width = parseFloat(style.width);
    if ((!paged && rect.right > viewport + 1) || element.scrollWidth > element.clientWidth + 1)
      add(element, 'element_overflow', 'quality_warning', 'Element wychodzi poza viewport.', Math.round(rect.width) + 'px');
    if (style.width.endsWith('px') && width > viewport)
      add(element, 'fixed_width', 'quality_warning', 'Stała szerokość jest większa od viewportu.', style.width);
    if (element.localName === 'img' && rect.width > viewport)
      add(element, 'wide_image', 'quality_warning', 'Obraz jest szerszy od strony.', Math.round(rect.width) + 'px');
    if ((style.position === 'absolute' || style.position === 'fixed') && rect.width > viewport * .35)
      add(element, 'suspicious_position', 'quality_warning', 'Podejrzane pozycjonowanie absolute/fixed.', style.position);
    const fontSize = parseFloat(style.fontSize), lineHeight = parseFloat(style.lineHeight);
    if (Number.isFinite(fontSize) && fontSize < minimumFont)
      add(element, 'small_font', 'quality_warning', 'Rozmiar fontu jest niższy od skonfigurowanego progu.', style.fontSize);
    if (Number.isFinite(lineHeight) && fontSize > 0 && lineHeight / fontSize < minimumLineHeight)
      add(element, 'tight_line_height', 'quality_warning', 'Line-height jest niższy od skonfigurowanego progu.', style.lineHeight);
    if (element.childElementCount === 0 && (element.textContent || '').trim()) {
      const fg = rgb(style.color), bg = rgb(style.backgroundColor);
      if (fg && bg && !/rgba\([^)]*,\s*0(?:\.0+)?\)/.test(style.backgroundColor)) {
        const l1 = luminance(fg), l2 = luminance(bg), contrast = (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
        if (contrast < 3) add(element, 'low_contrast', 'quality_warning', 'Niska czytelność kontrastu (ostrzeżenie, bez auto-fixu).', contrast.toFixed(2));
      }
    }
  }
  if (accessibility) {
    document.querySelectorAll('img:not([alt])').forEach(element => add(element, 'missing_alt', 'quality_warning', 'Obraz nie ma atrybutu alt.', null));
    let previous = 0;
    document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(element => {
      const level = Number(element.localName.slice(1));
      if (previous && level > previous + 1) add(element, 'heading_jump', 'quality_warning', 'Hierarchia nagłówków pomija poziom.', 'h' + previous + ' → h' + level);
      previous = level;
    });
  }
  if (document.fonts) {
    const families = new Map();
    document.fonts.forEach(face => families.set(face.family, face.status));
    for (const [family, status] of families) if (status !== 'loaded')
      add(document.body, 'font_not_loaded', 'quality_warning', 'Font nie został załadowany.', family + ': ' + status);
  }
  return {issues, viewport, scroll_width: document.documentElement.scrollWidth};
})
"""
