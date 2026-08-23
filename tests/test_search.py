"""Testy szukania i zamiany w plikach EPUB (czysta logika ``core.search``)."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from epubforge.core import Epub
from epubforge.core.search import (
    SearchPatternError,
    replace_in_epub,
    search_epub,
)

_CHAPTER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
    "<body>\n<p>Ala ma kota, a kot ma Alę.</p>\n<p>żółć i ZOO</p>\n</body></html>"
)


def _build_epub(tmp_path: Path, files: dict[str, bytes] | None = None) -> Path:
    """Buduje minimalny EPUB z jednym rozdziałem i opcjonalnymi dodatkowymi plikami."""
    epub_path = tmp_path / "book.epub"
    extra = files or {}
    extra_items = "".join(
        f'<item id="x{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(extra)
    )
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="b">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="b">id</dc:identifier><dc:title>t</dc:title>'
        "<dc:language>pl</dc:language></metadata>"
        '<manifest><item id="c1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>'
        f'<item id="css" href="styles/main.css" media-type="text/css"/>{extra_items}</manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", _CHAPTER.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/styles/main.css", b"p { color: red; }", zipfile.ZIP_DEFLATED)
        for href, data in extra.items():
            zf.writestr(f"OEBPS/{href}", data, zipfile.ZIP_STORED)
    return epub_path


# ── Szukanie ─────────────────────────────────────────────────────────────────


def test_search_literal(tmp_path: Path) -> None:
    """Literalne szukanie znajduje wszystkie wystąpienia z linią i kolumną."""
    with Epub(_build_epub(tmp_path)) as epub:
        hits = search_epub(epub, "kot")
    paths = {hit.internal_path for hit in hits}
    assert "OEBPS/text/chapter1.xhtml" in paths
    kot = [h for h in hits if h.internal_path.endswith("chapter1.xhtml")]
    # „kota" i „kot" — dwa trafienia w linii 2 (1-based).
    assert len(kot) == 2
    assert all(hit.line == 2 for hit in kot)
    assert kot[0].column >= 1


def test_search_case_sensitive(tmp_path: Path) -> None:
    """Domyślnie bez rozróżniania wielkości; z case_sensitive rozróżnia."""
    with Epub(_build_epub(tmp_path)) as epub:
        insensitive = search_epub(epub, "zoo")
        sensitive = search_epub(epub, "zoo", case_sensitive=True)
    assert any(h.internal_path.endswith("chapter1.xhtml") for h in insensitive)
    assert not any(h.internal_path.endswith("chapter1.xhtml") for h in sensitive)  # jest „ZOO"


def test_search_whole_words_unicode(tmp_path: Path) -> None:
    """Całe słowa działają dla polskich znaków (żółć) dzięki re.UNICODE."""
    with Epub(_build_epub(tmp_path)) as epub:
        whole = search_epub(epub, "żółć", whole_words=True)
        partial = search_epub(epub, "ółć", whole_words=True)
    assert any(h.internal_path.endswith("chapter1.xhtml") for h in whole)
    assert partial == []  # „ółć" nie jest całym słowem


def test_search_regex(tmp_path: Path) -> None:
    """Regex dopasowuje wzorzec (słowa 3-literowe zaczynające się na 'ko')."""
    with Epub(_build_epub(tmp_path)) as epub:
        hits = search_epub(epub, r"ko\w", regex=True)
    assert any(h.internal_path.endswith("chapter1.xhtml") for h in hits)


def test_search_bad_regex_raises(tmp_path: Path) -> None:
    """Błędny regex → SearchPatternError (nie traceback)."""
    with Epub(_build_epub(tmp_path)) as epub, pytest.raises(SearchPatternError):
        search_epub(epub, "(niezamknięty", regex=True)


def test_search_empty_pattern_rejected(tmp_path: Path) -> None:
    """Wzorzec dopasowujący pusty ciąg jest odrzucany."""
    with Epub(_build_epub(tmp_path)) as epub, pytest.raises(SearchPatternError):
        search_epub(epub, "a*", regex=True)


def test_search_scoped_to_paths(tmp_path: Path) -> None:
    """Zakres paths ogranicza wyszukiwanie do wskazanych plików."""
    with Epub(_build_epub(tmp_path)) as epub:
        hits = search_epub(epub, "color", paths=["OEBPS/styles/main.css"])
    assert {h.internal_path for h in hits} == {"OEBPS/styles/main.css"}


# ── Zamiana ──────────────────────────────────────────────────────────────────


def test_replace_writes_to_buffer_only(tmp_path: Path) -> None:
    """Zamiana trafia do bufora; dysk pozostaje nietknięty do save()."""
    path = _build_epub(tmp_path)
    with Epub(path) as epub:
        report = replace_in_epub(epub, "kot", "pies")
        assert report.total == 2
        assert "OEBPS/text/chapter1.xhtml" in report.changed_files
        assert b"pies" in epub.read_file("OEBPS/text/chapter1.xhtml")
    # Bez save() — świeże otwarcie z dysku wciąż ma oryginał.
    with Epub(path) as fresh:
        assert b"pies" not in fresh.read_file("OEBPS/text/chapter1.xhtml")
        assert b"kot" in fresh.read_file("OEBPS/text/chapter1.xhtml")


def test_replace_literal_does_not_interpret_backrefs(tmp_path: Path) -> None:
    """W trybie literalnym podstawienie ze znakiem '\\1' nie jest interpretowane."""
    with Epub(_build_epub(tmp_path)) as epub:
        report = replace_in_epub(epub, "kota", r"\1x")
        text = epub.read_file("OEBPS/text/chapter1.xhtml").decode("utf-8")
    assert report.total == 1
    assert r"\1x" in text


def test_replace_skips_non_utf8_file(tmp_path: Path) -> None:
    """Plik ze znakami zastępczymi (nie-UTF-8) jest pomijany przy zamianie."""
    broken = {"text/broken.xhtml": b"<p>kot \xff\xfe kot</p>"}
    path = _build_epub(tmp_path, broken)
    with Epub(path) as epub:
        # Szukanie w takim pliku jest dozwolone…
        found = search_epub(epub, "kot", paths=["OEBPS/text/broken.xhtml"])
        assert found  # trafienia są
        # …ale zamiana pomija go z powodem.
        report = replace_in_epub(epub, "kot", "pies")
        skipped_paths = {path for path, _reason in report.skipped}
        assert "OEBPS/text/broken.xhtml" in skipped_paths
        assert "OEBPS/text/broken.xhtml" not in report.changed_files
        # niezłamany rozdział nadal podmieniony
        assert "OEBPS/text/chapter1.xhtml" in report.changed_files


def test_replace_regex_backreference(tmp_path: Path) -> None:
    """W trybie regex podstawienie może używać grup (\\1)."""
    with Epub(_build_epub(tmp_path)) as epub:
        report = replace_in_epub(epub, r"(kot)a", r"\1y", regex=True)
        text = epub.read_file("OEBPS/text/chapter1.xhtml").decode("utf-8")
    assert report.total == 1
    assert "koty" in text


# ── ReDoS / timeout ───────────────────────────────────────────────────────────

_REDOS_NESTED = "(x+x+)+y"
_REDOS_TIMEOUT = r"(a|a)+$"
_WATCHDOG_SECONDS = 5.0


def _run_search_script(epub_path: Path, query: str) -> subprocess.CompletedProcess[str]:
    """Woła ``search_epub`` w osobnym procesie — watchdog, nie wall-clock w pytest."""
    code = textwrap.dedent(
        f"""
        from epubforge.core import Epub
        from epubforge.core.search import SearchPatternError, search_epub
        with Epub(r"{epub_path}") as epub:
            try:
                hits = search_epub(epub, r"{query}", regex=True)
            except SearchPatternError as exc:
                print("error", type(exc).__name__, str(exc), flush=True)
            else:
                print("hits", len(hits), flush=True)
        """
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_WATCHDOG_SECONDS,
    )


def test_search_nested_quantifier_does_not_hang(tmp_path: Path) -> None:
    """Klasyczny ``(x+x+)+y`` na ``x``*28 nie wiesza procesu (API ``search_epub``)."""
    path = _build_epub(tmp_path, {"text/payload.xhtml": ("x" * 28).encode()})
    result = _run_search_script(path, _REDOS_NESTED)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("hits 0")


def test_search_expensive_regex_raises_timeout(tmp_path: Path) -> None:
    """Wzorzec, który pakiet regex też backtrackuje, kończy się SearchPatternError."""
    path = _build_epub(tmp_path, {"text/payload.xhtml": ("a" * 28 + "!").encode()})
    result = _run_search_script(path, _REDOS_TIMEOUT)
    assert result.returncode == 0, result.stderr
    assert "SearchPatternError" in result.stdout
    assert "limit czasu" in result.stdout


def test_replace_expensive_regex_skips_timed_out_file(tmp_path: Path) -> None:
    """Timeout w późniejszym pliku nie gubi wcześniejszej udanej zamiany."""
    path = _build_epub(
        tmp_path,
        {
            "text/a.xhtml": b"aaa",
            "text/z.xhtml": ("a" * 28 + "!").encode(),
        },
    )
    code = textwrap.dedent(
        f"""
        from epubforge.core import Epub
        from epubforge.core.search import replace_in_epub
        with Epub(r"{path}") as epub:
            report = replace_in_epub(
                epub,
                r"{_REDOS_TIMEOUT}",
                "z",
                regex=True,
                paths=["OEBPS/text/a.xhtml", "OEBPS/text/z.xhtml"],
            )
        print("total", report.total)
        print("changed", ",".join(report.changed_files))
        for internal, reason in report.skipped:
            print("skipped", internal, reason)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_WATCHDOG_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    assert "total 1" in result.stdout
    assert "changed OEBPS/text/a.xhtml" in result.stdout
    assert "skipped OEBPS/text/z.xhtml" in result.stdout
    assert "limit czasu" in result.stdout
