"""Testy klienta AI (:mod:`epubforge.bookmeta.ai`) — wyłącznie mock, zero sieci."""

from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from epubforge.bookmeta import _http, ai
from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy()


@pytest.fixture(autouse=True)
def _stub_dns_for_hostnames(monkeypatch: pytest.MonkeyPatch) -> None:
    """Literały IP bez zmian; localhost → loopback; reszta hostów → publiczny IP."""

    def resolve(host: str) -> list[str]:
        lowered = host.lower()
        if lowered in {"localhost", "localhost.localdomain"}:
            return ["127.0.0.1"]
        return ["93.184.216.34"]

    monkeypatch.setattr(_http, "_resolve_addresses", resolve)


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int | None = None) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _chat_opener(content: str) -> Any:
    """Atrapa urlopen zwracająca odpowiedź chat/completions z podaną treścią."""
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(body)

    return opener


def _raising_opener(exc: Exception) -> Any:
    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        raise exc

    return opener


# ── Presety i konfiguracja ────────────────────────────────────────────────────────


def test_default_preset_is_ollama() -> None:
    """Domyślny preset to lokalna Ollama (bez klucza)."""
    config = ai.AIConfig()
    assert config.preset == "ollama"
    assert config.base_url == "http://localhost:11434/v1"
    assert config.api_key_env == ""


def test_from_preset_unknown_falls_back() -> None:
    """Nieznany preset → domyślny Ollama."""
    assert ai.AIConfig.from_preset("nieistniejący").preset == "ollama"


def test_all_cloud_presets_are_https() -> None:
    """Wszystkie presety chmurowe używają https (tylko ollama to http loopback)."""
    for name, preset in ai.PRESETS.items():
        if name == "ollama":
            assert preset.base_url.startswith("http://")
        else:
            assert preset.base_url.startswith("https://")


# ── Walidacja endpointu ───────────────────────────────────────────────────────────


def test_http_public_host_rejected(taxonomy: Taxonomy) -> None:
    """http do hosta publicznego → AIError (nawet zanim poleci zapytanie)."""
    config = ai.AIConfig(preset="x", base_url="http://api.example.com/v1", model="m")
    with pytest.raises(ai.AIError):
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]/v1",
        "http://192.168.0.10:11434/v1",
        "http://10.0.0.5:8000/v1",
        "http://172.16.1.2:1234/v1",
        "https://api.example.com/v1",
    ],
)
def test_allowed_endpoints(taxonomy: Taxonomy, base_url: str) -> None:
    """Loopback/RFC1918 po http oraz publiczny https są dozwolone (bez AIError)."""
    config = ai.AIConfig(preset="x", base_url=base_url, model="m")
    # poprawny (pusty) JSON -> brak wyjątku, pusta sugestia
    result = ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))
    assert result.is_empty()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/",
        "http://[fe80::1]/v1",
        "https://[fe80::1]/v1",
        "https://user:pass@example.com/v1",
        "https://user@example.com/v1",
        "http://0.0.0.0/v1",
        "https://0.0.0.0/v1",
        "http://8.8.8.8/v1",
        "http://[::]/v1",
    ],
)
def test_forbidden_ai_endpoints_rejected(taxonomy: Taxonomy, base_url: str) -> None:
    """Link-local, userinfo, unspecified i publiczne http są odrzucane."""
    config = ai.AIConfig(preset="x", base_url=base_url, model="m")
    with pytest.raises(ai.AIError):
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))


def test_userinfo_error_does_not_echo_credentials(taxonomy: Taxonomy) -> None:
    """Komunikat AIError nie powtarza loginu/hasła z URL."""
    config = ai.AIConfig(preset="x", base_url="https://user:pass@example.com/v1", model="m")
    with pytest.raises(ai.AIError) as exc_info:
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))
    message = str(exc_info.value)
    assert "user:pass" not in message
    assert "pass@" not in message


