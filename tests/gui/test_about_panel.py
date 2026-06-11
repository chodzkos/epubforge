"""Testy panelu „O programie" (PySide6)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from epubforge import __version__
from epubforge.gui.widgets import about_panel as about_module
from epubforge.gui.widgets.about_panel import GITHUB_URL, HELP_URL, AboutPanel

pytestmark = pytest.mark.gui


def test_about_shows_version_not_hardcoded(qtbot: QtBot) -> None:
    """Panel pokazuje wersję pochodzącą z epubforge.__version__."""
    panel = AboutPanel()
    qtbot.addWidget(panel)
    labels = panel.findChildren(QLabel)
    assert any(__version__ in label.text() for label in labels)


def test_about_links_open_browser(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aktywacja linków otwiera odpowiednie URL przez webbrowser.open."""
    opened: list[str] = []
    monkeypatch.setattr(about_module.webbrowser, "open", lambda url: opened.append(url) or True)

    panel = AboutPanel()
    qtbot.addWidget(panel)
    panel._open(GITHUB_URL)
    panel._open(HELP_URL)

    assert opened == [GITHUB_URL, HELP_URL]


def test_about_open_handles_browser_error(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd przeglądarki nie wywala aplikacji (łapany OSError)."""

    def boom(url: str) -> bool:
        raise OSError("no browser")

    monkeypatch.setattr(about_module.webbrowser, "open", boom)
    panel = AboutPanel()
    qtbot.addWidget(panel)
    panel._open(GITHUB_URL)  # brak wyjątku
