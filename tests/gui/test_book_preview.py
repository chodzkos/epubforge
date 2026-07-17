"""Testy widgetu ``BookPreview`` — wybór backendu, fallback, config, motyw."""

from __future__ import annotations

import pytest
from chodzkos_gui_kit.palette import DARK, LIGHT
from pytestqt.qtbot import QtBot

from epubforge.core import ConfigStore
from epubforge.gui.preview import book_preview as bp_mod
from epubforge.gui.preview.availability import WebEngineProbe
from epubforge.gui.preview.backend import BackendKind
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.settings import BACKEND_KEY, PreviewSettings
from epubforge.gui.preview.webengine_backend import WebEngineInitError

pytestmark = pytest.mark.gui


def test_defaults_to_text_backend_without_webengine(qtbot: QtBot) -> None:
    """Bez WebEngine (środowisko testowe) aktywny jest lekki backend tekstowy."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    assert preview.active_kind is BackendKind.TEXT


def test_render_shows_content(qtbot: QtBot) -> None:
    """Render wyświetla treść dokumentu w lekkim backendzie."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.render("<html><body><h1>ZNACZNIK</h1></body></html>", None, None)
    assert "ZNACZNIK" in preview.html_preview.view.toPlainText()


def test_forced_webengine_unavailable_falls_back(qtbot: QtBot) -> None:
    """Wymuszony Dokładny bez WebEngine → lekki backend + oferta szybkiego."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.backend_combo.setCurrentIndex(1)  # Dokładny
    assert preview.active_kind is BackendKind.TEXT
    assert not preview.fallback_label.isHidden()
    assert not preview.use_fast_button.isHidden()
    preview.use_fast_button.click()
    assert preview.backend_combo.currentIndex() == 2  # Szybki


def test_init_exception_falls_back(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wyjątek inicjalizacji WebEngine nie wywraca GUI — cichy fallback."""
    monkeypatch.setattr(bp_mod, "probe_webengine", lambda: WebEngineProbe(True, ""))

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise WebEngineInitError("symulowana awaria")

    monkeypatch.setattr(bp_mod, "WebEnginePreviewBackend", _boom)
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.backend_combo.setCurrentIndex(1)  # Dokładny wymuszony
    assert preview.active_kind is BackendKind.TEXT
    assert not preview.fallback_label.isHidden()


def test_backend_choice_persists_via_configstore(qtbot: QtBot, tmp_path: object) -> None:
    """Wybór backendu zapisuje się przez istniejący ConfigStore (on_dirty)."""
    store = ConfigStore("epubforge", path=tmp_path / "config.json")  # type: ignore[operator]
    fired: list[str] = []
    store.on_dirty = lambda: fired.append("dirty")
    preview = BookPreview(settings=PreviewSettings(store))
    qtbot.addWidget(preview)
    preview.backend_combo.setCurrentIndex(2)  # Szybki
    assert store[BACKEND_KEY] == "text"
    assert fired, "zmiana backendu powinna oznaczyć config jako brudny"


def test_theme_change_does_not_rerender(qtbot: QtBot) -> None:
    """Zmiana motywu przemalowuje chrome, ale NIE renderuje ponownie książki."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.render("<html><body><p>x</p></body></html>", None, None)
    before = preview.render_count
    preview.set_theme(DARK)
    preview.set_theme(LIGHT)
    assert preview.render_count == before
