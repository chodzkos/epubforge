"""Wielokrotnego użycia widgety Qt (PySide6) dla GUI EpubForge.

``PathEntry``, ``FileList`` i ``LogView`` pochodzą z chodzkos-gui-kit (warstwa
``qt/widgets``); re-eksportujemy je tutaj, by reszta GUI importowała widgety z
jednego miejsca. Polskie etykiety i licznik (formy mnogie) wstrzykujemy przez
:func:`path_entry_texts`, :func:`file_list_texts` i :func:`file_list_count_label`
— kit jest i18n-agnostyczny (``LogView`` nie ma etykiet, więc bez helpera).
"""

from chodzkos_gui_kit.qt.widgets import (
    FileList,
    FileListTexts,
    LogView,
    PathEntry,
    PathEntryTexts,
)

from epubforge.gui.widgets.about_panel import AboutPanel
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.css_inspector import CssInspector
from epubforge.gui.widgets.html_preview import HtmlPreview
from epubforge.gui.widgets.image_preview import ImagePreview
from epubforge.gui.widgets.section import Section
from epubforge.i18n import _, ngettext

__all__ = [
    "AboutPanel",
    "CodeEditor",
    "CssInspector",
    "FileList",
    "FileListTexts",
    "HtmlPreview",
    "ImagePreview",
    "LogView",
    "PathEntry",
    "PathEntryTexts",
    "Section",
    "file_list_count_label",
    "file_list_texts",
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


def file_list_texts() -> FileListTexts:
    """Polskie (gettext) etykiety toolbara, tooltipów i filtra dla ``FileList``."""
    return FileListTexts(
        files=_("Pliki"),
        folder=_("Folder"),
        remove=_("Usuń"),
        clear=_("Wyczyść"),
        tooltip_files=_("Dodaj pliki przez okno wyboru"),
        tooltip_folder=_("Dodaj obsługiwane pliki z wybranego folderu"),
        tooltip_remove=_("Usuń zaznaczone pozycje z listy"),
        tooltip_clear=_("Usuń wszystkie pozycje z listy"),
        list_tooltip=_("Lista plików — przeciągnij pliki tutaj lub użyj przycisków powyżej"),
        dialog_add_files=_("Dodaj pliki"),
        dialog_add_folder=_("Dodaj folder"),
        filter_supported=_("Obsługiwane ({pattern})"),
    )


def file_list_count_label(count: int) -> str:
    """Licznik plików z polskimi formami mnogimi (gettext ``ngettext``)."""
    return ngettext("{n} plik", "{n} plików", count).format(n=count)
