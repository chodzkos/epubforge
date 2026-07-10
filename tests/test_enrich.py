"""Testy hurtowego wzbogacania metadanych (:mod:`epubforge.enrich`).

Sieć jest zawsze zamockowana (wstrzykiwany ``fetcher``), a ``calibredb`` mockowany
przez podmianę ``subprocess.run`` (wzorzec z ``test_converter.py``). Zero realnych
wywołań sieciowych i zewnętrznych narzędzi.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from epubforge.bookmeta import BookRecord
from epubforge.core import Epub, Metadata, get_number_of_pages
from epubforge.enrich import (
    BookOutcome,
    EnrichOptions,
    EnrichSummary,
    collect_epubs,
    enrich_epub,
    enrich_paths,
    format_summary,
    plan_enrichment,
    write_report,
)
from epubforge.enrich import calibre as calibre_mod
from epubforge.enrich.calibre import (
    CalibreError,
    enrich_library,
    list_books,
    preflight,
    set_metadata,
)
from epubforge.enrich.engine import FetchOutcome
from epubforge.enrich.model import ACTION_CHANGED

_RECORD = BookRecord(
    title="Ostatnie życzenie",
    creators=["Sapkowski, Andrzej"],
    publisher="SuperNOWA",
    date="2014",
    description="Opowiadania o wiedźminie.",
    language="pl",
    page_count=330,
    subjects=["Fantasy", "Komiksy"],
    series="Wiedźmin",
    source="bn",
)


def _fetcher(record: BookRecord | None, match: str = "isbn", *, from_cache: bool = False):
    def fetch(metadata: Metadata, epub: object) -> FetchOutcome:
        return FetchOutcome(record, match, record.source if record else "", from_cache)

    return fetch


# ── Plan i polityki ─────────────────────────────────────────────────────────────


def test_plan_fill_keeps_existing() -> None:
    """Polityka fill: istniejące pola nietknięte, puste uzupełnione."""
    current = Metadata(title="Mam tytuł", publisher="")
    plan = plan_enrichment(current, None, _RECORD, EnrichOptions(field_policy="fill"), None)
    actions = {c.field: c.action for c in plan.changes}
    assert actions["title"] != ACTION_CHANGED  # istniejący tytuł nietknięty
    assert actions["publisher"] == ACTION_CHANGED  # puste uzupełnione
    assert plan.metadata.title == "Mam tytuł"
    assert plan.metadata.publisher == "SuperNOWA"


def test_plan_overwrite_replaces() -> None:
    """Polityka overwrite: istniejąca wartość zostaje zastąpiona."""
    current = Metadata(title="Stary tytuł")
    plan = plan_enrichment(current, None, _RECORD, EnrichOptions(field_policy="overwrite"), None)
    actions = {c.field: c.action for c in plan.changes}
    assert actions["title"] == ACTION_CHANGED
    assert plan.metadata.title == "Ostatnie życzenie"


def test_plan_append_creators_union() -> None:
    """append dla list: autorzy scalani bez duplikatów."""
    current = Metadata(creators=["Inny Autor"])
    plan = plan_enrichment(
        current, None, _RECORD, EnrichOptions(fields=("creators",), field_policy="append"), None
    )
    assert plan.metadata.creators == ["Inny Autor", "Sapkowski, Andrzej"]


def test_plan_pages_fill_only_when_absent() -> None:
    """Liczba stron (fill): ustawiana, gdy w OPF jej nie było."""
    plan = plan_enrichment(Metadata(), None, _RECORD, EnrichOptions(fields=("page_count",)), None)
    assert plan.page_count == 330
    plan2 = plan_enrichment(
        Metadata(), 100, _RECORD, EnrichOptions(fields=("page_count",), field_policy="fill"), None
    )
    assert plan2.page_count is None  # już była liczba stron → fill nie zmienia


def test_plan_tags_mapped_to_taxonomy() -> None:
    """--tags mapuje surowe tematy rekordu na kanoniczne tagi taksonomii."""
    from epubforge.bookmeta.taxonomy import load_taxonomy

    plan = plan_enrichment(
        Metadata(), None, _RECORD, EnrichOptions(fields=(), want_tags=True), load_taxonomy()
    )
    assert "fantasy" in plan.metadata.subjects
    assert "komiks" in plan.metadata.subjects


# ── Wzbogacanie plików ─────────────────────────────────────────────────────────────


def test_enrich_epub_dry_run_no_writes(sample_epub: Path) -> None:
    """--dry-run: plan policzony, plik na dysku nietknięty."""
    original = sample_epub.read_bytes()
    outcome = enrich_epub(sample_epub, EnrichOptions(dry_run=True), _fetcher(_RECORD), None)
    assert outcome.found
    assert outcome.changed  # są planowane zmiany
    assert sample_epub.read_bytes() == original  # nic nie zapisano


def test_enrich_epub_applies_and_saves(sample_epub: Path) -> None:
    """Bez dry-run: puste pola i liczba stron zapisane do OPF."""
    outcome = enrich_epub(sample_epub, EnrichOptions(), _fetcher(_RECORD), None)
    assert outcome.match == "isbn"
    with Epub(sample_epub) as epub:
        meta = epub.metadata
        assert meta.publisher == "SuperNOWA"
        assert meta.series == "Wiedźmin"
        assert get_number_of_pages(epub.read_file(epub.opf_path)) == 330


def test_enrich_epub_no_match(sample_epub: Path) -> None:
    """Brak dopasowania → match=brak, zero zmian, plik nietknięty."""
    original = sample_epub.read_bytes()
    outcome = enrich_epub(sample_epub, EnrichOptions(), _fetcher(None, "brak"), None)
    assert outcome.match == "brak"
    assert not outcome.found
    assert sample_epub.read_bytes() == original


def test_enrich_paths_summary(sample_epub: Path) -> None:
    """Podsumowanie liczy znalezione/z cache."""
    _outcomes, summary = enrich_paths(
        [sample_epub], EnrichOptions(dry_run=True), fetcher=_fetcher(_RECORD, from_cache=True)
    )
    assert summary.total == 1
    assert summary.found == 1
    assert summary.from_cache == 1


def test_collect_epubs_expands_directory(tmp_path: Path, sample_epub: Path) -> None:
    """Katalog jest rozwijany do plików .epub (bez duplikatów)."""
    import shutil

    (tmp_path / "a.epub").write_bytes(b"x")
    shutil.copy2(sample_epub, tmp_path / "b.epub")
    found = collect_epubs([tmp_path, tmp_path / "b.epub"])
    names = [p.name for p in found]
    assert {"a.epub", "b.epub"} <= set(names)
    assert names.count("b.epub") == 1  # katalog + jawna ścieżka → bez duplikatu


def test_cancellation_stops_early(sample_epub: Path, tmp_path: Path) -> None:
    """should_cancel przerywa przetwarzanie kolejnych książek."""
    import shutil

    second = tmp_path / "second.epub"
    shutil.copy2(sample_epub, second)
    outcomes, _summary = enrich_paths(
        [sample_epub, second],
        EnrichOptions(dry_run=True),
        fetcher=_fetcher(_RECORD),
        should_cancel=lambda: True,  # anuluj od razu
    )
    assert outcomes == []


# ── Raport ──────────────────────────────────────────────────────────────────────


def test_report_csv(tmp_path: Path) -> None:
    """Raport CSV zawiera nagłówek i wiersz per książka."""
    outcomes = [BookOutcome("book.epub", "isbn", "bn", ["publisher"], ["title"], from_cache=True)]
    path = tmp_path / "report.csv"
    write_report(path, outcomes, EnrichSummary.from_outcomes(outcomes))
    text = path.read_text(encoding="utf-8")
    assert "identifier,match,source" in text
    assert "book.epub,isbn,bn" in text


def test_report_json(tmp_path: Path) -> None:
    """Raport JSON zawiera podsumowanie i listę książek."""
    outcomes = [BookOutcome("1", "fuzzy", "lubimyczytac", ["date"], [])]
    path = tmp_path / "report.json"
    write_report(path, outcomes, EnrichSummary.from_outcomes(outcomes))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["found"] == 1
    assert data["books"][0]["match"] == "fuzzy"


def test_format_summary_line() -> None:
    """Podsumowanie tekstowe wymienia kluczowe liczby."""
    line = format_summary(EnrichSummary(total=3, found=2, not_found=1, from_cache=1, changed=2))
    assert "3" in line and "2" in line


# ── Backend calibredb (mock subprocess) ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fake_calibredb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Udaje wykryte ``calibredb`` (żeby nie zależeć od instalacji Calibre)."""
    tool = SimpleNamespace(path=Path("/usr/bin/calibredb"))
    monkeypatch.setattr(calibre_mod.Tools, "calibredb", staticmethod(lambda: tool))


