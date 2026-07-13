"""Wspólny stub sieci dla testów bookmeta.

Po utwardzeniu :mod:`epubforge.bookmeta._http` warstwa sieciowa idzie przez własny
opener (``_build_safe_opener().open``) i walidację URL z rozwiązywaniem DNS. Testy
providerów mockują więc DWA punkty: opener (na router URL→treść, jak dawniej atrapa
``urlopen``) oraz DNS (``_resolve_addresses`` → publiczny adres, by walidacja SSRF
przepuściła realne hosty providerów bez sieci).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from epubforge.bookmeta import _http

# Publiczny, „bezpieczny" adres — walidacja SSRF go przepuszcza (nie loopback/prywatny).
_PUBLIC_IP = "93.184.216.34"


def patch_net(monkeypatch: pytest.MonkeyPatch, opener_fn: Callable[..., Any]) -> None:
    """Kieruje ``_http`` na atrapę: ``opener.open`` → ``opener_fn``, DNS → publiczny adres.

    ``opener_fn`` ma sygnaturę ``(request, timeout=None)`` — identyczną jak dawne
    atrapy ``urlopen``, więc istniejące routery URL→treść działają bez zmian.
    """

    class _FakeOpener:
        def open(self, request: Any, timeout: float | None = None) -> Any:
            return opener_fn(request, timeout)

    monkeypatch.setattr(_http, "_build_safe_opener", lambda _allowed_hosts=None: _FakeOpener())
    monkeypatch.setattr(_http, "_resolve_addresses", lambda _host: [_PUBLIC_IP])
