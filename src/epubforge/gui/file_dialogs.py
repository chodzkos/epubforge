"""Dialogi wyboru plików/folderów spójne z motywem (GUI_STANDARD v2.0 §4).

Na Win11 natywny dialog systemu sam jest ciemny, gdy system jest ciemny — więc
domyślnie używamy natywnego (ma pasek „Szybki dostęp"). Jedyny problematyczny
przypadek to rozjazd: aplikacja ciemna, a system jasny — wtedy natywny dialog
byłby jasny i psułby spójność. Tylko wtedy używamy dialogu Qt
(``DontUseNativeDialog``) i ciemnimy jego pasek tytułu przez DWM.

⚠️ Pasek tytułu (DWM) trzeba pociemnić zanim okno się pokaże — tworzymy więc
natywny uchwyt (``WA_NativeWindow``) przed ``exec()``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget

from epubforge.gui.theme import ThemeName, current_theme, system_scheme
from epubforge.gui.window_theme import sync_titlebar


def use_native_dialog(app_mode: ThemeName, system: ThemeName) -> bool:
    """Czy użyć natywnego dialogu systemu.

    Reguła symetryczna: natywny dialog (idący za motywem systemu) jest spójny
    TYLKO gdy efektywny motyw aplikacji == motyw systemu. Przy KAŻDYM rozjeździe
    (ciemny↔jasny w obie strony) używamy dialogu Qt z paskiem tytułu zgodnym z
    aplikacją. W trybie auto motywy są z definicji zgodne → zawsze natywny.
    """
    return app_mode == system


def open_file(parent: QWidget, title: str, start_dir: str, name_filter: str) -> str:
    """Wybór jednego istniejącego pliku. Zwraca ścieżkę lub ``""``."""
    if _native():
        path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog)


def open_files(parent: QWidget, title: str, name_filter: str) -> list[str]:
    """Wybór wielu istniejących plików. Zwraca listę ścieżek (może być pusta)."""
    if _native():
        paths, _ = QFileDialog.getOpenFileNames(parent, title, "", name_filter)
        return paths
    dialog = _dark_dialog(parent, title, "")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    _set_filters(dialog, name_filter)
    return dialog.selectedFiles() if dialog.exec() else []


def save_file(parent: QWidget, title: str, start_dir: str, name_filter: str) -> str:
    """Wybór miejsca i nazwy zapisu. Zwraca ścieżkę lub ``""``."""
    if _native():
        path, _ = QFileDialog.getSaveFileName(parent, title, start_dir, name_filter)
        return path
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    _set_filters(dialog, name_filter)
    return _first_selected(dialog)


def pick_dir(parent: QWidget, title: str, start_dir: str = "") -> str:
    """Wybór istniejącego folderu. Zwraca ścieżkę lub ``""``."""
    if _native():
        return QFileDialog.getExistingDirectory(parent, title, start_dir)
    dialog = _dark_dialog(parent, title, start_dir)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    return _first_selected(dialog)


def _native() -> bool:
    """Decyzja natywny/Qt na podstawie bieżącego motywu i motywu systemu."""
    return use_native_dialog(current_theme().name, system_scheme())


def _dark_dialog(parent: QWidget, title: str, start_dir: str) -> QFileDialog:
    """Buduje dialog Qt (nie-natywny) z ciemnym paskiem tytułu na Windows."""
    dialog = QFileDialog(parent, title, start_dir)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    # Wymusza utworzenie natywnego okna, by DWM pociemnił pasek przed pokazaniem.
    dialog.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
    sync_titlebar(dialog, current_theme().name, system_scheme())
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
