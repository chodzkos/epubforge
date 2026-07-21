"""Formatowanie danych kaskady dla panelu elementu CSS."""

from __future__ import annotations

from epubforge.gui.css_inspection import ElementInspection, InspectorRule
from epubforge.i18n import _


def format_box(box: object) -> str:
    """Składa margin/border/padding/content do zwartego opisu."""
    if not isinstance(box, dict):
        return ""

    def values(name: str) -> str:
        item = box.get(name, {})
        return (
            "/".join(str(item.get(side, "")) for side in ("top", "right", "bottom", "left"))
            if isinstance(item, dict)
            else ""
        )

    content = box.get("content", {})
    size = (
        f"{content.get('width', '')} x {content.get('height', '')}"
        if isinstance(content, dict)
        else ""
    )
    return _(
        "Box: margin {margin} · border {border} · padding {padding} · content {content}"
    ).format(
        margin=values("margin"), border=values("border"), padding=values("padding"), content=size
    )


def format_font(inspection: ElementInspection) -> str:
    """Pokazuje font rzeczywisty, computed, osadzenie i fallback."""
    font = inspection.font
    if font is None:
        return ""
    return _(
        "Font: {used} · computed {computed} · osadzony {embedded} ({status}) · fallback {fallback}"
    ).format(
        used=font.used_family,
        computed=font.computed_family,
        embedded=_("tak") if font.embedded else _("nie"),
        status=font.status,
        fallback=", ".join(font.fallbacks) or "—",
    )


def state_label(state: str) -> str:
    """Lokalizuje stan deklaracji CSS."""
    return {
        "winning": _("zwycięska"),
        "partial": _("częściowo nadpisana"),
        "lost": _("przegrana"),
        "inactive": _("nieaktywna"),
    }.get(state, state)


def declaration_source(rule: InspectorRule, winner_order: int | None, state: str) -> str:
    """Pokazuje kolejność/specyficzność i zwycięzcę przegranej deklaracji."""
    winner = f" -> {_('wygrywa')} #{winner_order}" if state == "lost" and winner_order else ""
    return f"spec={rule.specificity} · #{rule.order}{winner}"
