"""Testy klienta AI (:mod:`epubforge.bookmeta.ai`) — wyłącznie mock, zero sieci."""

from __future__ import annotations

import json
from typing import Any

import pytest

from epubforge.bookmeta import ai
from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy()


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
        "http://192.168.0.10:11434/v1",
        "http://10.0.0.5:8000/v1",
        "https://api.example.com/v1",
    ],
)
def test_allowed_endpoints(taxonomy: Taxonomy, base_url: str) -> None:
    """Loopback/RFC1918 po http oraz dowolny https są dozwolone (bez AIError)."""
    config = ai.AIConfig(preset="x", base_url=base_url, model="m")
    # poprawny (pusty) JSON -> brak wyjątku, pusta sugestia
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
