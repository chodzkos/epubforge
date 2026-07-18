"""Regresja: profil dokładnego podglądu nigdy nie akceptuje pobrań."""

from __future__ import annotations

import pytest

from epubforge.gui.preview.webengine_security import _cancel_download

pytestmark = pytest.mark.gui


class _FakeDownload:
    """Minimalny dublet żądania pobrania do testu polityki cancel-only."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        """Zapamiętuje anulowanie bez zapisu na dysku."""
        self.cancelled = True


def test_download_is_always_cancelled() -> None:
    """Callback profilu wykonuje wyłącznie cancel, nigdy accept."""
    download = _FakeDownload()
    _cancel_download(download)  # type: ignore[arg-type] - kontrolowany dublet Qt
    assert download.cancelled
