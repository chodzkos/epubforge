"""Testy kontrolek symulatora z atrapą dokładnego backendu."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.preview import book_preview as bp_mod
from epubforge.gui.preview import reader_ui as reader_ui_mod
from epubforge.gui.preview import reader_webengine as reader_webengine_mod
from epubforge.gui.preview.availability import WebEngineProbe
from epubforge.gui.preview.backend import BackendKind, PreviewBackend, PreviewSnapshot, PreviewState
from epubforge.gui.preview.book_preview import BookPreview
from epubforge.gui.preview.quality import QualityIssue
from epubforge.gui.preview.reader import (
    READER_PROFILES,
    ComparisonMode,
    ReaderProfile,
    UserStyleSettings,
)
from epubforge.gui.preview.reader_webengine import ReaderWebEngineMixin
from epubforge.gui.preview.settings import PreviewSettings
from epubforge.gui.preview.webengine_state import CAPTURE_SCRIPT, READER_STATE_SCRIPT

pytestmark = pytest.mark.gui


class _FakeWebEngine(PreviewBackend):
    """Minimalny backend rejestrujący wywołania bez importu Chromium."""

    instances: ClassVar[list[_FakeWebEngine]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__()
        self.kind = BackendKind.WEBENGINE
        self.reader_calls: list[tuple[ReaderProfile, UserStyleSettings, ComparisonMode]] = []
        self.snapshots: list[PreviewSnapshot] = []
        self.focused: list[str] = []
        self.disposed = False
        self.session: object = None
        self.instances.append(self)

    def set_session(self, session: object) -> None:
        self.session = session

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        self.snapshots.append(snapshot)

    def capture_state(self) -> PreviewState:
        return PreviewState(node_id="selected")

    def restore_state(self, state: PreviewState) -> None:
        pass

    def focus_node(self, node_id: str) -> None:
        self.focused.append(node_id)

    def set_reader_simulation(
        self,
        profile: ReaderProfile,
        user_style: UserStyleSettings,
        comparison: ComparisonMode,
    ) -> None:
        self.reader_calls.append((profile, user_style, comparison))

    def run_quality_diagnostics(
        self, *, min_font_px: float = 12.0, min_line_height: float = 1.1, accessibility: bool = True
    ) -> None:
        self.quality_diagnostics.emit(
            (QualityIssue("element_overflow", "quality_warning", "Overflow", "node-1"),)
        )

    def set_theme(self, palette: object) -> None:
        pass

    def dispose(self) -> None:
        self.disposed = True


class _Emitter:
    def __init__(self) -> None:
        self.values: list[object] = []

    def emit(self, value: object) -> None:
        self.values.append(value)


class _ScriptPage:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def runJavaScript(self, script: str, _world: int, callback: object = None) -> None:  # noqa: N802
        self.scripts.append(script)
        if not callable(callback):
            return
        if script == CAPTURE_SCRIPT:
            callback({"node_id": "selected-node", "scroll_ratio": 0.4})
        elif script == READER_STATE_SCRIPT:
            callback({"page": 1, "pages": 2})
        else:
            callback(True)


class _ViewportObject:
    def __init__(self) -> None:
        self.size: tuple[int, int] | None = None

    def setFixedSize(self, width: int, height: int) -> None:  # noqa: N802
        self.size = (width, height)

    def setToolTip(self, _text: str) -> None:  # noqa: N802
        pass


class _GrabResult:
    def __init__(self) -> None:
        self.saved: tuple[str, str] | None = None

    def save(self, path: str, image_format: str) -> bool:
        self.saved = (path, image_format)
        return True


class _ScreenshotViewport(_ViewportObject):
    def __init__(self) -> None:
        super().__init__()
        self.result = _GrabResult()

    def grab(self) -> _GrabResult:
        return self.result


class _ReaderHost(ReaderWebEngineMixin):
    def __init__(self) -> None:
        self._page = _ScriptPage()
        self._view = _ViewportObject()
        self._viewport_frame = _ViewportObject()
        self._last_snapshot = PreviewSnapshot("", None, None)
        self._last_state = PreviewState()
        self._expected_generation = 1
        self.reader_state_changed = _Emitter()
        self.quality_diagnostics = _Emitter()
        self.cache_changed = _Emitter()
        self.restored: list[PreviewState] = []
        self._init_reader_engine()

    def restore_state(self, state: PreviewState) -> None:
        self.restored.append(state)


@pytest.fixture
def exact_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeWebEngine.instances.clear()
    monkeypatch.setattr(bp_mod, "preview_scheme_registered", lambda: True)
    monkeypatch.setattr(bp_mod, "probe_webengine", lambda: WebEngineProbe(True, ""))
    monkeypatch.setattr(bp_mod, "WebEnginePreviewBackend", _FakeWebEngine)
    monkeypatch.setattr(reader_ui_mod, "WebEnginePreviewBackend", _FakeWebEngine)


def test_profile_and_user_style_reach_exact_backend(qtbot: QtBot, exact_backend: None) -> None:
    settings = PreviewSettings()
    settings.backend = "webengine"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    backend = _FakeWebEngine.instances[0]

    preview.profile_combo.setCurrentIndex(preview.profile_combo.findData("phone-portrait"))
    preview.reader_settings_button.setChecked(True)
    preview.font_size_spin.setValue(26)
    preview.comparison_combo.setCurrentIndex(
        preview.comparison_combo.findData(ComparisonMode.PUBLISHER_USER.value)
    )

    profile, user, comparison = backend.reader_calls[-1]
    assert profile.key == "phone-portrait"
    assert user.font_size_px == 26
    assert comparison is ComparisonMode.PUBLISHER_USER


def test_two_profiles_render_side_by_side_and_are_disposed(
    qtbot: QtBot, exact_backend: None
) -> None:
    settings = PreviewSettings()
    settings.backend = "webengine"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    preview.render_document("<html><body><p>x</p></body></html>", None, None)

    preview.reader_settings_button.setChecked(True)
    preview.compare_profiles_button.setChecked(True)
    assert len(_FakeWebEngine.instances) == 2
    second = _FakeWebEngine.instances[1]
    assert second.snapshots
    assert preview._body_layout.indexOf(second) >= 0

    preview.compare_profiles_button.setChecked(False)
    assert second.disposed is True
    assert preview._comparison_backend is None


def test_quality_diagnostic_is_visible(qtbot: QtBot, exact_backend: None) -> None:
    settings = PreviewSettings()
    settings.backend = "webengine"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)
    preview.diagnostics_button.click()
    assert preview.diagnostics_tree.topLevelItemCount() == 1
    assert "Overflow" in preview.diagnostics_tree.topLevelItem(0).text(1)
    assert not preview.diagnostics_tree.isHidden()

    preview.diagnostics_button.click()
    assert preview.diagnostics_tree.isHidden()


def test_custom_viewport_and_flow_are_persisted(qtbot: QtBot, exact_backend: None) -> None:
    store: dict[str, object] = {}
    settings = PreviewSettings(store)
    settings.backend = "webengine"
    preview = BookPreview(settings=settings)
    qtbot.addWidget(preview)

    preview.profile_combo.setCurrentIndex(preview.profile_combo.findData("custom"))
    preview.viewport_width_spin.setValue(712)
    preview.viewport_height_spin.setValue(934)
    preview.flow_combo.setCurrentIndex(preview.flow_combo.findData("pages"))

    assert settings.custom_viewport["width"] == 712
    assert settings.custom_viewport["height"] == 934
    assert settings.custom_viewport["flow"] == "pages"


def test_reader_toolbar_scrolls_instead_of_clipping_buttons(qtbot: QtBot) -> None:
    """Wąski panel zachowuje naturalne szerokości długich etykiet i dostaje scroll."""
    preview = BookPreview()
    qtbot.addWidget(preview)
    preview.resize(650, 500)
    preview.show()
    qtbot.waitExposed(preview)
    preview.reader_toolbar.setFixedWidth(260)
    qtbot.waitUntil(lambda: preview.reader_toolbar.horizontalScrollBar().maximum() > 0)

    button = preview.reader_settings_button
    assert button.width() >= button.minimumSizeHint().width()
    assert button.toolTip()


def test_profile_change_restores_selected_element() -> None:
    host = _ReaderHost()
    profile = READER_PROFILES["eink-small"]
    host.set_reader_simulation(profile, profile.user_style, ComparisonMode.PUBLISHER_USER)

    assert host._last_state.node_id == "selected-node"
    assert host.restored and host.restored[-1].node_id == "selected-node"
    assert any("epubforge-reader-user-layer" in script for script in host._page.scripts)


def test_reader_layers_are_inert_until_explicitly_enabled() -> None:
    host = _ReaderHost()

    host._apply_reader_layers()

    assert host.restored == []
    assert not any("epubforge-reader-simulator-layer" in script for script in host._page.scripts)
    assert host.reader_state_changed.values[-1]["enabled"] is False
    assert host.reader_state_changed.values[-1]["columns_enabled"] is False
    assert host.reader_state_changed.values[-1]["overrides"] == {}


def test_screenshot_hides_inspector_overlay_and_restores_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regresja strukturalna jest stabilniejsza niż piksele poza przypiętym Qt CI."""
    monkeypatch.setattr(
        reader_webengine_mod.QTimer, "singleShot", lambda _delay, callback: callback()
    )
    host = _ReaderHost()
    viewport = _ScreenshotViewport()
    host._view = viewport
    target = str(tmp_path / "viewport.png")

    assert host.export_viewport(target)
    assert viewport.result.saved == (target, "PNG")
    assert "node.disabled = true" in host._page.scripts[-2]
    assert "node.disabled = item.disabled" in host._page.scripts[-1]
