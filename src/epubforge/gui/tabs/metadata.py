"""Zakładka edycji metadanych Dublin Core."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from math import isfinite
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, cast

from epubforge.core import Epub, EpubError, Metadata, Tool, Tools
from epubforge.gui.widgets import FileList, PathEntry, Section, Tooltip

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_TOOL_LABELS = {
    "sigil": "Sigil",
    "calibre_editor": "Calibre Editor",
    "calibre_viewer": "Calibre Viewer",
}


class MetadataTab(ttk.Frame):
    """Zakładka do przeglądania i edycji metadanych EPUB."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent, padding=12)
        self.tools = tools if tools is not None else _detect_tools()
        self.current_path: Path | None = None
        self._loaded_metadata: Metadata | None = None
        self.tool_buttons: dict[str, ttk.Button] = {}

        self.title_var = tk.StringVar()
        self.series_var = tk.StringVar()
        self.series_index_var = tk.StringVar()
        self.language_var = tk.StringVar(value="en")
        self.publisher_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.identifier_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Wybierz plik EPUB")

        self._build_layout()
        self._refresh_tool_buttons()

    def _build_layout(self) -> None:
        """Buduje dwukolumnowy układ zakładki."""
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 10, 0))
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=2)

        self._build_file_browser(left)
        self._build_form(right)

        status = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")
        status.pack(fill="x", pady=(10, 0))

    def _build_file_browser(self, parent: tk.Misc) -> None:
        """Buduje panel wyboru folderu i listy EPUB."""
        browser = Section(parent, "Pliki EPUB")
        browser.pack(fill="both", expand=True)

        self.folder_entry = PathEntry(browser, mode="dir", on_change=self._load_folder)
        self.folder_entry.pack(fill="x", pady=(0, 8))
        Tooltip(self.folder_entry.entry, "Folder z plikami EPUB do edycji metadanych")

        self.file_list = FileList(browser, extensions={".epub"}, on_change=self._on_files_changed)
        self.file_list.pack(fill="both", expand=True)
        self.file_list.listbox.bind("<<ListboxSelect>>", self._on_file_selected)

    def _build_form(self, parent: tk.Misc) -> None:
        """Buduje formularz metadanych i przyciski akcji."""
        form = Section(parent, "Metadane Dublin Core")
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(8, weight=1)

        self._add_entry(form, "Tytuł", self.title_var, 0, tooltip="Tytuł książki (dc:title)")
        self._add_series_row(form, 1)
        self.creators_text = self._add_text(
            form, "Autorzy", 2, height=3, tooltip="Autorzy — jeden na linię; format: Nazwisko, Imię"
        )
        self._add_entry(
            form, "Język", self.language_var, 3, tooltip="Kod języka, np. pl, en (dc:language)"
        )
        self._add_entry(form, "Wydawca", self.publisher_var, 4, tooltip="Wydawca (dc:publisher)")
        self._add_entry(
            form, "Data", self.date_var, 5, tooltip="Data publikacji w formacie ISO: RRRR-MM-DD"
        )
        self._add_entry(
            form,
            "ISBN",
            self.identifier_var,
            6,
            tooltip="Identyfikator: ISBN lub UUID (dc:identifier)",
        )
        self.subjects_text = self._add_text(
            form, "Tematy", 7, height=3, tooltip="Tematy/tagi — jeden na linię (dc:subject)"
        )
        self.description_text = self._add_text(
            form, "Opis", 8, height=7, tooltip="Opis/streszczenie książki (dc:description)"
        )

        actions = ttk.Frame(form)
        actions.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions.columnconfigure(0, weight=1)

        save = ttk.Button(actions, text="Zapisz", command=self._save_metadata)
        save.grid(row=0, column=0, sticky="w")
        Tooltip(save, "Zapisuje metadane do wybranego EPUB (tworzy kopię .bak)")

        tools_frame = ttk.Frame(actions)
        tools_frame.grid(row=0, column=1, sticky="e")
        for key, label in _TOOL_LABELS.items():
            button = ttk.Button(
                tools_frame,
                text=label,
                command=_make_external_callback(self, key, label),
            )
            button.pack(side="left", padx=(6, 0))
            self.tool_buttons[key] = button

    def _add_entry(
        self,
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        row: int,
        *,
        tooltip: str = "",
    ) -> ttk.Entry:
        """Dodaje podpisane pole tekstowe (z opcjonalnym tooltipem)."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        if tooltip:
            Tooltip(entry, tooltip)
        return entry

    def _add_series_row(self, parent: tk.Misc, row: int) -> None:
        """Dodaje pola cyklu i numeru tomu w jednym wierszu."""
        ttk.Label(parent, text="Cykl:").grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="ew", pady=3)
        frame.columnconfigure(0, weight=1)

        series_entry = ttk.Entry(frame, textvariable=self.series_var)
        series_entry.grid(row=0, column=0, sticky="ew")
        Tooltip(series_entry, "Nazwa cyklu/serii, np. Wiedźmin")

        ttk.Label(frame, text="Tom nr:").grid(row=0, column=1, sticky="w", padx=(12, 6))
        series_index_entry = ttk.Entry(frame, textvariable=self.series_index_var, width=10)
        series_index_entry.grid(row=0, column=2, sticky="w")
        Tooltip(series_index_entry, "Numer tomu w cyklu, np. 2 (można 1.5)")

    def _add_text(
        self, parent: tk.Misc, label: str, row: int, *, height: int, tooltip: str = ""
    ) -> tk.Text:
        """Dodaje podpisane pole wielowierszowe (z opcjonalnym tooltipem)."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", pady=3, padx=(0, 8))
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="nsew", pady=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(frame, height=height, wrap="word", undo=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        if tooltip:
            Tooltip(text, tooltip)
        return text

    def _load_folder(self, raw_path: str) -> None:
        """Wczytuje EPUB-y z podanego folderu do listy plików."""
        path = Path(raw_path).expanduser()
        if not raw_path:
            return
        if not path.is_dir():
            self.status_var.set("Wybrany folder nie istnieje")
            return
        self.current_path = None
        self._clear_form()
        self.file_list.clear()
        self.file_list.add_files(sorted(path.glob("*.epub")))
        count = len(self.file_list.files())
        self.status_var.set(f"Wczytano {count} {_plural_files(count)} EPUB")

    def _on_files_changed(self, files: list[Path]) -> None:
        """Czyści wybór lub automatycznie ładuje pierwszy plik z listy."""
        if self.current_path in files:
            return
        self.current_path = None
        self._clear_form()
        if files:
            self.file_list.listbox.selection_clear(0, "end")
            self.file_list.listbox.selection_set(0)
            self.file_list.listbox.activate(0)
            self._load_metadata(files[0])

    def _on_file_selected(self, _event: tk.Event[Any] | None = None) -> None:
        """Ładuje metadane zaznaczonego pliku."""
        listbox = cast(Any, self.file_list.listbox)
        selection = tuple(int(index) for index in listbox.curselection())
        if not selection:
            return
        files = self.file_list.files()
        index = selection[0]
        if index >= len(files):
            return
        self._load_metadata(files[index])

    def _load_metadata(self, path: Path) -> None:
        """Czyta metadane z EPUB i wypełnia formularz."""
        try:
            with Epub(path) as epub:
                metadata = epub.metadata
        except (EpubError, OSError, KeyError) as exc:
            self.status_var.set(f"Nie udało się wczytać metadanych: {exc}")
            messagebox.showerror("Metadane", f"Nie udało się wczytać metadanych:\n{exc}")
            return
        self.current_path = path
        self._loaded_metadata = metadata
        self._set_form(metadata)
        self.status_var.set(f"Wczytano metadane: {path.name}")

    def _save_metadata(self) -> None:
        """Zapisuje metadane do aktualnego EPUB przez setter Epub.metadata."""
        if self.current_path is None:
            self.status_var.set("Wybierz plik EPUB przed zapisem")
            return
        metadata = self._metadata_from_form()
        try:
            with Epub(self.current_path) as epub:
                epub.metadata = metadata
        except (EpubError, OSError, KeyError) as exc:
            self.status_var.set(f"Nie udało się zapisać metadanych: {exc}")
            messagebox.showerror("Metadane", f"Nie udało się zapisać metadanych:\n{exc}")
            return
        self._loaded_metadata = metadata
        self.status_var.set(f"Zapisano metadane: {self.current_path.name}")

    def _open_external(self, key: str, label: str) -> None:
        """Uruchamia zewnętrzny edytor/podgląd dla aktualnego EPUB."""
        tool = self.tools.get(key)
        if tool is None or not tool.available or tool.path is None:
            self.status_var.set(f"Nie wykryto {label}")
            return
        if self.current_path is None:
            self.status_var.set("Wybierz plik EPUB")
            return
        try:
            subprocess.Popen(
                [str(tool.path), str(self.current_path)],
                creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            self.status_var.set(f"Nie udało się uruchomić {label}: {exc}")
            messagebox.showerror(label, f"Nie udało się uruchomić programu:\n{exc}")

    def _refresh_tool_buttons(self) -> None:
        """Aktualizuje stan przycisków narzędzi zewnętrznych."""
        for key, label in _TOOL_LABELS.items():
            button = self.tool_buttons[key]
            tool = self.tools.get(key)
            if tool is not None and tool.available and tool.path is not None:
                button.state(["!disabled"])
                Tooltip(button, str(tool.path))
            else:
                button.state(["disabled"])
                Tooltip(button, f"Nie wykryto {label}")

    def _set_form(self, metadata: Metadata) -> None:
        """Przepisuje obiekt Metadata do pól formularza."""
        self.title_var.set(metadata.title)
        self.series_var.set(metadata.series)
        self.series_index_var.set(_format_series_index(metadata.series_index))
        self.language_var.set(metadata.language)
        self.publisher_var.set(metadata.publisher)
        self.date_var.set(metadata.date)
        self.identifier_var.set(metadata.identifier)
        _set_text(self.creators_text, "\n".join(metadata.creators))
        _set_text(self.subjects_text, "\n".join(metadata.subjects))
        _set_text(self.description_text, metadata.description)

    def _metadata_from_form(self) -> Metadata:
        """Buduje Metadata z aktualnych wartości formularza."""
        series_index = self._series_index_from_form()
        return Metadata(
            title=self.title_var.get().strip(),
            creators=_split_lines(_get_text(self.creators_text)),
            language=self.language_var.get().strip() or "en",
            identifier=self.identifier_var.get().strip(),
            publisher=self.publisher_var.get().strip(),
            date=self.date_var.get().strip(),
            description=_get_text(self.description_text).strip(),
            subjects=_split_lines(_get_text(self.subjects_text)),
            series=self.series_var.get().strip(),
            series_index=series_index,
        )

    def _clear_form(self) -> None:
        """Czyści formularz metadanych."""
        self._loaded_metadata = None
        self._set_form(Metadata())

    def _series_index_from_form(self) -> float | None:
        """Parsuje numer tomu, łagodnie ignorując niepoprawną wartość."""
        raw_value = self.series_index_var.get().strip()
        if not raw_value:
            return None
        try:
            value = float(raw_value)
        except ValueError:
            return self._warn_invalid_series_index()
        if not isfinite(value):
            return self._warn_invalid_series_index()
        return value

    def _warn_invalid_series_index(self) -> float | None:
        """Pokazuje ostrzeżenie i zachowuje poprzedni numer tomu."""
        previous = self._loaded_metadata.series_index if self._loaded_metadata is not None else None
        self.status_var.set("Tom nr nie jest liczbą; zapisano pozostałe metadane")
        messagebox.showwarning(
            "Metadane",
            "Pole „Tom nr” musi być liczbą, np. 2 albo 1.5. Ta wartość nie zostanie zmieniona.",
        )
        return previous


def _detect_tools() -> dict[str, Tool]:
    """Wykrywa narzędzia używane przez zakładkę metadanych."""
    return {
        "sigil": Tools.sigil(),
        "calibre_editor": Tools.calibre_editor(),
        "calibre_viewer": Tools.calibre_viewer(),
    }


def _make_external_callback(
    tab: MetadataTab,
    key: str,
    label: str,
) -> Callable[[], None]:
    """Tworzy callback bez późnego wiązania zmiennych pętli."""

    def callback() -> None:
        tab._open_external(key, label)

    return callback


def _get_text(widget: tk.Text) -> str:
    """Zwraca zawartość pola Text bez końcowego znaku nowej linii."""
    return widget.get("1.0", "end-1c")


def _set_text(widget: tk.Text, value: str) -> None:
    """Ustawia zawartość pola Text."""
    widget.delete("1.0", "end")
    widget.insert("1.0", value)


def _format_series_index(value: float | None) -> str:
    """Formatuje numer tomu do pola formularza."""
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else str(value)


def _split_lines(value: str) -> list[str]:
    """Rozbija wielowierszową wartość formularza na niepuste wpisy."""
    return [line.strip() for line in value.splitlines() if line.strip()]


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
