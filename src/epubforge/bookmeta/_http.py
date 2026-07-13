"""Bezpieczny klient HTTP dla providerów metadanych (jedyny kod sieciowy projektu).

Cała warstwa sieciowa przechodzi przez ten moduł, żeby twarde zasady bezpieczeństwa
(lekcja D2 z audytu ``chodzkos-detection``) obowiązywały w jednym miejscu i nie dało
się ich obejść w pojedynczym providerze:

* **wyłącznie ``https``** — schemat, host i port są walidowane przez ``urlsplit``
  PRZED połączeniem (``file:``/``data:``/``http:`` i userinfo są odrzucane);
* **ochrona przed SSRF** — host jest rozwiązywany przez DNS, a adresy loopback /
  prywatne / link-local / reserved / multicast są odrzucane (żadnych żądań do
  sieci lokalnej ani metadanych chmury);
* **walidacja każdego przekierowania** — własny redirect handler sprawdza KAŻDY
  hop przed kolejnym żądaniem (brak downgrade do HTTP, brak skoku na host loopback/
  prywatny, opcjonalny pin hostów per provider), a liczba redirectów jest ograniczona;
* **twardy timeout** — żadne zapytanie nie blokuje wątku w nieskończoność;
* **limit rozmiaru odpowiedzi** — czytamy ``MAX_BYTES + 1`` i odrzucamy odpowiedź
  przekraczającą limit (zamiast po cichu ucinać i zwracać zepsuty JSON);
* **żaden błąd nie wychodzi na zewnątrz** — każdy wyjątek ląduje w ``logger.debug``
  i zwracamy ``None`` (warstwa UI nigdy nie widzi wyjątku).

Zależności: wyłącznie stdlib ``urllib``/``socket``/``ipaddress`` — bez ``requests``.

Uwaga o TOCTOU: sprawdzamy IP po rozwiązaniu DNS, ale nie pinujemy go do gniazda,
więc teoretyczny DNS-rebinding między walidacją a połączeniem pozostaje poza
zakresem tej warstwy (metadane i tak idą przez cache + rate limiter).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Twardy limit rozmiaru odpowiedzi w bajtach (D2). Odpowiedzi metadanych z BN /
# Open Library / Google Books to kilka-kilkadziesiąt kB; 1 MB to bezpieczny sufit.
MAX_BYTES = 1_000_000
# Domyślny timeout pojedynczego zapytania (sekundy).
DEFAULT_TIMEOUT = 5
# Maksymalna liczba przekierowań (każdy hop i tak jest walidowany).
MAX_REDIRECTS = 5
# Dozwolone porty dla https (None = domyślny 443).
_ALLOWED_PORTS = frozenset({None, 443})
# Nagłówek identyfikujący klienta (grzecznościowo wobec darmowych API).
_USER_AGENT = "EpubForge (+https://github.com/chodzkos/epubforge)"

# Zbiór dozwolonych hostów (pin per provider) albo ``None`` (dowolny host publiczny).
AllowedHosts = frozenset[str] | None


class UnsafeUrlError(ValueError):
    """URL odrzucony przez politykę bezpieczeństwa (schemat/host/port/userinfo/SSRF)."""


def _resolve_addresses(host: str) -> list[str]:
    """Zwraca adresy IP (v4/v6) hosta z DNS; pusta lista przy braku."""
    infos = socket.getaddrinfo(host, None)
    return [str(info[4][0]) for info in infos]


def _is_forbidden_ip(address: str) -> bool:
    """Czy adres należy do zakresu niedozwolonego dla żądań (loopback/prywatny/…)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True  # nierozpoznany adres — traktuj jako niedozwolony
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str, *, allowed_hosts: AllowedHosts = None) -> str:
    """Waliduje URL wg polityki bezpieczeństwa; zwraca host albo rzuca wyjątek.

    Sprawdza (w tej kolejności): dokładny schemat ``https``, brak userinfo, obecność
    hosta, dozwolony port, opcjonalny pin ``allowed_hosts`` oraz — po rozwiązaniu
    DNS — że żaden adres hosta nie jest loopback/prywatny/link-local/reserved.

    Args:
        url: pełny adres do sprawdzenia.
        allowed_hosts: gdy podane, host musi należeć do tego zbioru (pin per provider).

    Returns:
        Host (lowercase) — do dalszego logowania/pinowania.

    Raises:
        UnsafeUrlError: przy dowolnym naruszeniu polityki.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeUrlError(f"Niedozwolony schemat {parts.scheme!r} (wymagane https): {url!r}")
    if parts.username or parts.password:
        raise UnsafeUrlError(f"URL zawiera userinfo (login/hasło) — odrzucone: {url!r}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError(f"URL bez hosta: {url!r}")
    host = host.lower()
    try:
        port = parts.port
    except ValueError as exc:  # niepoprawny port w URL
        raise UnsafeUrlError(f"Niepoprawny port w URL {url!r}: {exc}") from exc
    if port not in _ALLOWED_PORTS:
        raise UnsafeUrlError(f"Niedozwolony port {port} w URL: {url!r}")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise UnsafeUrlError(f"Host {host!r} spoza dozwolonej listy providera: {url!r}")
    try:
        addresses = _resolve_addresses(host)
    except OSError as exc:
        raise UnsafeUrlError(f"Nie udało się rozwiązać hosta {host!r}: {exc}") from exc
    if not addresses:
        raise UnsafeUrlError(f"Host {host!r} nie ma adresów IP: {url!r}")
    for address in addresses:
        if _is_forbidden_ip(address):
            raise UnsafeUrlError(f"Host {host!r} → niedozwolony adres {address} (SSRF): {url!r}")
    return host


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler walidujący KAŻDY hop przez :func:`validate_url` przed skokiem."""

    max_redirections = MAX_REDIRECTS

    def __init__(self, allowed_hosts: AllowedHosts = None) -> None:
        self._allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Waliduje cel przekierowania; przy naruszeniu polityki podnosi ``HTTPError``."""
        try:
            validate_url(newurl, allowed_hosts=self._allowed_hosts)
        except UnsafeUrlError as exc:
            raise urllib.error.HTTPError(
                newurl, code, f"Odrzucony redirect: {exc}", headers, fp
            ) from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_safe_opener(allowed_hosts: AllowedHosts) -> urllib.request.OpenerDirector:
    """Buduje opener z bezpiecznym redirect handlerem (bez domyślnego, który nie waliduje)."""
    return urllib.request.build_opener(_SafeRedirectHandler(allowed_hosts))


def fetch_bytes(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
    allowed_hosts: AllowedHosts = None,
) -> bytes | None:
    """Pobiera treść spod ``https`` URL, zwracając ``None`` przy dowolnym błędzie.

    Args:
        url: pełny adres — waliduje :func:`validate_url` (https, host, port, brak
            userinfo, nie-lokalny po DNS) przed połączeniem.
        timeout: maksymalny czas oczekiwania na odpowiedź w sekundach.
        user_agent: opcjonalny nagłówek ``User-Agent`` (domyślnie :data:`_USER_AGENT`).
        allowed_hosts: opcjonalny pin dozwolonych hostów (per provider).

    Returns:
        Do :data:`MAX_BYTES` bajtów treści albo ``None`` (URL odrzucony przez
        politykę, błąd sieci, timeout, błąd HTTP, odpowiedź ponad limit) — funkcja
        **nigdy nie rzuca wyjątku**.
    """
    try:
        validate_url(url, allowed_hosts=allowed_hosts)
    except UnsafeUrlError as exc:
        logger.debug("Odrzucono URL: %s", exc)
        return None
    request = urllib.request.Request(url, headers={"User-Agent": user_agent or _USER_AGENT})
    opener = _build_safe_opener(allowed_hosts)
    try:
        # Bezpieczny wrapper: schemat wymuszony na https, każdy redirect walidowany,
        # SSRF blokowany po DNS — dlatego opener.open jest tu bezpieczny (nie urlopen).
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("Nie udało się pobrać %s: %s", url, exc)
        return None
    if len(data) > MAX_BYTES:
        logger.debug("Odpowiedź z %s przekracza limit %d B — odrzucona.", url, MAX_BYTES)
        return None
    return bytes(data)


def fetch_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str | None = None,
    allowed_hosts: AllowedHosts = None,
) -> Any | None:
    """Pobiera i parsuje odpowiedź JSON spod ``https`` URL.

    Args:
        url: pełny adres ``https``.
        timeout: maksymalny czas oczekiwania w sekundach.
        user_agent: opcjonalny nagłówek ``User-Agent``.
        allowed_hosts: opcjonalny pin dozwolonych hostów (per provider).

    Returns:
        Zdekodowany obiekt JSON albo ``None``, gdy pobranie się nie powiodło lub
        treść nie jest poprawnym JSON-em (np. odrzucona przez limit :data:`MAX_BYTES`).
    """
    raw = fetch_bytes(url, timeout=timeout, user_agent=user_agent, allowed_hosts=allowed_hosts)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.debug("Niepoprawny JSON z %s: %s", url, exc)
        return None
