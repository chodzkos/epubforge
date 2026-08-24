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

Opcja ``allow_lan`` (domyślnie wyłączona) jest wyłącznie dla lokalnego AI:
dopuszcza ``http``/``https`` do loopback i RFC1918/ULA, nadal blokując
link-local, unspecified, multicast i userinfo. Polityka LAN hopów jest
zamrażana na originie żądania (publiczny HTTPS nie może skoczyć na LAN).
Providerzy metadanych zostają przy twardym ``https`` + braku sieci prywatnej.

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
from urllib.parse import urlsplit, urlunsplit

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
# RFC1918 + IPv6 ULA — jawny LAN, bez link-local / unspecified z ``is_private``.
_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
# Nagłówek identyfikujący klienta (grzecznościowo wobec darmowych API).
_USER_AGENT = "EpubForge (+https://github.com/chodzkos/epubforge)"

# Zbiór dozwolonych hostów (pin per provider) albo ``None`` (dowolny host publiczny).
AllowedHosts = frozenset[str] | None


class UnsafeUrlError(ValueError):
    """URL odrzucony przez politykę bezpieczeństwa (schemat/host/port/userinfo/SSRF)."""


def _canonical_ip(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Parsuje adres; IPv4-mapped IPv6 sprowadza do IPv4."""
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _resolve_addresses(host: str) -> list[str]:
    """Zwraca adresy IP (v4/v6) hosta z DNS; pusta lista przy braku."""
    infos = socket.getaddrinfo(host, None)
    return [str(info[4][0]) for info in infos]


def _host_addresses(host: str) -> list[str]:
    """Dla literału IP pomija DNS; w przeciwnym razie rozwiązuje hostname."""
    try:
        return [str(_canonical_ip(host))]
    except ValueError:
        return _resolve_addresses(host)


def _is_forbidden_ip(address: str) -> bool:
    """Czy adres należy do zakresu niedozwolonego dla żądań (loopback/prywatny/…)."""
    try:
        ip = _canonical_ip(address)
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


def _is_lan_allowed_ip(address: str) -> bool:
    """Czy adres to loopback albo RFC1918/ULA — bez link-local i unspecified."""
    try:
        ip = _canonical_ip(address)
    except ValueError:
        return False
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        return False
    if ip.is_loopback:
        return True
    return any(ip in network for network in _LAN_NETWORKS)


def _origin_allows_lan(url: str) -> bool:
    """Czy origin to loopback/RFC1918/ULA — polityka hopów przy ``allow_lan``."""
    host = urlsplit(url).hostname
    if not host:
        return False
    host = host.lower()
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = _host_addresses(host)
    except OSError:
        return False
    return bool(addresses) and all(_is_lan_allowed_ip(address) for address in addresses)


def _url_origin(url: str) -> tuple[str, str, int] | None:
    """Zwraca ``(scheme, host, port)`` albo ``None``, gdy origin nie da się ustalić."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


def _is_cross_origin(current: str, newurl: str) -> bool:
    """Czy zmiana URL to inny origin (schemat, host albo port)."""
    left = _url_origin(current)
    right = _url_origin(newurl)
    if left is None or right is None:
        return True
    return left != right


def _strip_authorization(req: urllib.request.Request) -> None:
    """Usuwa nagłówek Authorization (bez logowania wartości)."""
    for key in list(req.headers):
        if key.lower() == "authorization":
            req.remove_header(key)
    for key in list(req.unredirected_hdrs):
        if key.lower() == "authorization":
            del req.unredirected_hdrs[key]


def _url_for_error(url: str) -> str:
    """URL do komunikatu błędu — bez userinfo (login/hasło)."""
    parts = urlsplit(url)
    if not (parts.username or parts.password):
        return url
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port_num = parts.port
    except ValueError:
        port = ""
    else:
        port = f":{port_num}" if port_num is not None else ""
    return urlunsplit((parts.scheme, f"{host}{port}", parts.path, parts.query, parts.fragment))


def validate_url(
    url: str,
    *,
    allowed_hosts: AllowedHosts = None,
    allow_lan: bool = False,
    restrict_ports: bool = True,
) -> str:
    """Waliduje URL wg polityki bezpieczeństwa; zwraca host albo rzuca wyjątek.

    Sprawdza (w tej kolejności): schemat, brak userinfo, obecność hosta, port,
    opcjonalny pin ``allowed_hosts`` oraz — po rozwiązaniu DNS — że adresy IP
    nie łamią polityki SSRF.

    Przy ``allow_lan=False`` (domyślnie, metadane) wymagane jest wyłącznie
    ``https`` na publiczny host. Przy ``allow_lan=True`` (lokalne AI) dozwolone
    są też ``http``/``https`` do loopback i RFC1918/ULA; link-local, unspecified
    i multicast pozostają zabronione.

    Args:
        url: pełny adres do sprawdzenia.
        allowed_hosts: gdy podane, host musi należeć do tego zbioru (pin per provider).
        allow_lan: zezwól na lokalny HTTP/HTTPS (AI), bez otwierania metadanych.
        restrict_ports: gdy True, tylko port 443 / domyślny https.

    Returns:
        Host (lowercase) — do dalszego logowania/pinowania.

    Raises:
        UnsafeUrlError: przy dowolnym naruszeniu polityki.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    shown = _url_for_error(url)
    if scheme not in {"https", "http"}:
        raise UnsafeUrlError(f"Niedozwolony schemat {parts.scheme!r} (wymagane https): {shown!r}")
    if scheme == "http" and not allow_lan:
        raise UnsafeUrlError(f"Niedozwolony schemat {parts.scheme!r} (wymagane https): {shown!r}")
    if parts.username or parts.password:
        raise UnsafeUrlError("URL zawiera userinfo (login/hasło) — odrzucone.")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError(f"URL bez hosta: {shown!r}")
    host = host.lower()
    try:
        port = parts.port
    except ValueError as exc:  # niepoprawny port w URL
        raise UnsafeUrlError(f"Niepoprawny port w URL {shown!r}: {exc}") from exc
    if restrict_ports and port not in _ALLOWED_PORTS:
        raise UnsafeUrlError(f"Niedozwolony port {port} w URL: {shown!r}")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise UnsafeUrlError(f"Host {host!r} spoza dozwolonej listy providera: {shown!r}")
    try:
        addresses = _host_addresses(host)
    except OSError as exc:
        raise UnsafeUrlError(f"Nie udało się rozwiązać hosta {host!r}: {exc}") from exc
    if not addresses:
        raise UnsafeUrlError(f"Host {host!r} nie ma adresów IP: {shown!r}")
    if allow_lan and all(_is_lan_allowed_ip(address) for address in addresses):
        return host
    if scheme != "https":
        raise UnsafeUrlError(f"Niedozwolony endpoint HTTP do hosta poza LAN: {shown!r}")
    for address in addresses:
        if _is_forbidden_ip(address):
            raise UnsafeUrlError(f"Host {host!r} → niedozwolony adres {address} (SSRF): {shown!r}")
    return host


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler walidujący KAŻDY hop przez :func:`validate_url` przed skokiem."""

    max_redirections = MAX_REDIRECTS

    def __init__(
        self,
        allowed_hosts: AllowedHosts = None,
        *,
        allow_lan: bool = False,
        restrict_ports: bool = True,
        origin_url: str | None = None,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        # Polityka LAN jest zamrażana na originie — nie resetujemy jej na każdym hopie.
        if origin_url is not None:
            self._allow_lan = allow_lan and _origin_allows_lan(origin_url)
        else:
            self._allow_lan = allow_lan
        self._restrict_ports = restrict_ports

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
            validate_url(
                newurl,
                allowed_hosts=self._allowed_hosts,
                allow_lan=self._allow_lan,
                restrict_ports=self._restrict_ports,
            )
        except UnsafeUrlError as exc:
            raise urllib.error.HTTPError(
                _url_for_error(newurl), code, f"Odrzucony redirect: {exc}", headers, fp
            ) from exc
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None and _is_cross_origin(req.full_url, newurl):
            _strip_authorization(new_req)
        return new_req


def _build_safe_opener(
    allowed_hosts: AllowedHosts,
    *,
    allow_lan: bool = False,
    restrict_ports: bool = True,
    origin_url: str | None = None,
) -> urllib.request.OpenerDirector:
    """Buduje opener z bezpiecznym redirect handlerem (bez domyślnego, który nie waliduje)."""
    return urllib.request.build_opener(
        _SafeRedirectHandler(
            allowed_hosts,
            allow_lan=allow_lan,
            restrict_ports=restrict_ports,
            origin_url=origin_url,
        )
    )


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
