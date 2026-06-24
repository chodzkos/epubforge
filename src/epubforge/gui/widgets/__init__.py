"""Wielokrotnego użycia widgety Qt (PySide6) dla GUI EpubForge.

``PathEntry`` pochodzi z chodzkos-gui-kit (warstwa ``qt/widgets``); re-eksportujemy
go tutaj, by reszta GUI importowała widgety z jednego miejsca. Polskie etykiety
dialogów wstrzykujemy przez :func:`path_entry_texts` (kit jest i18n-agnostyczny).
"""

from chodzkos_gui_kit.qt.widgets import PathEntry, PathEntryTexts

from epubforge.gui.widgets.about_panel import AboutPanel
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.css_inspector import CssInspector
from epubforge.gui.widgets.file_list import FileList
from epubforge.gui.widgets.html_preview import HtmlPreview
from epubforge.gui.widgets.image_preview import ImagePreview
from epubforge.gui.widgets.log_view import LogView
from epubforge.gui.widgets.section import Section
from epubforge.i18n import _

__all__ = [
    "AboutPanel",
    "CodeEditor",
    "CssInspector",
    "FileList",
    "HtmlPreview",
    "ImagePreview",
    "LogView",
    "PathEntry",
    "PathEntryTexts",
    "Section",
    "path_entry_texts",
]


def path_entry_texts() -> PathEntryTexts:
    """Polskie (gettext) etykiety tooltipów i tytułów dialogów dla ``PathEntry``.

    Wołane przy budowie widgetu, więc ``_()`` rozwiązuje się po załadowaniu locale.
    Msgidy są identyczne jak w dawnym lokalnym widgecie — tłumaczenia .po działają
    bez zmian.
    """
    return PathEntryTexts(
        tooltip_dir=_("Wybierz folder"),
        tooltip_file=_("Wybierz plik"),
        tooltip_save=_("Wybierz miejsce i nazwę zapisu"),
        title_dir=_("Wybierz folder"),
        title_file=_("Wybierz plik"),
        title_save=_("Zapisz jako"),
    )
