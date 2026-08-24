"""Klient AI zgodny z OpenAI Chat Completions — klasyfikacja tagów (opt-in).

Jeden protokół (OpenAI ``/chat/completions``, ``temperature = 0``) obsługuje wszystkie
backendy — lokalną **Ollamę** (domyślnie) i chmury przez ich warstwy zgodności.
Klasyfikacja gatunku/epoki/miejsca/tematów odbywa się **wyłącznie z listy zamkniętej**
taksonomii (walidacja odpowiedzi, 1 ponowienie), a postacie/organizacje są otwarte.

**Bezpieczeństwo (D2 + wyjątek dla LAN):** hosty publiczne wyłącznie ``https``;
``http`` dozwolone tylko dla loopback i RFC1918/ULA (Ollama/LiteLLM w LAN).
Link-local, unspecified, multicast i URL z userinfo są zawsze odrzucane.
Przekierowania waliduje ten sam mechanizm co :mod:`._http`. Klucz API pochodzi
**wyłącznie ze zmiennej środowiskowej** — w konfiguracji trzymamy jedynie jej
nazwę, nigdy sam klucz. Limit rozmiaru odpowiedzi jak w :mod:`._http`
(``MAX_BYTES + 1``, bez cichego ucięcia).

Presety ``base_url`` (zweryfikowane na dzień implementacji — warstwy zgodności z
OpenAI API): patrz :data:`PRESETS`. Wszystkie są edytowalne w konfiguracji.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from epubforge.bookmeta._http import (
    MAX_BYTES,
    UnsafeUrlError,
    _build_safe_opener,
    _host_addresses,
    _is_lan_allowed_ip,
    validate_url,
)
from epubforge.bookmeta.taxonomy import CATEGORIES, Taxonomy

logger = logging.getLogger(__name__)

# Maksymalna liczba otwartych bytów (postacie/organizacje) przyjmowanych od modelu.
_MAX_ENTITIES = 10
# Domyślny timeout zapytania do modelu (sekundy) — lokalne modele bywają wolne.
DEFAULT_TIMEOUT = 60.0

# Typ atrapy urlopen wstrzykiwanej w testach.
UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class Preset:
    """Preset backendu AI: bazowy URL, domyślny model i nazwa zmiennej z kluczem."""

    base_url: str
    model: str
    api_key_env: str


# Presety zgodne z OpenAI Chat Completions (base_url; klucz ze zmiennej środowiskowej).
# Zweryfikowane warstwy zgodności na dzień implementacji:
#   ollama     — lokalny serwer, bez klucza;
#   openai     — natywne API;
#   anthropic  — warstwa zgodności OpenAI (/v1/chat/completions);
#   gemini     — Google „OpenAI compatibility" (/v1beta/openai);
#   deepseek   — natywnie zgodne z OpenAI;
#   glm        — Zhipu AI (bigmodel) /api/paas/v4.
PRESETS: dict[str, Preset] = {
    "ollama": Preset("http://localhost:11434/v1", "llama3.1", ""),
    "openai": Preset("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "anthropic": Preset(
        "https://api.anthropic.com/v1", "claude-3-5-haiku-latest", "ANTHROPIC_API_KEY"
    ),
    "gemini": Preset(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash",
        "GEMINI_API_KEY",
    ),
    "deepseek": Preset("https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "glm": Preset("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "GLM_API_KEY"),
}
# Preset domyślny — lokalna Ollama (prywatność, brak kosztów, brak klucza).
DEFAULT_PRESET = "ollama"


class AIError(Exception):
    """Problem z endpointem AI (niedozwolony schemat, brak połączenia, zła odpowiedź).

    Podnoszony, gdy AI jest niedostępne — GUI pokazuje czytelny komunikat, a kaskada
    tagowania działa dalej bez AI (na samym mapowaniu taksonomii).
    """


@dataclass
class AIConfig:
    """Konfiguracja klienta AI (trzymana w ``config.json`` — bez klucza API).

    Attributes:
        preset: nazwa presetu (do UI); ``base_url``/``model`` mogą być nadpisane.
        base_url: bazowy URL API zgodnego z OpenAI.
        model: nazwa modelu.
        api_key_env: **nazwa** zmiennej środowiskowej z kluczem (nie sam klucz).
        timeout: timeout zapytania w sekundach.
    """

    preset: str = DEFAULT_PRESET
    base_url: str = PRESETS[DEFAULT_PRESET].base_url
    model: str = PRESETS[DEFAULT_PRESET].model
    api_key_env: str = PRESETS[DEFAULT_PRESET].api_key_env
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_preset(cls, name: str) -> AIConfig:
        """Buduje konfigurację z presetu (nieznany preset → domyślny Ollama)."""
        preset = PRESETS.get(name, PRESETS[DEFAULT_PRESET])
        resolved = name if name in PRESETS else DEFAULT_PRESET
        return cls(
            preset=resolved,
            base_url=preset.base_url,
            model=preset.model,
            api_key_env=preset.api_key_env,
        )


@dataclass
class TagSuggestion:
    """Propozycje tagów od modelu: kategorie zamknięte + otwarte byty.

    Kategorie ``gatunek``/``epoka``/``miejsce``/``tematy`` zawierają wyłącznie
    kanoniczne tagi z taksonomii (po walidacji). ``postacie``/``organizacje`` to
    otwarta ekstrakcja (np. „Piłsudski", „Armia Czerwona").
    """

    gatunek: list[str] = field(default_factory=list)
    epoka: list[str] = field(default_factory=list)
    miejsce: list[str] = field(default_factory=list)
    tematy: list[str] = field(default_factory=list)
    postacie: list[str] = field(default_factory=list)
    organizacje: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Czy model nie zaproponował żadnego tagu ani bytu."""
        return not any(
            (self.gatunek, self.epoka, self.miejsce, self.tematy, self.postacie, self.organizacje)
        )


