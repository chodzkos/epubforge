"""Testy panelu „O programie" (PySide6)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from epubforge import __version__
from epubforge.gui.widgets import about_panel as about_module
from epubforge.gui.widgets.about_panel import GITHUB_URL, AboutPanel

pytestmark = pytest.mark.gui


def test_about_shows_version_not_hardcoded(qtbot: QtBot) -> None:
    """Panel pokazuje wersję pochodzącą z epubforge.__version__."""
    panel = AboutPanel()
    qtbot.addWidget(panel)
    labels = panel.findChildren(QLabel)
    assert any(__version__ in label.text() for label in labels)


def test_about_github_link_opens_browser(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aktywacja linku GitHub otwiera URL przez webbrowser.open."""
    opened: list[str] = []
    monkeypatch.setattr(about_module.webbrowser, "open", lambda url: opened.append(url) or True)

    panel = AboutPanel()
    qtbot.addWidget(panel)
    panel._open(GITHUB_URL)

    assert opened == [GITHUB_URL]


def test_about_open_handles_browser_error(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd przeglądarki nie wywala aplikacji (łapany OSError)."""

    def boom(url: str) -> bool:
        raise OSError("no browser")

    monkeypatch.setattr(about_module.webbrowser, "open", boom)
    panel = AboutPanel()
    qtbot.addWidget(panel)
    panel._open(GITHUB_URL)  # brak wyjątku


def test_about_help_button_opens_offline_help(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przycisk „Pomoc" otwiera offline HelpWindow i dokłada zakładki po konstrukcji.

    W 0.5.3 zakładki (Markdown z plików + HTML narzędzi) dokładane są metodami
    ``add_markdown_section`` / ``add_html_section`` po konstrukcji, nie przez ``tabs=``.
    """
    captured: dict[str, object] = {}

    class _FakeHelp:
        def __init__(self, parent: object, *, title: str) -> None:
            captured["title"] = title
            captured["markdown"] = []
            captured["html"] = []

        def add_markdown_section(self, title: str, source: object) -> None:
            captured["markdown"].append((title, source))  # type: ignore[union-attr]

        def add_html_section(self, title: str, html: str) -> None:
            captured["html"].append(title)  # type: ignore[union-attr]

        def exec(self) -> int:
            captured["exec"] = True
            return 0

    monkeypatch.setattr(about_module, "HelpWindow", _FakeHelp)

    panel = AboutPanel()
    qtbot.addWidget(panel)

    help_buttons = [b for b in panel.findChildren(QPushButton) if b.text() == "Pomoc"]
    assert help_buttons, "brak przycisku Pomoc"
    help_buttons[0].click()

    assert captured.get("exec") is True
    assert captured.get("title") == "Pomoc — EpubForge"
    # 9 zakładek Markdown z plików + 1 zakładka HTML (narzędzia) = 10 sekcji.
    assert len(captured["markdown"]) == 9  # type: ignore[arg-type]
    assert captured["html"] == ["Narzędzia zewnętrzne"]
