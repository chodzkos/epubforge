"""Testy treści okna pomocy EpubForge (zakładki dla kitowego HelpWindow)."""

from __future__ import annotations

import pytest

from epubforge.gui.help_window import HELP_TITLE, help_tabs

pytestmark = pytest.mark.gui


def test_help_tabs_cover_gui_tabs() -> None:
    """9 zakładek odwzorowujących GUI + narzędzia; tytuły zgodne z zakładkami aplikacji."""
    titles = [t for t, _ in help_tabs()]
    assert titles == [
        "Metadane",
        "Konwerter",
        "Fixer",
        "Eksport Kindle",
        "Edytor",
        "Walidacja",
        "Spis treści",
        "Statystyki",
        "Narzędzia zewnętrzne",
    ]
    assert HELP_TITLE == "Pomoc — EpubForge"


def test_help_content_uses_palette_not_hex() -> None:
    """Kolory wyłącznie przez palette() (kit) — zero zaszytych hexów."""
    html = "".join(h for _, h in help_tabs())
    assert "palette(" in html
    assert "#" not in html  # żadnych kolorów hex w treści


def test_help_content_mentions_real_facts() -> None:
    """Pomoc nie kłamie: kluczowe, realne fakty EpubForge są obecne."""
    html = "".join(h for _, h in help_tabs())
    for needle in (
        "EpubCheck",
        "Java",  # epubcheck wymaga Javy
        "Temurin",
        "Calibre",
        "kindlegen",  # wycofany — preferuj Calibre
        "pyphen",  # hyphenacja
        "Dublin Core",
        "pasku statusu",  # delegacja zmiennego stanu
    ):
        assert needle in html, f"brak wzmianki o: {needle}"


def test_kindlegen_marked_retired() -> None:
    """kindlegen opisany jako wycofany (nie mylić użytkownika)."""
    html = "".join(h for _, h in help_tabs())
    assert "wycofany" in html
