"""Testy treści okna pomocy EpubForge (Markdown z plików pakietu + HTML narzędzi)."""

from __future__ import annotations

from importlib.resources import files

import pytest
from chodzkos_gui_kit.qt.widgets import HelpWindow
from pytestqt.qtbot import QtBot

from epubforge.gui.help_window import (
    HELP_TITLE,
    TOOLS_TITLE,
    populate_help_window,
    section_titles,
)
from epubforge.help_docs import MARKDOWN_SECTIONS

pytestmark = pytest.mark.gui

# Zakładki robocze GUI (MainWindow) — pomoc musi je wszystkie pokrywać. Trzymane
# jawnie (bez budowania MainWindow), spójne z app.py: tabs.addTab(..., _(...)).
_GUI_TABS = (
    "Metadane",
    "Konwerter",
    "Fixer",
    "Eksport Kindle",
    "Edytor",
    "Walidacja",
    "Spis treści",
    "Statystyki",
)


def test_section_titles_order() -> None:
    """Kolejność zakładek: 8 zakładek GUI → Wiersz poleceń → Narzędzia zewnętrzne."""
    assert section_titles() == [
        "Metadane",
        "Konwerter",
        "Fixer",
        "Eksport Kindle",
        "Edytor",
        "Walidacja",
        "Spis treści",
        "Statystyki",
        "Wiersz poleceń",
        "Narzędzia zewnętrzne",
    ]
    assert HELP_TITLE == "Pomoc — EpubForge"


def test_sections_cover_all_gui_tabs() -> None:
    """Każda zakładka robocza GUI ma odpowiednik w pomocy (audyt pokrycia)."""
    titles = set(section_titles())
    for gui_tab in _GUI_TABS:
        assert gui_tab in titles, f"pomoc nie pokrywa zakładki GUI: {gui_tab}"


def test_help_docs_files_exist_and_nonempty() -> None:
    """Test strażniczy: każdy plik .md z rejestru istnieje w pakiecie i jest niepusty.

    Czyta przez ``importlib.resources`` — kontrakt „jeden plik prawdy" musi działać z
    zainstalowanego pakietu (koło/exe), nie tylko z drzewa źródeł.
    """
    docs = files("epubforge.help_docs")
    for _title, filename in MARKDOWN_SECTIONS:
        text = (docs / filename).read_text(encoding="utf-8")
        assert text.strip(), f"pusty plik pomocy: {filename}"
        # Pliki prawdy odsyłają do pełnej wersji (kontrakt 0.5.3 opcja ii).
        assert "user-guide.md" in text, f"brak odnośnika do pełnej wersji: {filename}"


def test_cli_help_covers_all_subcommands() -> None:
    """Zakładka „Wiersz poleceń" wymienia wszystkie podkomendy CLI (audyt kompletności)."""
    cli_md = (files("epubforge.help_docs") / "cli.md").read_text(encoding="utf-8")
    for command in (
        "info",
        "doctor",
        "check",
        "a11y",
        "convert",
        "enrich",
        "meta",
        "fix",
        "hyphenate",
        "typo",
        "upgrade",
        "toc",
        "stats",
        "kfx",
        "mobi",
        "presets",
        "run",
    ):
        assert command in cli_md, f"zakładka CLI nie opisuje komendy: {command}"


def test_tools_tab_uses_palette_not_hex() -> None:
    """Zakładka HTML (narzędzia) — kolory wyłącznie przez palette() kitu, zero hexów."""
    window_html = _tools_html()
    assert "palette(" in window_html
    assert "#" not in window_html


def test_tools_tab_mentions_real_facts() -> None:
    """Tabela narzędzi nie kłamie: 11 narzędzi + kluczowe fakty obecne."""
    html = _tools_html()
    for needle in (
        "Java",
        "Temurin",
        "EpubCheck",
        "Pandoc",
        "pdf2md",
        "Calibre",
        "calibredb",
        "Sigil",
        "DAISY Ace",
        "Kindle Previewer",
        "kindlegen",
        "wycofany",  # kindlegen wycofany
        "Motyw",  # nota o motywie/języku
    ):
        assert needle in html, f"brak wzmianki o: {needle}"


def test_help_window_builds_with_all_sections(qtbot: QtBot) -> None:
    """Okno pomocy buduje się z kompletem zakładek (offscreen)."""
    window = HelpWindow(title=HELP_TITLE)
    qtbot.addWidget(window)
    populate_help_window(window)
    # Liczba zakładek == liczba sekcji z rejestru (Markdown) + 1 (narzędzia HTML).
    assert window._tabs.count() == len(section_titles())
    rendered = [window._tabs.tabText(i) for i in range(window._tabs.count())]
    assert rendered == section_titles()
    assert TOOLS_TITLE in rendered


def _tools_html() -> str:
    """Pomocnik: HTML zakładki narzędzi (jedyna zakładka HTML pomocy)."""
    from epubforge.gui.help_window import _tools_tab

    return _tools_tab()