def test_out_of_range_port_raises_aierror(taxonomy: Taxonomy) -> None:
    """Port spoza zakresu kończy się AIError, nie surowym ValueError."""
    config = ai.AIConfig(preset="x", base_url="https://example.com:99999/v1", model="m")
    with pytest.raises(ai.AIError, match="port"):
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))


def test_userinfo_and_bad_port_does_not_echo_credentials(taxonomy: Taxonomy) -> None:
    """Userinfo + zły port: AIError bez loginu/hasła."""
    config = ai.AIConfig(preset="x", base_url="https://user:pass@example.com:99999/v1", model="m")
    with pytest.raises(ai.AIError) as exc_info:
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))
    message = str(exc_info.value)
    assert "user:pass" not in message
    assert "pass@" not in message


def test_hostname_resolving_to_link_local_is_rejected(
    monkeypatch: pytest.MonkeyPatch, taxonomy: Taxonomy
) -> None:
    """Hostname wskazujący na 169.254.169.254 jest odrzucany (mock DNS, bez sieci)."""
    monkeypatch.setattr(_http, "_resolve_addresses", lambda _host: ["169.254.169.254"])
    config = ai.AIConfig(preset="x", base_url="https://ai.example/v1", model="m")
    with pytest.raises(ai.AIError):
        ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))


def test_public_ai_opener_disables_lan_redirects(
    monkeypatch: pytest.MonkeyPatch, taxonomy: Taxonomy
) -> None:
    """Publiczny HTTPS nie followuje 302 na RFC1918 (Authorization nie idzie do LAN)."""
    seen: dict[str, object] = {}

    class _DummyOpener:
        def open(self, request: Any, timeout: float | None = None) -> Any:
            raise urllib.error.URLError("no-network")

    def fake_build(
        allowed_hosts: object,
        *,
        allow_lan: bool = False,
        restrict_ports: bool = True,
        origin_url: str | None = None,
    ) -> _DummyOpener:
        seen["allow_lan"] = allow_lan
        seen["origin_url"] = origin_url
        return _DummyOpener()

    monkeypatch.setattr(ai, "_build_safe_opener", fake_build)
    config = ai.AIConfig(preset="x", base_url="https://api.example.com/v1", model="m")
    with pytest.raises(ai.AIError):
        ai.suggest_tags("o", "t", taxonomy, config)
    assert seen["allow_lan"] is False
    assert seen["origin_url"] == "https://api.example.com/v1/chat/completions"


def test_lan_ai_opener_keeps_lan_redirects(
    monkeypatch: pytest.MonkeyPatch, taxonomy: Taxonomy
) -> None:
    """Lokalny endpoint AI nadal pozwala na hop-y RFC1918/loopback."""
    seen: dict[str, object] = {}

    class _DummyOpener:
        def open(self, request: Any, timeout: float | None = None) -> Any:
            raise urllib.error.URLError("no-network")

    def fake_build(
        allowed_hosts: object,
        *,
        allow_lan: bool = False,
        restrict_ports: bool = True,
        origin_url: str | None = None,
    ) -> _DummyOpener:
        seen["allow_lan"] = allow_lan
        seen["origin_url"] = origin_url
        return _DummyOpener()

    monkeypatch.setattr(ai, "_build_safe_opener", fake_build)
    config = ai.AIConfig(preset="x", base_url="http://192.168.1.10:11434/v1", model="m")
    with pytest.raises(ai.AIError):
        ai.suggest_tags("o", "t", taxonomy, config)
    assert seen["allow_lan"] is True
    assert seen["origin_url"] == "http://192.168.1.10:11434/v1/chat/completions"


