"""Treść okna pomocy offline EpubForge — zakładki dla kitowego ``HelpWindow``.

Okno (belka DWM + re-render motywu na ``PaletteChange``) liczy wspólny kit
(:class:`chodzkos_gui_kit.qt.widgets.HelpWindow`). Tu zostaje WYŁĄCZNIE wiedza o
EpubForge: kolejność zakładek i ich źródła treści.

„Jeden plik prawdy" (gui-kit 0.5.3): zakładki odwzorowujące zakładki GUI — w tym
instrukcja liczby stron EPUB 3 w zakładce Metadane — renderowane są z Markdown
wprost z plików pakietu (:mod:`epubforge.help_docs`), bez duplikowania treści w
kodzie. Zakładka **Narzędzia zewnętrzne** zostaje HTML-owa: tabela
narzędzi (+ nota o motywie/języku) dobrze składa się helperami kitu
(``palette(...)`` → zero hexów; re-render motywu robi kit).

Wołający (:mod:`epubforge.gui.widgets.about_panel`)::

    from chodzkos_gui_kit.qt.widgets import HelpWindow
    from epubforge.gui.help_window import HELP_TITLE, populate_help_window

    window = HelpWindow(parent, title=HELP_TITLE)
    populate_help_window(window)
    window.exec()
"""

from __future__ import annotations

from importlib.resources import as_file, files
from typing import TYPE_CHECKING

from chodzkos_gui_kit.qt.widgets import (
    code as _code,
)
from chodzkos_gui_kit.qt.widgets import (
    paragraph as _p,
)
from chodzkos_gui_kit.qt.widgets import (
    section as _section,
)
from chodzkos_gui_kit.qt.widgets import (
    table as _table,
)
from chodzkos_gui_kit.qt.widgets import (
    unordered_list as _ul,
)

from epubforge.help_docs import MARKDOWN_SECTIONS

if TYPE_CHECKING:
    from chodzkos_gui_kit.qt.widgets import HelpWindow

HELP_TITLE = "Pomoc — EpubForge"

# Tytuł jedynej zakładki HTML (help-only, bez odpowiednika .md) — tabela narzędzi.
TOOLS_TITLE = "Narzędzia zewnętrzne"


def section_titles() -> list[str]:
    """Tytuły zakładek pomocy w kolejności — Markdown z plików + HTML narzędzi.

    Kolejność musi pokrywać zakładki GUI (:mod:`epubforge.help_docs` odwzorowuje je
    1:1) i dokłada „Wiersz poleceń" oraz „Narzędzia zewnętrzne". Używane przez test
    strażniczy porównujący pokrycie z zakładkami ``MainWindow``.
    """
    return [title for title, _ in MARKDOWN_SECTIONS] + [TOOLS_TITLE]


def populate_help_window(window: HelpWindow) -> None:
    """Dokłada zakładki pomocy do świeżo utworzonego ``HelpWindow`` (w kolejności).

    Zakładki Markdown czytane są z plików pakietu przez ``importlib.resources`` (działa
    z koła, z drzewa i po zebraniu przez PyInstaller). ``as_file`` materializuje realny
    plik na czas odczytu — ``HelpWindow.add_markdown_section`` czyta go od razu.
    Ostatnia zakładka („Narzędzia zewnętrzne") to HTML składany helperami kitu.
    """
    docs = files("epubforge.help_docs")
    for title, filename in MARKDOWN_SECTIONS:
        with as_file(docs / filename) as path:
            window.add_markdown_section(title, path)
    window.add_html_section(TOOLS_TITLE, _tools_tab())


# ── Jedyna zakładka HTML: narzędzia zewnętrzne (po polsku; realny stan z kodu) ──────


def _tools_tab() -> str:
    """Tabela narzędzi zewnętrznych + nota o motywie/języku (help-only, HTML)."""
    intro = _p(
        "EpubForge korzysta z narzędzi zewnętrznych. Ich status (OK / brak) widać w "
        "<b>dolnym pasku</b>; wykrywanie jest cache'owane (ponowna detekcja co 7 dni)."
    )
    table = _table(
        ["Narzędzie", "Do czego", "Skąd"],
        [
            ["Java ≥ 11", "Uruchamia EpubCheck", "Eclipse Temurin (Adoptium)"],
            ["EpubCheck", "Walidacja EPUB (jar)", "github.com/w3c/epubcheck"],
            ["Pandoc", "Konwersje formatów → EPUB", "pandoc.org"],
            ["pdf2md", "Zalecany silnik PDF → EPUB", "github.com/chodzkos/pdf2md"],
            ["Calibre", "Konwersje, MOBI/AZW3, KFX (z wtyczką)", "calibre-ebook.com"],
            ["calibredb", "Wzbogacanie biblioteki Calibre (enrich)", "część Calibre"],
            ["Calibre Viewer", "Podgląd EPUB z zakładek Metadane/Edytor", "część Calibre"],
            ["Calibre Editor", "Zewnętrzna edycja EPUB (ebook-edit)", "część Calibre"],
            ["Sigil", "Zewnętrzny edytor EPUB", "sigil-ebook.com"],
            ["DAISY Ace", "Audyt dostępności (a11y)", "npm i -g @daisy/ace"],
            ["Kindle Previewer 3", "Eksperymentalny silnik KFX", "Amazon"],
            ["kindlegen", "Generator MOBI (wycofany)", "preferuj Calibre"],
        ],
    )
    setup = _p(
        "<b>EpubCheck:</b> rozpakuj wydanie do katalogu konfiguracji EpubForge albo wskaż jar "
        "w ustawieniach. <b>Java:</b> zainstaluj Temurin — EpubCheck bez Javy nie ruszy."
    )
    theme = _section(
        "Motyw i język interfejsu",
        _ul(
            "<b>Motyw</b> (górny pasek) — "
            + _code("Automatyczny")
            + " / "
            + _code("Jasny")
            + " / "
            + _code("Ciemny")
            + "; tryb auto podąża za systemem, na Windows zmienia się też "
            "kolor paska tytułu.",
            "<b>Język</b> (górny pasek) — " + _code("Polski") + " / " + _code("English") + "; "
            "treść pomocy pozostaje po polsku niezależnie od wyboru.",
        ),
    )
    return _section(TOOLS_TITLE, intro + table + setup) + theme
