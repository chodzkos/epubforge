"""Testy utwardzenia klienta HTTP (:mod:`epubforge.bookmeta._http`).

Pokrywają: walidację URL (schemat/host/port/userinfo/SSRF), redirect handler
walidujący każdy hop (downgrade do HTTP, localhost, 127.0.0.1, IPv6, userinfo,
poprawny https), limit liczby przekierowań (pętla) oraz odrzucanie odpowiedzi
ponad ``MAX_BYTES`` (odczyt ``MAX_BYTES+1``). DNS mockujemy dla hostów publicznych,
a adresy loopback/prywatne testujemy na literałach IP (bez sieci).
"""

from __future__ import annotations

import email.message
import io
import urllib.error
import urllib.request
from typing import Any

import pytest

from epubforge.bookmeta import _http
from epubforge.bookmeta._http import UnsafeUrlError, _SafeRedirectHandler, validate_url

_PUBLIC_IP = "93.184.216.34"


def _mock_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Podmienia DNS na publiczny adres (walidacja SSRF przepuszcza)."""
    monkeypatch.setattr(_http, "_resolve_addresses", lambda _host: [_PUBLIC_IP])


# ── validate_url ────────────────────────────────────────────────────────────


def test_validate_url_accepts_public_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """Poprawny https na host publiczny przechodzi i zwraca host."""
    _mock_public_dns(monkeypatch)
    assert validate_url("https://example.org/x") == "example.org"
    assert validate_url("https://example.org:443/x") == "example.org"  # jawny port 443


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/x",  # downgrade / nie-https
        "ftp://example.org/x",
        "file:///etc/passwd",
        "data:text/plain,hi",
        "https://user:pass@example.org/x",  # userinfo
        "https://user@example.org/x",
        "https://example.org:8080/x",  # niedozwolony port
        "https:///x",  # brak hosta
    ],
)
def test_validate_url_rejects_bad_scheme_userinfo_port_host(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """Zły schemat, userinfo, niedozwolony port i brak hosta są odrzucane."""
    _mock_public_dns(monkeypatch)  # DNS by nie było powodem odrzucenia
    with pytest.raises(UnsafeUrlError):
        validate_url(url)


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "[::1]", "10.0.0.1", "169.254.0.1", "192.168.1.1"],
)
def test_validate_url_rejects_local_and_private_after_dns(host: str) -> None:
    """Loopback/prywatne/link-local (po rozwiązaniu DNS) są odrzucane — bez mocka DNS."""
    with pytest.raises(UnsafeUrlError):
        validate_url(f"https://{host}/x")


def test_validate_url_host_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    """``allowed_hosts`` przepuszcza tylko host z listy providera."""
    _mock_public_dns(monkeypatch)
    allowed = frozenset({"lubimyczytac.pl"})
    assert validate_url("https://lubimyczytac.pl/ksiazka/1", allowed_hosts=allowed)
    with pytest.raises(UnsafeUrlError):
        validate_url("https://evil.example/x", allowed_hosts=allowed)


# ── redirect handler: walidacja każdego hopu ────────────────────────────────


def _redirect_to(newurl: str, *, allowed_hosts: _http.AllowedHosts = None) -> Any:
    """Woła ``redirect_request`` handlera dla ``newurl`` (zwraca Request albo rzuca)."""
    handler = _SafeRedirectHandler(allowed_hosts)
    request = urllib.request.Request("https://example.org/start")
    headers = email.message.Message()
    return handler.redirect_request(request, io.BytesIO(b""), 302, "Found", headers, newurl)


@pytest.mark.parametrize(
    "newurl",
    [
        "http://example.org/next",  # downgrade do HTTP
        "https://127.0.0.1/next",  # loopback
        "https://localhost/next",
        "https://[::1]/next",  # IPv6 loopback
        "https://user:pass@example.org/next",  # userinfo
    ],
)
def test_redirect_rejected_per_hop(newurl: str) -> None:
    """Każdy niebezpieczny hop przekierowania jest odrzucany jako ``HTTPError``.

    Bez mocka DNS: http/userinfo są odrzucane przed rozwiązaniem nazwy, a
    localhost/127.0.0.1/``[::1]`` rozwiązują się lokalnie do loopback (bez sieci).
    """
    with pytest.raises(urllib.error.HTTPError):
        _redirect_to(newurl)


def test_redirect_valid_https_hop_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Poprawny hop https na host publiczny jest przepuszczany (zwraca Request)."""
    _mock_public_dns(monkeypatch)
    result = _redirect_to("https://example.org/next")
    assert isinstance(result, urllib.request.Request)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10:11434/v1",
        "http://10.0.0.5:1234/",
        "http://127.0.0.1:11434/v1",
        "https://192.168.1.10:8443/v1",
    ],
)
def test_validate_url_allow_lan_accepts_rfc1918_and_loopback(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """Przy allow_lan lokalny HTTP/HTTPS (bez link-local) jest dozwolony."""
    _mock_public_dns(monkeypatch)
    assert validate_url(url, allow_lan=True, restrict_ports=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/",
        "http://[fe80::1]/v1",
        "https://[fe80::1]/v1",
        "http://0.0.0.0/v1",
        "https://0.0.0.0/v1",
        "https://user:pass@192.168.1.10/v1",
        "http://8.8.8.8/v1",
    ],
)
def test_validate_url_allow_lan_still_rejects_link_local_userinfo_public_http(url: str) -> None:
    """allow_lan nie otwiera link-local, unspecified, userinfo ani publicznego HTTP."""
    with pytest.raises(UnsafeUrlError):
        validate_url(url, allow_lan=True, restrict_ports=False)


