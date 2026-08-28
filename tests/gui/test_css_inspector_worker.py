"""Lifecycle ciężkiego parsera arkusza CSS poza wątkiem GUI."""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QThread
from pytestqt.qtbot import QtBot

import epubforge.gui.widgets.css_inspector as inspector_module
import epubforge.gui.widgets.css_sheet_loader as sheet_loader_module
from epubforge.gui.widgets.css_inspector import CssInspector

pytestmark = pytest.mark.gui


def _many_rules(count: int) -> str:
    return "\n".join(f".rule-{index} {{ color: red }}" for index in range(count))


def test_heavy_sheet_parse_runs_outside_gui_thread(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Koszt pure-data dla dużego, dozwolonego arkusza nie blokuje GUI thread."""
    source = _many_rules(5000)
    gui_thread = QThread.currentThread()
    parser_threads: list[QThread] = []
    original = inspector_module.parse_rules_bounded

    def recorded_parse(*args: object, **kwargs: object):
        parser_threads.append(QThread.currentThread())
        return original(*args, **kwargs)

    monkeypatch.setattr(inspector_module, "parse_rules_bounded", recorded_parse)
    inspector = CssInspector(get_source=lambda: source)
    qtbot.addWidget(inspector)
    qtbot.waitUntil(lambda: len(inspector._rules) == 5000, timeout=5000)
    assert parser_threads
    assert parser_threads[0] is not gui_thread


def test_new_sheet_invalidates_stale_worker_result(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spóźniony parse starego snapshotu nie może wygrać z nowym źródłem."""
    slow = _many_rules(5000)
    fast = _many_rules(100)
    state = {"source": slow}
    started = threading.Event()
    release = threading.Event()
    original = inspector_module.parse_rules_bounded

    def delayed_parse(source: str, **kwargs: int):
        if source == slow:
            started.set()
            release.wait(5)
        return original(source, **kwargs)

    monkeypatch.setattr(inspector_module, "parse_rules_bounded", delayed_parse)
    inspector = CssInspector(get_source=lambda: state["source"])
    qtbot.addWidget(inspector)
    assert started.wait(2)
    state["source"] = fast
    inspector.refresh()
    release.set()
    qtbot.waitUntil(lambda: len(inspector._rules) == 100, timeout=5000)
    assert inspector._source == fast


def test_dispose_does_not_wait_for_cooperative_parser(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zamknięcie nie zamraża GUI, gdy tinycss2 kończy już rozpoczęty parse."""
    source = _many_rules(5000)
    started = threading.Event()
    release = threading.Event()
    original = inspector_module.parse_rules_bounded

    def delayed_parse(text: str, **kwargs: int):
        started.set()
        release.wait(5)
        return original(text, **kwargs)

    monkeypatch.setattr(inspector_module, "parse_rules_bounded", delayed_parse)
    inspector = CssInspector(get_source=lambda: source)
    qtbot.addWidget(inspector)
    assert started.wait(2)
    before = time.perf_counter()
    inspector.dispose()
    elapsed = time.perf_counter() - before
    release.set()
    qtbot.waitUntil(lambda: not sheet_loader_module._RETIRED_WORKERS, timeout=5000)
    assert elapsed < 0.2