def suggest_tags(
    description: str,
    toc: str,
    taxonomy: Taxonomy,
    config: AIConfig,
    *,
    sample_text: str = "",
    urlopen: UrlOpen | None = None,
) -> TagSuggestion:
    """Prosi model o tagi na podstawie opisu/TOC (i opcjonalnie próbki treści).

    Args:
        description: opis/streszczenie książki (może być pusty).
        toc: spis treści (tytuły rozdziałów), może być pusty.
        taxonomy: taksonomia (listy zamknięte trafiają do promptu, walidacja odpowiedzi).
        config: konfiguracja backendu AI.
        sample_text: próbka treści (używana, gdy brak opisu).
        urlopen: atrapa ``urlopen`` do testów (domyślnie prawdziwy klient).

    Returns:
        :class:`TagSuggestion` (puste pola, gdy model zwrócił śmieci mimo ponowienia).

    Raises:
        AIError: gdy endpoint jest niedozwolony (http do hosta publicznego) lub
            nieosiągalny — kaskada łapie to i pomija AI.
    """
    prompt = _build_prompt(description, toc, sample_text, taxonomy)
    last_content = ""
    for _ in range(2):  # jedno ponowienie przy niewalidowalnej odpowiedzi
        content = _chat_completion(config, prompt, urlopen=urlopen)
        parsed = _parse_suggestion(content, taxonomy)
        if parsed is not None:
            return parsed
        last_content = content
    logger.debug("AI zwróciło niewalidowalny JSON po ponowieniu: %r", last_content[:200])
    return TagSuggestion()


# ── Zapytanie do modelu ─────────────────────────────────────────────────────────


