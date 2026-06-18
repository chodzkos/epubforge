"""Statystyki książki EPUB: słowa, strony, czas czytania, język, top-słowa.

Czysta logika (bez Qt): ekstrakcja tekstu ze spine (lxml recover, bez ``script``/
``style``), tokenizacja, wykrywanie języka (opcjonalny ``langdetect`` z fallbackiem
do metadanych) i samowystarczalny raport HTML (inline CSS, inline SVG — zero
zasobów sieciowych, ``html.escape`` na każdej wartości z książki).
"""

from __future__ import annotations

import html
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from epubforge.core.epub import Epub
from epubforge.toc._xml import (
    first_by_localname,
    iter_by_localname,
    localname,
    normalized_text,
    parse_xml,
    resolve_internal,
)

# Próbka tekstu do wykrywania języka (znaki).
_LANG_SAMPLE = 10_000
# Maks. liczba słupków na wykresie (powyżej — agregacja w kubełki).
_MAX_BARS = 60
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_SUPPORTED_STOP_LANGS = {"pl", "en", "de"}

# Jasna paleta GUI_STANDARD §5 — zduplikowana ŚWIADOMIE: raport HTML to samodzielny
# artefakt (otwierany w przeglądarce, drukowany do PDF), więc NIE importujemy
# gui.theme, by warstwa core/CLI nie ciągnęła zależności od PySide6. Kolory tekstowe
# akcentu = accent2 #0F7C5B (nota WCAG: kontrast na jasnym tle).
_BG = "#ffffff"
_BG2 = "#f5f5f7"
_FG = "#1d1d1f"
_FG2 = "#515154"
_ACCENT2 = "#0F7C5B"
_BORDER = "#d1d1d6"


@dataclass(frozen=True)
class ChapterStats:
    """Statystyki pojedynczego dokumentu spine."""

    title: str | None
    words: int
    chars: int


@dataclass(frozen=True)
class BookStats:
    """Zbiorcze statystyki książki."""

    title: str
    authors: list[str]
    words: int
    chars: int
    chapters: list[ChapterStats] = field(default_factory=list)
    estimated_pages: int = 0
    reading_time_min: int = 0
    language: str | None = None
    language_source: str = "none"  # "langdetect" | "metadata" | "none"
    top_words: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class StatsOptions:
    """Parametry obliczeń statystyk."""

    words_per_page: int = 250
    wpm: int = 200
    top_n: int = 50


def compute_stats(epub: Epub, options: StatsOptions | None = None) -> BookStats:
    """Liczy statystyki otwartego EPUB-a (słowa, strony, czas, język, top-słowa)."""
    opts = options if options is not None else StatsOptions()
    metadata = epub.metadata

    chapters: list[ChapterStats] = []
    full_text_parts: list[str] = []
    for internal in _spine_paths(epub):
        try:
            root, _doctype = parse_xml(epub.read_file(internal))
        except (KeyError, ValueError):
            continue
        body = first_by_localname(root, "body")  # licz tylko treść, nie <head><title>
        text = _text_content(body if body is not None else root)
        words = _word_tokens(text)
        full_text_parts.append(text)
        chapters.append(ChapterStats(title=_chapter_title(root), words=len(words), chars=len(text)))

    full_text = "\n".join(full_text_parts)
    all_words = _word_tokens(full_text)
    total_words = len(all_words)
    language, language_source = _detect_language(full_text, metadata.language)
    return BookStats(
        title=metadata.title,
        authors=list(metadata.creators),
        words=total_words,
        chars=sum(chapter.chars for chapter in chapters),
        chapters=chapters,
        estimated_pages=_ceil_div(total_words, opts.words_per_page),
        reading_time_min=_ceil_div(total_words, opts.wpm),
        language=language,
        language_source=language_source,
        top_words=_top_words(all_words, language, opts.top_n),
    )


# ── Ekstrakcja tekstu ───────────────────────────────────────────────────────


def _spine_paths(epub: Epub) -> list[str]:
    """Ścieżki wewnętrzne dokumentów w kolejności spine."""
    by_id = {item.id: item for item in epub.manifest}
    paths: list[str] = []
    for idref in epub.spine:
        item = by_id.get(idref)
        if item is not None:
            paths.append(resolve_internal(epub.opf_dir(), item.href)[0])
    return paths


def _text_content(root: object) -> str:
    """Zbiera tekst dokumentu, pomijając poddrzewa ``script`` i ``style``."""
    parts: list[str] = []

    def walk(element: object) -> None:
        for child in element:  # type: ignore[attr-defined]
            if localname(child) in {"script", "style"}:
                continue
            if child.text:
                parts.append(child.text)
            walk(child)
            if child.tail:
                parts.append(child.tail)

    if getattr(root, "text", None):
        parts.append(root.text)  # type: ignore[attr-defined]
    walk(root)
    return " ".join(" ".join(parts).split())


