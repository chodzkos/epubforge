"""Testy konfiguracji bezpieczeństwa prywatnego profilu Qt WebEngine."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.gui

_WEBENGINE_AVAILABLE = importlib.util.find_spec("PySide6.QtWebEngineCore") is not None

_PROFILE_SCRIPT = r"""
import gc
import weakref

from PySide6.QtCore import QObject
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import QApplication

from epubforge.gui.preview.preinit import preinit_webengine

assert preinit_webengine(), "schemat WebEngine nie został zarejestrowany"

from epubforge.gui.preview.webengine_security import create_secure_profile, make_reply_buffer

app = QApplication([])
owner = QObject()
profile, registry, handler, interceptor = create_secure_profile(owner)
assert profile.isOffTheRecord()
assert profile.httpCacheType() == QWebEngineProfile.HttpCacheType.NoCache
assert (
    profile.persistentCookiesPolicy()
    == QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
)
assert (
    profile.persistentPermissionsPolicy()
    == QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime
)
assert not profile.isPushServiceEnabled()
assert not profile.isSpellCheckEnabled()
assert handler.parent() is profile
assert interceptor.parent() is profile
registry.clear()

parent = QObject()
buffer = make_reply_buffer(b"sekret", parent)
reference = weakref.ref(buffer)
del buffer
gc.collect()
assert reference() is not None
assert reference() is not None and reference().parent() is parent
assert reference() is not None and bytes(reference().readAll()) == b"sekret"

from epubforge.gui.preview.backend import PreviewSnapshot
from epubforge.gui.preview.webengine_backend import WebEnginePreviewBackend

backend = WebEnginePreviewBackend()
backend._last_snapshot = PreviewSnapshot("", None, None)
fallbacks = []
backend.fallback_requested.connect(fallbacks.append)
status = backend._page.RenderProcessTerminationStatus.CrashedTerminationStatus
backend._on_renderer_terminated(status, 1)
assert fallbacks == []
backend._on_renderer_terminated(status, 1)
assert len(fallbacks) == 1
backend.dispose()
"""


@pytest.mark.skipif(not _WEBENGINE_AVAILABLE, reason="Brak Qt WebEngine")
def test_secure_profile_and_reply_buffer_in_isolated_process() -> None:
    """Profil i natywne procesy Chromium nie przeżywają procesu testowego."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _PROFILE_SCRIPT],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
