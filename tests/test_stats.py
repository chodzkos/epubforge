"""Testy statystyk książki (compute_stats, top-słowa, język, raport HTML, CLI)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from epubforge.cli.main import main
from epubforge.core import Epub
from epubforge.stats import (
    BookStats,
    ChapterStats,
    _top_words,
    _word_tokens,
    compute_stats,
    render_report_html,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"


# ── Tokenizacja i liczby ─────────────────────────────────────────────────────


def test_word_tokens_counts_and_filters_numbers() -> None:
    """„Zażółć gęślą jaźń" = 3 słowa; czyste liczby są odfiltrowane."""
    assert _word_tokens("Zażółć gęślą jaźń") == ["Zażółć", "gęślą", "jaźń"]
    assert _word_tokens("mam 3 koty i 42 psy") == ["mam", "koty", "i", "psy"]


def test_compute_stats_sample_deterministic() -> None:
    """Statystyki sample.epub są deterministyczne (6 słów, 1 rozdział)."""
    with Epub(_FIXTURE) as epub:
        stats = compute_stats(epub)
    assert stats.words == 6
    assert len(stats.chapters) == 1
    assert stats.estimated_pages == 1
    assert stats.reading_time_min == 1
    assert stats.chapters[0].title == "Rozdział 1"


# ── Stop-listy i top-słowa ───────────────────────────────────────────────────


def test_polish_stopwords_filter_function_words() -> None:
    """Stop-lista PL filtruje „i", „w", „się"."""
    words = ["i", "w", "się", "kot", "kot", "pies"]
    top = _top_words(words, "pl", top_n=10)
    assert top == [("kot", 2), ("pies", 1)]


def test_top_words_sort_descending_with_alphabetical_tie() -> None:
    """Top-słowa sortują się malejąco, remis alfabetycznie; top_n respektowane."""
    words = ["banan", "ala", "ala", "banan", "cebula", "cebula", "dom"]
    top = _top_words(words, None, top_n=2)
    # ala=2, banan=2, cebula=2 → alfabetycznie ala, banan; top_n=2
    assert top == [("ala", 2), ("banan", 2)]


# ── Fallback języka ──────────────────────────────────────────────────────────


def test_language_falls_back_to_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bez langdetect (ImportError) język pochodzi z metadanych."""
    monkeypatch.setitem(sys.modules, "langdetect", None)  # import langdetect → ImportError
    with Epub(_FIXTURE) as epub:
        stats = compute_stats(epub)
    assert stats.language_source == "metadata"
    assert stats.language == "pl"


# ── Raport HTML ──────────────────────────────────────────────────────────────


def _stats_with_chapters(chapters: list[ChapterStats], *, title: str = "Tytuł") -> BookStats:
    return BookStats(
        title=title,
        authors=["Autor Testowy"],
        words=sum(c.words for c in chapters),
        chars=100,
        chapters=chapters,
        estimated_pages=1,
        reading_time_min=5,
        language="pl",
        language_source="metadata",
        top_words=[("kot", 3), ("pies", 1)],
    )


def test_report_contains_title_and_escapes_chapter() -> None:
    """Raport zawiera tytuł książki i escapuje złośliwy tytuł rozdziału."""
    stats = _stats_with_chapters(
        [ChapterStats(title="<b>złośliwy</b>", words=10, chars=50)], title="Moja Książka"
    )
    html = render_report_html(stats, "9.9.9")
    assert "Moja Książka" in html
    assert "&lt;b&gt;złośliwy&lt;/b&gt;" in html
    assert "<b>złośliwy</b>" not in html
    assert "http" not in html  # samowystarczalny — zero zasobów sieciowych
    assert "EpubForge 9.9.9" in html


def test_report_rect_count_matches_chapters() -> None:
    """Liczba <rect> w SVG = liczba rozdziałów (gdy ≤ 60)."""
    chapters = [ChapterStats(title=f"R{i}", words=i + 1, chars=10) for i in range(5)]
    html = render_report_html(_stats_with_chapters(chapters))
    assert html.count("<rect") == 5


def test_report_aggregates_bars_above_limit() -> None:
    """Powyżej 60 rozdziałów słupki są agregowane do ≤ 60."""
    chapters = [ChapterStats(title=f"R{i}", words=i + 1, chars=10) for i in range(100)]
    html = render_report_html(_stats_with_chapters(chapters))
    assert html.count("<rect") <= 60


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_stats_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`epubforge stats --report` kończy się 0 i tworzy plik raportu."""
    report = tmp_path / "report.html"
    exit_code = main(["stats", str(_FIXTURE), "--report", str(report)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert report.is_file()
    assert "Słowa:" in out