def test_hostname_resolving_to_public_ip_allows_https(
    monkeypatch: pytest.MonkeyPatch, taxonomy: Taxonomy
) -> None:
    """Publiczny HTTPS po mockowanym DNS przechodzi walidację."""
    monkeypatch.setattr(_http, "_resolve_addresses", lambda _host: ["93.184.216.34"])
    config = ai.AIConfig(preset="x", base_url="https://ai.example/v1", model="m")
    result = ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener("{}"))
    assert result.is_empty()


# ── Parsowanie i walidacja odpowiedzi ─────────────────────────────────────────────


def test_valid_response_filtered_against_taxonomy(taxonomy: Taxonomy) -> None:
    """Tagi spoza listy zamkniętej są odrzucane; kanoniczne i byty zostają."""
    content = json.dumps(
        {
            "gatunek": ["science fiction", "coś wymyślonego"],
            "epoka": [],
            "miejsce": ["kosmos"],
            "tematy": ["space opera"],
            "postacie": ["Geralt z Rivii"],
            "organizacje": ["Loża Czarodziejek"],
        }
    )
    config = ai.AIConfig()
    suggestion = ai.suggest_tags("opis", "toc", taxonomy, config, urlopen=_chat_opener(content))
    assert suggestion.gatunek == ["science fiction"]  # wymyślony tag odrzucony
    assert suggestion.miejsce == ["kosmos"]
    assert suggestion.tematy == ["space opera"]
    assert suggestion.postacie == ["Geralt z Rivii"]
    assert suggestion.organizacje == ["Loża Czarodziejek"]


def test_response_with_code_fence(taxonomy: Taxonomy) -> None:
    """JSON owinięty w ```json ...``` jest wyłuskiwany."""
    content = '```json\n{"gatunek": ["fantasy"], "tematy": ["magia"]}\n```'
    suggestion = ai.suggest_tags("o", "t", taxonomy, ai.AIConfig(), urlopen=_chat_opener(content))
    assert suggestion.gatunek == ["fantasy"]
    assert suggestion.tematy == ["magia"]


def test_garbage_after_retry_returns_empty(taxonomy: Taxonomy) -> None:
    """Śmieci mimo ponowienia → pusta sugestia (bez wyjątku)."""
    suggestion = ai.suggest_tags(
        "o", "t", taxonomy, ai.AIConfig(), urlopen=_chat_opener("zupełnie nie JSON")
    )
    assert suggestion.is_empty()


def _padded_chat_body(size: int) -> bytes:
    """Buduje JSON chat/completions o dokładnym rozmiarze ``size`` bajtów."""
    prefix = b'{"choices":[{"message":{"content":"'
    suffix = b'"}}]}'
    pad = size - len(prefix) - len(suffix)
    assert pad >= 0
    return prefix + (b"a" * pad) + suffix


def test_response_at_max_bytes_is_accepted(taxonomy: Taxonomy) -> None:
    """Odpowiedź o rozmiarze dokładnie MAX_BYTES jest przyjmowana."""
    body = _padded_chat_body(ai.MAX_BYTES)
    assert len(body) == ai.MAX_BYTES

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(body)

    suggestion = ai.suggest_tags("o", "t", taxonomy, ai.AIConfig(), urlopen=opener)
    assert suggestion.is_empty()


def test_oversized_ai_response_is_rejected(taxonomy: Taxonomy) -> None:
    """Odpowiedź MAX_BYTES+1 jest odrzucana zanim ucięty JSON trafi do parsera."""
    body = _padded_chat_body(ai.MAX_BYTES + 1)
    assert len(body) == ai.MAX_BYTES + 1

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(body)

    with pytest.raises(ai.AIError, match="przekracza limit"):
        ai.suggest_tags("o", "t", taxonomy, ai.AIConfig(), urlopen=opener)


def test_connection_error_raises_aierror(taxonomy: Taxonomy) -> None:
    """Błąd połączenia → AIError (GUI pokaże komunikat)."""
    import urllib.error

    config = ai.AIConfig()
    with pytest.raises(ai.AIError):
        ai.suggest_tags(
            "o", "t", taxonomy, config, urlopen=_raising_opener(urllib.error.URLError("brak"))
        )


