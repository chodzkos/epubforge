"""Testy zakładki „O programie"."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator

import pytest

tk = pytest.importorskip("tkinter")

from epubforge import __version__
from epubforge.gui.tabs import about as about_module
from epubforge.gui.tabs.about import GITHUB_URL, HELP_URL, AboutTab

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


def test_about_shows_version_not_hardcoded(root: tk.Tk) -> None:
    """Wersja pochodzi z epubforge.__version__."""
    tab = AboutTab(root)
    assert __version__ in tab.version_label.cget("text")


def test_about_logo_fallback_without_file(root: tk.Tk) -> None:
    """Bez pliku logo pokazywany jest tekstowy zastępnik 'EpubForge'."""
    tab = AboutTab(root)
    assert tab._logo_image is None
    assert tab.logo_label.cget("text") == "EpubForge"


def test_about_links_open_browser(root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kliknięcie linków otwiera odpowiednie URL przez webbrowser.open."""
    opened: list[str] = []
    monkeypatch.setattr(about_module.webbrowser, "open", lambda url: opened.append(url) or True)

    tab = AboutTab(root)
    tab.github_link.event_generate("<Button-1>")
    tab.help_link.event_generate("<Button-1>")
    root.update()

    assert opened == [GITHUB_URL, HELP_URL]


def test_about_open_handles_browser_error(root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd przeglądarki nie wywala aplikacji."""

    def boom(url: str) -> bool:
        raise OSError("no browser")

    monkeypatch.setattr(about_module.webbrowser, "open", boom)
    tab = AboutTab(root)
    tab._open(GITHUB_URL)  # brak wyjątku