def _runner(calls: list[list[str]], *, books: str = "[]", returncode: int = 0, stderr: str = ""):
    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(command)
        if "set_metadata" in command:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        return SimpleNamespace(stdout=books, stderr=stderr, returncode=returncode)

    return run


def test_calibre_preflight_lock_stops() -> None:
    """Blokada bazy (returncode != 0) → CalibreError z czytelnym komunikatem."""
    runner = _runner([], returncode=1, stderr="database is locked")
    with pytest.raises(CalibreError, match="Zamknij program Calibre"):
        preflight(Path("/lib"), runner=runner)


def test_calibre_list_builds_command() -> None:
    """list_books buduje poprawną komendę i parsuje JSON."""
    calls: list[list[str]] = []
    books_json = json.dumps(
        [{"id": 7, "title": "Stara", "authors": ["Autor X"], "isbn": "", "tags": ["a"]}]
    )
    runner = _runner(calls, books=books_json)
    books = list_books(Path("/lib"), runner=runner)
    assert books[0].id == 7
    assert books[0].authors == ["Autor X"]
    command = calls[0]
    assert "list" in command and "--for-machine" in command
    assert "--library-path" in command and str(Path("/lib")) in command  # zależne od platformy


def test_calibre_set_metadata_command() -> None:
    """set_metadata przekazuje id i pola jako --field name:value."""
    calls: list[list[str]] = []
    set_metadata(Path("/lib"), 7, {"title": "Nowy", "tags": "a,b"}, runner=_runner(calls))
    command = calls[0]
    assert command[1] == "set_metadata"
    assert "7" in command
    assert "--field" in command and "title:Nowy" in command and "tags:a,b" in command


