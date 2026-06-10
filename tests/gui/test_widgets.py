"""Smoke testy frameworka GUI i widgetów."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from epubforge.core.detection import Tool
from epubforge.gui import app as app_module
from epubforge.gui.app import App
from epubforge.gui.streaming import LogStreamer
from epubforge.gui.theme import DARK, apply_theme
from epubforge.gui.widgets import FileList, PathEntry, Section, Toggle, Tooltip
from epubforge.gui.widgets import file_list as file_list_module

pytestmark = pytest.mark.gui


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    """Tworzy root tkinter albo pomija test, gdy środowisko nie ma display."""
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def test_widgets_create_without_errors(root: tk.Tk, tmp_path: Path) -> None:
    """Podstawowe widgety tworzą się i obsługują swoje publiczne API."""
    frame = tk.Frame(root)
    frame.pack()

    changed_paths: list[str] = []
    path_entry = PathEntry(frame, mode="file", on_change=changed_paths.append)
    path_entry.pack()
    path_entry.set(str(tmp_path / "book.epub"))
    assert path_entry.get().endswith("book.epub")
    assert changed_paths

    listed: list[list[Path]] = []
    file_list = FileList(frame, extensions={".epub"}, on_change=listed.append)
    file_list.pack()
    file_list.add_files([tmp_path / "book.epub", tmp_path / "skip.txt"])
    assert file_list.files() == [tmp_path / "book.epub"]
    assert listed[-1] == [tmp_path / "book.epub"]

    toggled: list[bool] = []
    toggle = Toggle(frame, text="Dark", value=False, on_change=toggled.append)
    toggle.pack()
    toggle.set(True)
    assert toggle.get() is True
    assert toggled[-1] is True

    section = Section(frame, "Opcje")
    section.pack()
    Tooltip(toggle, "Tooltip text")

    text = tk.Text(frame)
    text.pack()
    streamer = LogStreamer(text)
    streamer.write("ok\n", "ok")
    streamer.clear()

    apply_theme(root, DARK)
    root.update_idletasks()


def test_app_creates_saves_config_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """App startuje, pokazuje status narzędzi i zapisuje config przy zamknięciu."""
    try:
        tools = {
            "pandoc": Tool("pandoc", None, available=False),
            "calibre_ebook_convert": Tool(
                "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
            ),
            "sigil": Tool("sigil", None, available=False),
            "kindle_previewer": Tool("kindle_previewer", None, available=False),
        }
        monkeypatch.setattr(app_module, "detect_with_cache", lambda config_path: tools)
        app = App(config_path=tmp_path / "config.json")
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")

    app.withdraw()
    assert "Calibre: OK" in app.status_var.get()
    app._set_theme_setting("light")
    assert app.theme_name == "light"
    app._on_close()
    import json

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "light"


def test_file_list_survives_dnd_tclerror(
    root: tk.Tk,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FileList tworzy się i działa, nawet gdy rejestracja D&D rzuca TclError."""

    def boom(*args: object, **kwargs: object) -> None:
        raise tk.TclError('invalid command name "tkdnd::drop_target"')

    monkeypatch.setattr(file_list_module, "HAS_DND", True)
    monkeypatch.setattr(tk.Listbox, "drop_target_register", boom, raising=False)
    monkeypatch.setattr(tk.Listbox, "dnd_bind", boom, raising=False)

    file_list = FileList(root, extensions={".epub"})
    file_list.pack()
    # Brak crasha; lista nadal przyjmuje pliki przez API.
    file_list.add_files([tmp_path / "book.epub"])
    assert file_list.files() == [tmp_path / "book.epub"]