def _chapter_title(root: object) -> str | None:
    """Tytuł rozdziału: pierwszy ``h1``/``h2``, inaczej ``<title>``, inaczej ``None``."""
    for heading in iter_by_localname(root, {"h1", "h2"}):  # type: ignore[arg-type]
        text = normalized_text(heading)
        if text:
            return text
    title_el = first_by_localname(root, "title")  # type: ignore[arg-type]
    if title_el is not None:
        text = normalized_text(title_el)
        if text:
            return text
    return None


def _word_tokens(text: str) -> list[str]:
    """Tokenizuje tekst na słowa (``\\w+`` unicode), odfiltrowując czyste liczby."""
    return [token for token in _WORD_RE.findall(text) if not token.isdigit()]


def _ceil_div(value: int, divisor: int) -> int:
    """Dzielenie z zaokrągleniem w górę (0 dla pustego wejścia)."""
    if value <= 0 or divisor <= 0:
        return 0
    return math.ceil(value / divisor)


# ── Język ───────────────────────────────────────────────────────────────────


def _detect_language(text: str, metadata_language: str) -> tuple[str | None, str]:
    """Wykrywa język (langdetect → metadane → None) i zwraca ``(język, źródło)``."""
    detected = _langdetect_sample(text[:_LANG_SAMPLE])
    if detected is not None:
        return detected, "langdetect"
    fallback = (metadata_language or "").strip().lower()[:2]
    if fallback:
        return fallback, "metadata"
    return None, "none"


def _langdetect_sample(sample: str) -> str | None:
    """Próbuje wykryć język próbki przez ``langdetect`` (None gdy brak lib/błąd)."""
    if not sample.strip():
        return None
    try:
        from langdetect import DetectorFactory, detect
    except ImportError:
        return None
    DetectorFactory.seed = 0  # bez seeda langdetect jest niedeterministyczny
    try:
        return str(detect(sample))
    except Exception:
        return None


# ── Top-słowa ───────────────────────────────────────────────────────────────


def _top_words(words: list[str], language: str | None, top_n: int) -> list[tuple[str, int]]:
    """Zlicza słowa (bez stop-listy), sortuje malejąco z remisem alfabetycznym."""
    stop = _load_stopwords(language)
    counter: Counter[str] = Counter()
    for token in words:
        lower = token.lower()
        if lower not in stop:
            counter[lower] += 1
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:top_n]


