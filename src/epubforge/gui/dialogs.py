"""Dialogi wyboru plików/folderów z ciemnym paskiem tytułu na Windows.

W trybie jasnym używamy natywnych dialogów systemu (są spójne). W trybie ciemnym
natywny dialog ma jasny pasek tytułu i psuje spójność — wtedy używamy dialogu Qt
(``DontUseNativeDialog``) i dodatkowo ciemnimy jego pasek tytułu przez DWM, tak
samo jak główne okno (GUI_STANDARD §4).

⚠️ Pasek tytułu (DWM) trzeba pociemnić zanim okno się pokaże — tworzymy więc
natywny uchwyt (``WA_NativeWindow``) przed ``exec()``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget

from epubforge.gui.theme import native_file_dialogs
from epubforge.gui.window_theme import set_titlebar_dark


def open_file(parent: QWidget, title: str, start_dir: str, name_filter: str) -> str:
    """Wybór jednego istniejącego pliku. Zwraca ścieżkę lub ``""``."""
    if native_file_dialogs():
        path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog)


def open_files(parent: QWidget, title: str, name_filter: str) -> list[str]:
    """Wybór wielu istniejących plików. Zwraca listę ścieżek (może być pusta)."""
    if native_file_dialogs():
        paths, _ = QFileDialog.getOpenFileNames(parent, title, "", name_filter)
        return paths
    dialog = _dark_dialog(parent, title, "")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    _set_filters(dialog, name_filter)
    return dialog.selectedFiles() if dialog.exec() else []


def save_file(parent: QWidget, title: str, start_dir: str, name_filter: str) -> str:
    """Wybór miejsca i nazwy zapisu. Zwraca ścieżkę lub ``""``."""
    if native_file_dialogs():
        path, _ = QFileDialog.getSaveFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog)


def choose_directory(parent: QWidget, title: str, start_dir: str = "") -> str:
    """Wybór istniejącego folderu. Zwraca ścieżkę lub ``""``."""
    if native_file_dialogs():
        return QFileDialog.getExistingDirectory(parent, title, start_dir)
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    return _first_selected(dialog)


def _dark_dialog(parent: QWidget, title: str, start_dir: str) -> QFileDialog:
    """Buduje dialog Qt (nie-natywny) z ciemnym paskiem tytułu na Windows."""
    dialog = QFileDialog(parent, title, start_dir)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    # Wymusza utworzenie natywnego okna, by DWM pociemnił pasek przed pokazaniem.
    dialog.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
    set_titlebar_dark(dialog, True)
    return dialog


def _set_filters(dialog: QFileDialog, name_filter: str) -> None:
    """Ustawia filtry nazw, rozbijając łańcuch Qt rozdzielany ``;;``."""
    parts = [part for part in name_filter.split(";;") if part]
    if parts:
        dialog.setNameFilters(parts)


def _first_selected(dialog: QFileDialog) -> str:
    """Wykonuje dialog i zwraca pierwszą wybraną ścieżkę lub ``""``."""
    if dialog.exec():
        files = dialog.selectedFiles()
        return files[0] if files else ""
    return ""