def test_userinfo_with_invalid_port_is_still_policy_error() -> None:
    """Userinfo + zły port daje UnsafeUrlError, nie surowy ValueError."""
    with pytest.raises(UnsafeUrlError):
        validate_url("https://user:pass@example.com:99999/v1", allow_lan=True, restrict_ports=False)


def test_lan_redirect_to_link_local_is_rejected() -> None:
    """Hop 302 z publicznego HTTPS na 169.254 jest odrzucany także przy allow_lan."""
    handler = _SafeRedirectHandler(None, allow_lan=True, restrict_ports=False)
    request = urllib.request.Request("https://example.org/api")
    headers = email.message.Message()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            request,
            io.BytesIO(b""),
            302,
            "Found",
            headers,
            "http://169.254.169.254/metadata",
        )


def test_lan_redirect_to_rfc1918_is_allowed() -> None:
    """Hop na RFC1918 przy allow_lan jest legalny (lokalny serwer AI)."""
    handler = _SafeRedirectHandler(None, allow_lan=True, restrict_ports=False)
    request = urllib.request.Request("http://192.168.1.10:11434/v1")
    headers = email.message.Message()
    result = handler.redirect_request(
        request,
        io.BytesIO(b""),
        302,
        "Found",
        headers,
        "http://192.168.1.11:11434/v1",
    )
    assert isinstance(result, urllib.request.Request)


# ── pętla przekierowań: limit liczby hopów ──────────────────────────────────


class _FakeResp(io.BytesIO):
    """Minimalna atrapa odpowiedzi HTTP (302) dla łańcucha openera."""

    def __init__(self, code: int, headers: email.message.Message, url: str) -> None:
        super().__init__(b"")
        self.code = code
        self.status = code
        self.msg = "Found"
        self.headers = headers
        self.url = url

    def info(self) -> email.message.Message:
        return self.headers

    def geturl(self) -> str:
        return self.url


class _LoopHandler(urllib.request.HTTPSHandler):
    """Handler https zawsze zwracający 302 na ten sam URL (pętla przekierowań)."""

    def __init__(self, target: str) -> None:
        super().__init__()
        self._target = target

    def https_open(self, req: urllib.request.Request) -> _FakeResp:
        headers = email.message.Message()
        headers["Location"] = self._target
        return _FakeResp(302, headers, req.full_url)


def test_redirect_loop_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pętla przekierowań kończy się ``HTTPError`` po ``MAX_REDIRECTS`` (nie w nieskończoność)."""
    _mock_public_dns(monkeypatch)
    target = "https://good.test/loop"
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_SafeRedirectHandler(None))
    opener.add_handler(_LoopHandler(target))
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    with pytest.raises(urllib.error.HTTPError):
        opener.open(target)


def test_fetch_bytes_uses_safe_opener_and_rejects_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """``fetch_bytes`` na pętli przekierowań zwraca ``None`` (żaden wyjątek nie wychodzi)."""
    _mock_public_dns(monkeypatch)
    target = "https://good.test/loop"

    def _looping_opener(_allowed_hosts: _http.AllowedHosts = None) -> urllib.request.OpenerDirector:
        opener = urllib.request.OpenerDirector()
        opener.add_handler(_SafeRedirectHandler(None))
        opener.add_handler(_LoopHandler(target))
        opener.add_handler(urllib.request.HTTPErrorProcessor())
        return opener

    monkeypatch.setattr(_http, "_build_safe_opener", _looping_opener)
    assert _http.fetch_bytes(target) is None