def _stopwords_dir() -> Path:
    """Katalog ze stop-listami (działa też w bundlu PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "stats_stopwords"
    return Path(__file__).resolve().parent / "stats_stopwords"


@cache
def _load_stopwords(language: str | None) -> frozenset[str]:
    """Wczytuje stop-listę dla języka (z cache); pusta gdy język nieobsługiwany."""
    code = (language or "").lower()[:2]
    if code not in _SUPPORTED_STOP_LANGS:
        return frozenset()
    path = _stopwords_dir() / f"{code}.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(word.strip().lower() for word in lines if word.strip())


# ── Raport HTML ─────────────────────────────────────────────────────────────


def render_report_html(stats: BookStats, app_version: str = "") -> str:
    """Buduje samowystarczalny raport HTML (inline CSS jasnej palety, inline SVG)."""
    authors = ", ".join(stats.authors)
    header = (
        f"<h1>{html.escape(stats.title or '(bez tytułu)')}</h1>"
        f"<p class='authors'>{html.escape(authors)}</p>"
    )
    body = "".join(
        (
            header,
            _cards_html(stats),
            _tag_cloud_html(stats.top_words),
            _chapters_table_html(stats.chapters),
            _bar_chart_section(stats.chapters),
            _footer_html(app_version),
        )
    )
    return _HTML_TEMPLATE.format(css=_REPORT_CSS, body=body)


def _cards_html(stats: BookStats) -> str:
    """Karty liczbowe: słowa, strony, czas czytania, język."""
    language = stats.language or "—"
    if stats.language and stats.language_source != "none":
        language = f"{html.escape(stats.language)} ({html.escape(stats.language_source)})"
    cards = [
        (str(stats.words), "słowa"),
        (str(stats.estimated_pages), "szac. strony"),
        (_format_minutes(stats.reading_time_min), "czas czytania"),
        (language, "język"),
    ]
    items = "".join(
        f"<div class='card'><span class='num'>{value}</span>"
        f"<span class='label'>{html.escape(label)}</span></div>"
        for value, label in cards
    )
    return f"<div class='cards'>{items}</div>"


def _tag_cloud_html(top_words: list[tuple[str, int]]) -> str:
    """Chmurka top-słów; rozmiar fontu w skali logarytmicznej 12-40 px."""
    if not top_words:
        return ""
    counts = [count for _word, count in top_words]
    low, high = math.log(min(counts)), math.log(max(counts))
    spans = []
    for word, count in top_words:
        size = 12.0 if high == low else 12 + 28 * (math.log(count) - low) / (high - low)
        spans.append(
            f"<span style='font-size:{size:.0f}px' title='{count}'>{html.escape(word)}</span>"
        )
    return f"<h2>Najczęstsze słowa</h2><div class='cloud'>{' '.join(spans)}</div>"


def _chapters_table_html(chapters: list[ChapterStats]) -> str:
    """Tabela rozdziałów (tytuł, słowa)."""
    rows = "".join(
        f"<tr><td>{html.escape(chapter.title or f'Rozdział {index}')}</td>"
        f"<td class='r'>{chapter.words}</td></tr>"
        for index, chapter in enumerate(chapters, start=1)
    )
    return f"<h2>Rozdziały</h2><table><thead><tr><th>Tytuł</th><th>Słowa</th></tr></thead><tbody>{rows}</tbody></table>"


def _bar_chart_section(chapters: list[ChapterStats]) -> str:
    """Sekcja z wykresem słupkowym liczby słów w rozdziałach."""
    if not chapters:
        return ""
    values = [chapter.words for chapter in chapters]
    return f"<h2>Słowa w rozdziałach</h2>{_bar_chart_svg(values)}"


def _bar_chart_svg(values: list[int]) -> str:
    """Inline SVG wykresu słupkowego (≤60 słupków; powyżej — agregacja w kubełki).

    Bez deklaracji ``xmlns`` (inline SVG w HTML5) — raport nie sięga do sieci.
    """
    bars = _aggregate(values, _MAX_BARS)
    if not bars:
        return ""
    width, height, gap = 720, 200, 2
    bar_width = (width - gap * (len(bars) - 1)) / len(bars)
    peak = max(bars) or 1
    rects = []
    for index, value in enumerate(bars):
        bar_height = (value / peak) * (height - 10)
        x = index * (bar_width + gap)
        y = height - bar_height
        rects.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_width:.1f}' "
            f"height='{bar_height:.1f}'></rect>"
        )
    return (
        f"<svg class='chart' viewBox='0 0 {width} {height}' width='100%' height='{height}'>"
        f"{''.join(rects)}</svg>"
    )


def _aggregate(values: list[int], max_bars: int) -> list[int]:
    """Redukuje listę do ≤``max_bars`` słupków, sumując sąsiednie kubełki."""
    if len(values) <= max_bars:
        return values
    bucket = math.ceil(len(values) / max_bars)
    return [sum(values[i : i + bucket]) for i in range(0, len(values), bucket)]


def _footer_html(app_version: str) -> str:
    """Stopka z podpowiedzią druku do PDF i wersją aplikacji."""
    version = f" · EpubForge {html.escape(app_version)}" if app_version else ""
    return f"<footer>Wydrukuj do PDF: Ctrl+P{version}</footer>"


def _format_minutes(minutes: int) -> str:
    """Formatuje minuty jako ``h:mm`` albo ``N min``."""
    if minutes >= 60:
        return f"{minutes // 60}:{minutes % 60:02d} h"
    return f"{minutes} min"


_REPORT_CSS = (
    f"body{{font-family:sans-serif;margin:2rem;background:{_BG};color:{_FG};}}"
    f"h1{{margin-bottom:0;}}.authors{{color:{_FG2};margin-top:.2rem;}}"
    f"h2{{color:{_ACCENT2};border-bottom:1px solid {_BORDER};padding-bottom:.2rem;}}"
    ".cards{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0;}"
    f".card{{background:{_BG2};border:1px solid {_BORDER};border-radius:8px;"
    "padding:1rem 1.4rem;min-width:120px;text-align:center;}}"
    f".card .num{{display:block;font-size:1.8rem;font-weight:bold;color:{_ACCENT2};}}"
    f".card .label{{color:{_FG2};font-size:.85rem;}}"
    ".cloud{line-height:2;}"
    f".cloud span{{margin:0 .35rem;color:{_ACCENT2};}}"
    "table{border-collapse:collapse;width:100%;}"
    f"th,td{{border:1px solid {_BORDER};padding:.3rem .6rem;text-align:left;}}"
    "td.r{text-align:right;}"
    f".chart rect{{fill:{_ACCENT2};}}"
    f"footer{{margin-top:2rem;color:{_FG2};font-size:.85rem;}}"
)

_HTML_TEMPLATE = (
    "<!DOCTYPE html><html lang='pl'><head><meta charset='utf-8'>"
    "<title>Statystyki książki</title><style>{css}</style></head>"
    "<body>{body}</body></html>"
)
