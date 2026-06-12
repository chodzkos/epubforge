"""Dialogi wyboru plików/folderów spójne z motywem (GUI_STANDARD §4).

Domyślnie używamy natywnego dialogu systemu (ma pasek „Szybki dostęp" i jest
spójny, gdy motyw aplikacji == motyw systemu). Przy rozjeździe motywów (w obie
strony) natywny dialog kłóci się z aplikacją — wtedy używamy dialogu Qt
(``DontUseNativeDialog``), ciemnimy jego pasek tytułu przez DWM i dopieszczamy
go kosmetycznie: pasek boczny (Pulpit/Dokumenty/Pobrane/dyski/ostatni katalog),
widok szczegółowy i zapamiętany rozmiar okna.

⚠️ Pasek tytułu (DWM) trzeba pociemnić zanim okno się pokaże — tworzymy więc
natywny uchwyt (``WA_NativeWindow``) przed ``exec()``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QStandardPaths, Qt, QUrl
from PySide6.QtWidgets import QFileDialog, QWidget

from epubforge.core.config import Config
from epubforge.gui.theme import ThemeName, current_theme, system_scheme
from epubforge.gui.window_theme import sync_titlebar

# Klucz i domyślny rozmiar okna dialogu Qt (zapamiętywane w configu).
_DIALOG_SIZE_KEY = "file_dialog_size"
_DEFAULT_DIALOG_SIZE = (900, 550)
# Klucz ostatnio używanego katalogu (wspólny z polami ścieżek/eksportem).
_LAST_DIR_KEY = "last_output_dir"


def use_native_dialog(app_mode: ThemeName, system: ThemeName) -> bool:
    """Czy użyć natywnego dialogu systemu.

    Reguła symetryczna: natywny dialog (idący za motywem systemu) jest spójny
    TYLKO gdy efektywny motyw aplikacji == motyw systemu. Przy KAŻDYM rozjeździe
    (ciemny↔jasny w obie strony) używamy dialogu Qt z paskiem tytułu zgodnym z
    aplikacją. W trybie auto motywy są z definicji zgodne → zawsze natywny.
    """
    return app_mode == system


def open_file(
    parent: QWidget, title: str, start_dir: str, name_filter: str, config: Config | None = None
) -> str:
    """Wybór jednego istniejącego pliku. Zwraca ścieżkę lub ``""``."""
    if _native():
        path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir, config)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog, config)


def open_files(
    parent: QWidget, title: str, name_filter: str, config: Config | None = None
) -> list[str]:
    """Wybór wielu istniejących plików. Zwraca listę ścieżek (może być pusta)."""
    if _native():
        paths, _ = QFileDialog.getOpenFileNames(parent, title, "", name_filter)
        return paths
    dialog = _dark_dialog(parent, title, "", config)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    _set_filters(dialog, name_filter)
    accepted = dialog.exec()
    _persist_size(dialog, config)
    return dialog.selectedFiles() if accepted else []


def save_file(
    parent: QWidget, title: str, start_dir: str, name_filter: str, config: Config | None = None
) -> str:
    """Wybór miejsca i nazwy zapisu. Zwraca ścieżkę lub ``""``."""
    if _native():
        path, _ = QFileDialog.getSaveFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir, config)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog, config)


def pick_dir(parent: QWidget, title: str, start_dir: str = "", config: Config | None = None) -> str:
    """Wybór istniejącego folderu. Zwraca ścieżkę lub ``""``."""
    if _native():
        return QFileDialog.getExistingDirectory(parent, title, start_dir)
    dialog = _dark_dialog(parent, title, start_dir, config)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    return _first_selected(dialog, config)


def _native() -> bool:
    """Decyzja natywny/Qt na podstawie bieżącego motywu i motywu systemu."""
    return use_native_dialog(current_theme().name, system_scheme())


def _dark_dialog(parent: QWidget, title: str, start_dir: str, config: Config | None) -> QFileDialog:
    """Buduje dopieszczony dialog Qt (nie-natywny) z ciemnym paskiem tytułu.

    Ustawia pasek boczny (standardowe katalogi + dyski + ostatni katalog), widok
    szczegółowy i odtwarza zapamiętany rozmiar okna.
    """
    dialog = QFileDialog(parent, title, start_dir)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    # Wymusza utworzenie natywnego okna, by DWM pociemnił pasek przed pokazaniem.
    dialog.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
    dialog.setViewMode(QFileDialog.ViewMode.Detail)
    dialog.setSidebarUrls(_sidebar_urls(start_dir, config))
    _restore_size(dialog, config)
    sync_titlebar(dialog, current_theme().name, system_scheme())
    return dialog


def _sidebar_urls(start_dir: str, config: Config | None) -> list[QUrl]:
    """Buduje pasek boczny: Pulpit, Dokumenty, Pobrane, dyski, ostatni katalog."""
    urls: list[QUrl] = []
    for location in (
        QStandardPaths.StandardLocation.DesktopLocation,
        QStandardPaths.StandardLocation.DocumentsLocation,
        QStandardPaths.StandardLocation.DownloadLocation,
    ):
        paths = QStandardPaths.standardLocations(location)
        if paths:
            urls.append(QUrl.fromLocalFile(paths[0]))
    for drive in QDir.drives():
        urls.append(QUrl.fromLocalFile(drive.absoluteFilePath()))
    last = _last_dir(start_dir, config)
    if last:
        urls.append(QUrl.fromLocalFile(last))

    # Deduplikacja z zachowaniem kolejności (różne lokalizacje bywają tym samym).
    seen: set[str] = set()
    unique: list[QUrl] = []
    for url in urls:
        key = url.toString()
        if key and key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def _last_dir(start_dir: str, config: Config | None) -> str:
    """Ostatni używany katalog: bieżący punkt startowy albo zapamiętany w configu."""
    if start_dir and Path(start_dir).is_dir():
        return start_dir
    if config is not None:
        value = config.get(_LAST_DIR_KEY)
        if isinstance(value, str) and value:
            return value
    return ""


def _restore_size(dialog: QFileDialog, config: Config | None) -> None:
    """Odtwarza rozmiar okna z configu albo ustawia domyślny."""
    width, height = _DEFAULT_DIALOG_SIZE
    if config is not None:
        saved = config.get(_DIALOG_SIZE_KEY)
        if (
            isinstance(saved, (list, tuple))
            and len(saved) == 2
            and all(isinstance(value, int) for value in saved)
        ):
            width, height = saved[0], saved[1]
    dialog.resize(width, height)


def _persist_size(dialog: QFileDialog, config: Config | None) -> None:
    """Zapisuje rozmiar okna do configu (na ConfigStore ``__setitem__`` = mark_dirty)."""
    if config is not None:
        size = dialog.size()
        config[_DIALOG_SIZE_KEY] = [size.width(), size.height()]


def _set_filters(dialog: QFileDialog, name_filter: str) -> None:
    """Ustawia filtry nazw, rozbijając łańcuch Qt rozdzielany ``;;``."""
    parts = [part for part in name_filter.split(";;") if part]
    if parts:
        dialog.setNameFilters(parts)


def _first_selected(dialog: QFileDialog, config: Config | None) -> str:
    """Wykonuje dialog, zapamiętuje rozmiar i zwraca pierwszą ścieżkę lub ``""``."""
    accepted = dialog.exec()
    _persist_size(dialog, config)
    if accepted:
        files = dialog.selectedFiles()
        return files[0] if files else ""
    return ""
