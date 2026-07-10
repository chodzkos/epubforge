"""Testy kaskady tagowania (:mod:`epubforge.bookmeta.tagging`) — mock AI, zero sieci."""

from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from epubforge.bookmeta import ai, tagging
from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy
from epubforge.core import ManifestItem


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


def _opener(content: str) -> Any:
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(body)

    return opener


_AI_JSON = json.dumps(
    {
        "gatunek": ["science fiction"],
        "epoka": [],
        "miejsce": ["kosmos"],
        "tematy": ["space opera"],
        "postacie": ["HAL 9000"],
        "organizacje": [],
    }
)


# ── Kaskada ─────────────────────────────────────────────────────────────────────


def test_stage1_only_when_enough_tags(taxonomy: Taxonomy) -> None:
    """≥3 tagi z taksonomii → AI nie jest uruchamiane (mimo use_ai)."""
    result = tagging.suggest_tags_cascade(
        ["Fantasy", "Komiksy", "Potwory", "Magia"],
        "jest opis",
        "toc",
        taxonomy,
        ai.AIConfig(),
        use_ai=True,
        urlopen=_opener(_AI_JSON),
    )
    assert not result.ai_used
    assert all(p.source == tagging.SOURCE_TAXONOMY for p in result.proposals)


def test_stage2_ai_when_few_tags(taxonomy: Taxonomy) -> None:
    """<3 tagi → AI na opisie+TOC dokłada propozycje (z oznaczeniem źródła AI)."""
    result = tagging.suggest_tags_cascade(
        ["Powieść"], "opis SF", "Rozdział 1", taxonomy, ai.AIConfig(), urlopen=_opener(_AI_JSON)
    )
    assert result.ai_used
    tags = {p.tag: p.source for p in result.proposals}
    assert tags["powieść"] == tagging.SOURCE_TAXONOMY
    assert tags["science fiction"] == tagging.SOURCE_AI
    assert tags["HAL 9000"] == tagging.SOURCE_AI


def test_use_ai_false_skips_ai(taxonomy: Taxonomy) -> None:
    """use_ai=False → wyłącznie taksonomia, żadnych wywołań AI."""

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("AI nie powinno zostać wywołane")

    result = tagging.suggest_tags_cascade(
        ["Powieść"], "", "", taxonomy, ai.AIConfig(), use_ai=False, urlopen=explode
    )
    assert not result.ai_used
    assert [p.tag for p in result.proposals] == ["powieść"]


def test_ai_error_keeps_deterministic(taxonomy: Taxonomy) -> None:
    """Błąd AI → ai_error ustawione, ale propozycje z taksonomii zostają."""
    result = tagging.suggest_tags_cascade(
        ["Powieść"],
        "opis",
        "toc",
        taxonomy,
        ai.AIConfig(),
        urlopen=lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    assert result.ai_error
    assert [p.tag for p in result.proposals] == ["powieść"]


# ── Polityki scalania ────────────────────────────────────────────────────────────


def test_policy_append_default() -> None:
    """append (domyślna) = istniejące + wybrane, bez duplikatów."""
    assert tagging.apply_policy(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_policy_replace() -> None:
    """replace = tylko wybrane."""
    assert tagging.apply_policy(["a", "b"], ["c"], "replace") == ["c"]


def test_policy_keep() -> None:
    """keep = zachowaj istniejące (jeśli są); inaczej użyj wybranych."""
    assert tagging.apply_policy(["a"], ["c"], "keep") == ["a"]
    assert tagging.apply_policy([], ["c"], "keep") == ["c"]


def test_policy_unknown_falls_back_to_append() -> None:
    """Nieznana polityka → zachowanie append."""
    assert tagging.apply_policy(["a"], ["b"], "cokolwiek") == ["a", "b"]


# ── Próbka treści ────────────────────────────────────────────────────────────────


class _FakeEpub:
    def __init__(self, docs: dict[str, bytes]) -> None:
        self._docs = docs
        self.manifest = [
            ManifestItem(id="d1", href="text/a.xhtml", media_type="application/xhtml+xml"),
            ManifestItem(id="d2", href="text/b.xhtml", media_type="application/xhtml+xml"),
        ]
        self.spine = ["d1", "d2"]

    def opf_dir(self) -> str:
        return "OEBPS"

    def read_file(self, path: str) -> bytes:
        return self._docs[path]


def test_extract_content_sample_strips_tags_and_limits() -> None:
    """Próbka treści usuwa znaczniki HTML i respektuje limit słów."""
    docs = {
        "OEBPS/text/a.xhtml": b"<p>Ala ma kota</p>",
        "OEBPS/text/b.xhtml": b"<p>oraz psa i chomika</p>",
    }
    sample = tagging.extract_content_sample(_FakeEpub(docs), max_words=4)  # type: ignore[arg-type]
    assert sample == "Ala ma kota oraz"


def test_extract_content_sample_skips_missing_docs() -> None:
    """Brakujący dokument spine jest pomijany (odczyt defensywny)."""
    sample = tagging.extract_content_sample(
        _FakeEpub({"OEBPS/text/a.xhtml": b"<p>tekst</p>"})  # d2 nieobecny
    )  # type: ignore[arg-type]
    assert sample == "tekst"