def test_api_key_from_env(monkeypatch: pytest.MonkeyPatch, taxonomy: Taxonomy) -> None:
    """Klucz API brany jest wyłącznie ze zmiennej środowiskowej wskazanej w configu."""
    captured: dict[str, Any] = {}

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        captured["auth"] = request.headers.get("Authorization")
        return _FakeResponse(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())

    monkeypatch.setenv("MY_KEY", "sekret123")
    config = ai.AIConfig(
        preset="openai", base_url="https://api.openai.com/v1", model="m", api_key_env="MY_KEY"
    )
    ai.suggest_tags("o", "t", taxonomy, config, urlopen=opener)
    assert captured["auth"] == "Bearer sekret123"


# ── Prywatność: ujawnienie i zgoda na chmurę (F-19) ──────────────────────────────


@pytest.mark.parametrize(
    ("base_url", "cloud"),
    [
        ("http://localhost:11434/v1", False),
        ("http://127.0.0.1:11434/v1", False),
        ("http://192.168.1.10:11434/v1", False),
        ("https://api.openai.com/v1", True),
        ("https://api.deepseek.com/v1", True),
    ],
)
def test_is_cloud_endpoint(base_url: str, cloud: bool) -> None:
    """Loopback/LAN to NIE chmura; hosty publiczne to chmura."""
    assert ai.is_cloud_endpoint(base_url) is cloud


def test_describe_request_lists_only_sent_fields() -> None:
    """Ujawnienie zawiera dokładnie pola, które przy danych wejściach pójdą do modelu."""
    config = ai.AIConfig(preset="openai", base_url="https://api.openai.com/v1", model="gpt")
    # Z opisem: opis + taksonomia; próbka NIE (bo jest opis).
    with_desc = ai.describe_request(config, description="opis", toc="", sample_text="tekst")
    assert with_desc.is_cloud is True
    assert with_desc.host == "api.openai.com"
    assert with_desc.model == "gpt"
    assert ai.FIELD_DESCRIPTION in with_desc.fields
    assert ai.FIELD_CONTENT_SAMPLE not in with_desc.fields
    # Bez opisu, z próbką: próbka + taksonomia (bez opisu).
    with_sample = ai.describe_request(config, description="", toc="", sample_text="tekst")
    assert ai.FIELD_CONTENT_SAMPLE in with_sample.fields
    assert ai.FIELD_DESCRIPTION not in with_sample.fields
    # Taksonomia zawsze.
    assert ai.FIELD_TAXONOMY in with_desc.fields and ai.FIELD_TAXONOMY in with_sample.fields


def test_cloud_consent_roundtrip() -> None:
    """Zgoda jest per (host, model): zapis i odczyt, zmiana modelu unieważnia."""
    config: dict[str, object] = {}
    assert ai.cloud_consent_granted(config, "api.openai.com", "gpt") is False
    ai.grant_cloud_consent(config, "api.openai.com", "gpt")
    assert ai.cloud_consent_granted(config, "api.openai.com", "gpt") is True
    # Inny model na tym samym hoście → brak zgody (ponowne pytanie).
    assert ai.cloud_consent_granted(config, "api.openai.com", "gpt-inny") is False
    # Inny host → brak zgody.
    assert ai.cloud_consent_granted(config, "api.deepseek.com", "gpt") is False


def test_content_sample_setting_default_and_toggle() -> None:
    """Domyślnie wolno wysyłać próbkę; ustawienie da się wyłączyć i odczytać."""
    config: dict[str, object] = {}
    assert ai.content_sample_enabled(config) is True  # domyślnie tak
    ai.set_content_sample_enabled(config, False)
    assert ai.content_sample_enabled(config) is False
    ai.set_content_sample_enabled(config, True)
    assert ai.content_sample_enabled(config) is True
