"""Testy konfiguracji bezpieczeństwa prywatnego profilu Qt WebEngine."""

from __future__ import annotations

import gc
import weakref

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWebEngineCore import QWebEngineProfile
from pytestqt.qtbot import QtBot

from epubforge.gui.preview.webengine_security import create_secure_profile, make_reply_buffer

pytestmark = pytest.mark.gui


def test_profile_is_off_the_record_without_persistence(qtbot: QtBot) -> None:
    """Dedykowany profil nie zapisuje cache, cookies ani uprawnień na dysku."""
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


def test_reply_buffer_lives_with_request_parent(qtbot: QtBot) -> None:
    """QBuffer nie jest zwalniany po wyjściu z handlera, bo jego parentem jest job."""
    parent = QObject()
    buffer = make_reply_buffer(b"sekret", parent)
    reference = weakref.ref(buffer)
    del buffer
    gc.collect()
    assert reference() is not None
    assert reference() is not None and reference().parent() is parent
    assert reference() is not None and bytes(reference().readAll()) == b"sekret"