def test_calibre_enrich_library_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pełny przepływ: preflight → list → fetch → set_metadata (fill uzupełnia puste)."""
    calls: list[list[str]] = []
    books_json = json.dumps(
        [{"id": 1, "title": "Ostatnie życzenie", "authors": [], "isbn": "", "tags": []}]
    )
    outcomes, summary = enrich_library(
        Path("/lib"),
        EnrichOptions(),
        fetcher=_fetcher(_RECORD),
        runner=_runner(calls, books=books_json),
    )
    assert summary.found == 1
    assert outcomes[0].changed  # coś zmieniono
    set_calls = [c for c in calls if "set_metadata" in c]
    assert len(set_calls) == 1
    joined = " ".join(set_calls[0])
    assert "publisher:SuperNOWA" in joined  # puste pole uzupełnione


def test_calibre_dry_run_no_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run dla Calibre: brak wywołań set_metadata."""
    calls: list[list[str]] = []
    books_json = json.dumps([{"id": 1, "title": "X", "authors": [], "isbn": "", "tags": []}])
    enrich_library(
        Path("/lib"),
        EnrichOptions(dry_run=True),
        fetcher=_fetcher(_RECORD),
        runner=_runner(calls, books=books_json),
    )
    assert not any("set_metadata" in c for c in calls)