def _chat_completion(config: AIConfig, prompt: str, *, urlopen: UrlOpen | None) -> str:
    """Wysyła zapytanie chat/completions i zwraca treść odpowiedzi modelu.

    Raises:
        AIError: niedozwolony endpoint, błąd połączenia lub niepoprawna odpowiedź HTTP.
    """
    url = config.base_url.rstrip("/") + "/chat/completions"
    _validate_endpoint(config.base_url)
    _validate_endpoint(url)
    payload = {
        "model": config.model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json"}
    api_key = _api_key(config)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        if urlopen is not None:
            response_cm = urlopen(request, timeout=config.timeout)
        else:
            opener = _build_safe_opener(
                None,
                allow_lan=_use_lan_redirects(config.base_url),
                restrict_ports=False,
                origin_url=url,
            )
            response_cm = opener.open(request, timeout=config.timeout)
        with response_cm as response:
            raw = bytes(response.read(MAX_BYTES + 1))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AIError(f"Nie udało się połączyć z endpointem AI ({config.base_url}): {exc}") from exc
    if len(raw) > MAX_BYTES:
        raise AIError(f"Odpowiedź endpointu AI przekracza limit {MAX_BYTES} B.")
    return _extract_content(raw)


def _extract_content(raw: bytes) -> str:
    """Wyłuskuje ``choices[0].message.content`` z odpowiedzi API (albo ``AIError``)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise AIError(f"Niepoprawna odpowiedź endpointu AI: {exc}") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Odpowiedź AI bez pola choices[0].message.content") from exc
    if not isinstance(content, str):
        raise AIError("Treść odpowiedzi AI nie jest tekstem")
    return content


def _validate_endpoint(base_url: str) -> None:
    """Waliduje endpoint AI tą samą polityką co :func:`validate_url` (z LAN)."""
    try:
        validate_url(base_url, allow_lan=True, restrict_ports=False)
    except UnsafeUrlError as exc:
        raise AIError(f"Niedozwolony endpoint AI: {exc}") from exc


def _use_lan_redirects(base_url: str) -> bool:
    """Czy hop-y przekierowań mogą iść na LAN (tylko gdy sam endpoint jest LAN)."""
    host = urllib.parse.urlsplit(base_url).hostname
    if not host:
        return False
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = _host_addresses(host)
    except OSError:
        return False
    return bool(addresses) and all(_is_lan_allowed_ip(address) for address in addresses)


def _is_local_host(host: str | None) -> bool:
    """Czy host to loopback albo RFC1918/ULA (nie link-local)."""
    if not host:
        return False
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    return _is_lan_allowed_ip(host)


def _api_key(config: AIConfig) -> str:
    """Czyta klucz API ze zmiennej środowiskowej wskazanej w konfiguracji (lub pusty)."""
    if not config.api_key_env:
        return ""
    return os.environ.get(config.api_key_env, "")


# ── Prywatność: ujawnienie żądania i zgoda na chmurę (F-19) ───────────────────────

# Identyfikatory pól, które MOGĄ trafić do modelu — UI tłumaczy je na etykiety.
FIELD_DESCRIPTION = "description"
FIELD_TOC = "toc"
FIELD_CONTENT_SAMPLE = "content_sample"
FIELD_TAXONOMY = "taxonomy"

# Klucze konfiguracji: zapisana zgoda per host oraz zgoda na wysyłkę próbki treści.
_CONSENT_SECTION = "ai_cloud_consent"
_CONTENT_SAMPLE_KEY = "ai_send_content_sample"


@dataclass(frozen=True)
class AIDisclosure:
    """Jawne ujawnienie żądania AI do ekranu świadomej zgody.

    Attributes:
        host: host docelowy (z ``base_url``).
        scheme: schemat (``https``/``http``).
        model: nazwa modelu.
        is_cloud: czy host jest publiczny (chmura) — czyli NIE loopback/LAN.
        fields: identyfikatory pól, które przy DANYCH wejściach faktycznie pójdą.
    """

    host: str
    scheme: str
    model: str
    is_cloud: bool
    fields: tuple[str, ...]


def is_cloud_endpoint(base_url: str) -> bool:
    """Czy endpoint to host PUBLICZNY (chmura) — a nie loopback/adres prywatny (LAN)."""
    return not _is_local_host(urllib.parse.urlparse(base_url).hostname)


def describe_request(
    config: AIConfig, *, description: str, toc: str, sample_text: str
) -> AIDisclosure:
    """Zwraca dokładny opis żądania: host, model i pola, które FAKTYCZNIE pójdą.

    Lista pól odzwierciedla logikę :func:`_build_prompt` — pokazujemy dokładnie to,
    co przy danych wejściach trafi do modelu (nie „potencjalnie"). Zawsze wysyłamy
    listy taksonomii; opis/spis treści/próbkę tylko, gdy realnie są dołączane.
    """
    parsed = urllib.parse.urlparse(config.base_url)
    fields = [FIELD_TAXONOMY]
    if description:
        fields.insert(0, FIELD_DESCRIPTION)
    if toc:
        fields.append(FIELD_TOC)
    if sample_text and not description:
        fields.append(FIELD_CONTENT_SAMPLE)
    return AIDisclosure(
        host=parsed.hostname or config.base_url,
        scheme=parsed.scheme.lower(),
        model=config.model,
        is_cloud=is_cloud_endpoint(config.base_url),
        fields=tuple(fields),
    )


def cloud_consent_granted(config: Mapping[str, Any], host: str, model: str) -> bool:
    """Czy zapisano świadomą zgodę na wysyłkę do danej pary ``(host, model)``.

    Zgoda jest per ``(host, model)`` — zmiana modelu wymaga ponownej zgody (model
    jest jawnie ujawniany), więc użytkownik nie wysyła nieświadomie do innego celu.
    """
    section = config.get(_CONSENT_SECTION)
    return isinstance(section, dict) and section.get(host) == model


def grant_cloud_consent(config: MutableMapping[str, Any], host: str, model: str) -> None:
    """Zapisuje zgodę na ``(host, model)`` w configu (utrwalenie należy do wołającego)."""
    raw = config.get(_CONSENT_SECTION)
    section = dict(raw) if isinstance(raw, dict) else {}
    section[host] = model
    config[_CONSENT_SECTION] = section


def content_sample_enabled(config: Mapping[str, Any]) -> bool:
    """Czy wolno wysyłać próbkę treści książki do modelu (domyślnie: tak)."""
    return bool(config.get(_CONTENT_SAMPLE_KEY, True))


def set_content_sample_enabled(config: MutableMapping[str, Any], enabled: bool) -> None:
    """Ustawia zgodę na wysyłkę próbki treści (utrwalenie należy do wołającego)."""
    config[_CONTENT_SAMPLE_KEY] = bool(enabled)


# ── Budowa promptu i parsowanie odpowiedzi ────────────────────────────────────────


def _build_prompt(description: str, toc: str, sample_text: str, taxonomy: Taxonomy) -> str:
    """Składa polski prompt klasyfikacyjny z listami zamkniętymi z taksonomii."""
    closed = "\n".join(
        f"- {category}: {', '.join(taxonomy.canonical_tags(category))}" for category in CATEGORIES
    )
    context_parts = []
    if description:
        context_parts.append(f"OPIS:\n{description}")
    if toc:
        context_parts.append(f"SPIS TREŚCI:\n{toc}")
    if sample_text and not description:
        context_parts.append(f"PRÓBKA TREŚCI:\n{sample_text}")
    context = "\n\n".join(context_parts) if context_parts else "(brak dodatkowych informacji)"
    return (
        "Jesteś bibliotekarzem klasyfikującym książki. Na podstawie poniższych informacji "
        "zaproponuj tagi PO POLSKU.\n\n"
        "Dla kategorii gatunek, epoka, miejsce, tematy wybieraj WYŁĄCZNIE z podanych list "
        "(nie wymyślaj własnych, nie tłumacz). Dla postaci i organizacji wypisz nazwy własne "
        "występujące w treści (np. postaci historyczne, armie, instytucje).\n\n"
        f"DOZWOLONE WARTOŚCI:\n{closed}\n\n"
        f"{context}\n\n"
        "Odpowiedz wyłącznie obiektem JSON o kluczach: gatunek, epoka, miejsce, tematy, "
        "postacie, organizacje — każdy z listą stringów (może być pusta). Bez komentarzy."
    )


def _parse_suggestion(content: str, taxonomy: Taxonomy) -> TagSuggestion | None:
    """Parsuje JSON z odpowiedzi i waliduje kategorie zamknięte; ``None`` gdy brak JSON."""
    obj = _extract_json_object(content)
    if obj is None:
        return None
    return TagSuggestion(
        gatunek=_validated(obj.get("gatunek"), taxonomy, "gatunek"),
        epoka=_validated(obj.get("epoka"), taxonomy, "epoka"),
        miejsce=_validated(obj.get("miejsce"), taxonomy, "miejsce"),
        tematy=_validated(obj.get("tematy"), taxonomy, "tematy"),
        postacie=_open_entities(obj.get("postacie")),
        organizacje=_open_entities(obj.get("organizacje")),
    )


def _extract_json_object(content: str) -> dict[str, Any] | None:
    """Wyłuskuje pierwszy obiekt JSON z tekstu (toleruje ```json fences``` i otoczkę)."""
    try:
        direct = json.loads(content)
        if isinstance(direct, dict):
            return direct
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match is None:
        return None
    try:
        obj = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _validated(value: Any, taxonomy: Taxonomy, category: str) -> list[str]:
    """Zostawia tylko wartości należące do zamkniętej listy kategorii (kanonizowane)."""
    result: list[str] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, str):
            continue
        canonical = taxonomy.resolve_canonical(item, category)
        if canonical is not None and canonical not in result:
            result.append(canonical)
    return result


def _open_entities(value: Any) -> list[str]:
    """Czyści otwartą listę bytów (postacie/organizacje): trim, dedup, limit."""
    result: list[str] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, str):
            continue
        name = " ".join(item.split())
        if name and name not in result:
            result.append(name)
        if len(result) >= _MAX_ENTITIES:
            break
    return result
