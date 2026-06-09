"""Testy konwersji do EPUB.

Zewnętrzne binaria są mockowane: nie uruchamiamy Pandoc ani Calibre w CI.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from epubforge.cli import convert as cli_convert
from epubforge.cli.main import main
from epubforge.converters import ConversionResult, ConvertOptions, to_epub
from epubforge.core import Metadata
from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError

converter = importlib.import_module("epubforge.converters.to_epub")


def _tool(name: str, path: str) -> Tool:
    """Buduje dostępne narzędzie do testów."""
    return Tool(name=name, path=Path(path), version=f"{name} 1.0", available=True)


def _missing_tool(name: str) -> Tool:
    """Buduje niedostępne narzędzie do testów."""
    return Tool(name=name, path=None, version="", available=False)


def _fake_run(
    calls: list[tuple[list[str], dict[str, object]]],
    *,
    stdout: str = "ok",
    stderr: str = "",
    returncode: int = 0,
):
    """Zwraca mock ``subprocess.run`` zapisujący komendę i opcje."""

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return run


def test_pandoc_command_with_metadata_cover_and_css(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pandoc dostaje ścieżki, EPUB version, TOC, CSS, okładkę i metadane."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _tool("pandoc", "/bin/pandoc")))
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls, stdout="pandoc log"))

    source = tmp_path / "book.md"
    target = tmp_path / "book.epub"
    cover = tmp_path / "cover.jpg"
    css = tmp_path / "style.css"
    metadata = Metadata(
        title="Zażółć jaźń",
        creators=["Jan Kowalski", "Anna Nowak"],
        language="pl",
        publisher="EpubForge",
        subjects=["fiction", "test"],
    )

    result = to_epub(
        source,
        target,
        ConvertOptions(metadata=metadata, cover_image=cover, css=css, toc_depth=2),
        engine="pandoc",
    )

    command, kwargs = calls[0]
    assert result == ConversionResult(True, target, "pandoc log", "pandoc")
    assert command[:6] == [
        "/bin/pandoc",
        str(source),
        "--to",
        "epub3",
        "--output",
        str(target),
    ]
    assert command[6:9] == ["--toc", "--toc-depth", "2"]
    assert command[9:11] == ["--css", str(css)]
    assert command[11:13] == ["--epub-cover-image", str(cover)]
    assert command[13:15] == ["--metadata", "title=Zażółć jaźń"]
    assert "--metadata" in command
    assert "author=Jan Kowalski" in command
    assert "author=Anna Nowak" in command
    assert "subject=fiction" in command
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["check"] is False


def test_calibre_command_with_metadata_and_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibre dostaje ebook-convert, EPUB version, okładkę i metadane CLI."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls, stdout="calibre log"))

    source = tmp_path / "book.docx"
    target = tmp_path / "book.epub"
    cover = tmp_path / "cover.jpg"
    metadata = Metadata(
        title="Book",
        creators=["A", "B"],
        language="en",
        publisher="Publisher",
        date="2026-01-02",
        description="Description",
        subjects=["one", "two"],
    )

    result = to_epub(
        source,
        target,
        ConvertOptions(epub_version="epub2", metadata=metadata, cover_image=cover),
        engine="calibre",
    )

    command, _kwargs = calls[0]
    assert result.engine == "calibre"
    assert command[:6] == [
        "/bin/ebook-convert",
        str(source),
        str(target),
        "--epub-version",
        "2",
        "--cover",
    ]
    assert str(cover) == command[6]
    assert command[7:9] == ["--title", "Book"]
    assert command[9:11] == ["--authors", "A & B"]
    assert command[11:13] == ["--language", "en"]
    assert "--publisher" in command
    assert "--pubdate" in command
    assert "--comments" in command
    assert "--tags" in command
    assert "one,two" in command


def test_auto_uses_pandoc_for_non_pdf_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto wybiera Pandoc dla nie-PDF, jeśli jest dostępny."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _tool("pandoc", "/p")))
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))

    result = to_epub(tmp_path / "book.html", tmp_path / "book.epub")

    assert result.engine == "pandoc"
    assert calls[0][0][0] == "/p"


def test_auto_falls_back_to_calibre_when_pandoc_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto dla nie-PDF przechodzi na Calibre, gdy Pandoc jest niedostępny."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _missing_tool("pandoc")))
    monkeypatch.setattr(
        converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/ebook-convert")),
    )
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))

    result = to_epub(tmp_path / "book.rtf", tmp_path / "book.epub")

    assert result.engine == "calibre"
    assert calls[0][0][0] == "/ebook-convert"


def test_auto_pdf_uses_calibre_even_when_pandoc_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PDF w trybie auto trafia do Calibre, nawet jeśli Pandoc jest dostępny."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _tool("pandoc", "/pandoc")))
    monkeypatch.setattr(
        converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/ebook-convert")),
    )
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))

    result = to_epub(tmp_path / "book.pdf", tmp_path / "book.epub")

    assert result.engine == "calibre"
    assert calls[0][0][0] == "/ebook-convert"


def test_missing_requested_tool_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak jawnie wybranego narzędzia daje ConverterNotFoundError."""
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _missing_tool("pandoc")))

    with pytest.raises(ConverterNotFoundError, match="Pandoc"):
        to_epub(tmp_path / "book.md", tmp_path / "book.epub", engine="pandoc")


def test_non_zero_exit_raises_conversion_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kod wyjścia różny od zera daje ConversionError z fragmentem logu."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(converter.Tools, "pandoc", staticmethod(lambda: _tool("pandoc", "/pandoc")))
    monkeypatch.setattr(
        converter.subprocess,
        "run",
        _fake_run(calls, stdout="stdout log", stderr="stderr failure", returncode=7),
    )

    with pytest.raises(ConversionError, match="stderr failure"):
        to_epub(tmp_path / "book.md", tmp_path / "book.epub", engine="pandoc")


def test_cli_convert_subcommand(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """CLI przekazuje SOURCE, TARGET i engine do warstwy konwersji."""
    seen: dict[str, object] = {}

    def fake_to_epub(
        source: Path,
        target: Path,
        options: ConvertOptions | None = None,
        engine: str = "auto",
    ) -> ConversionResult:
        seen.update({"source": source, "target": target, "options": options, "engine": engine})
        return ConversionResult(True, target, "cli log", "pandoc")

    monkeypatch.setattr(cli_convert, "to_epub", fake_to_epub)
    source = tmp_path / "book.md"
    target = tmp_path / "book.epub"

    exit_code = main(["convert", str(source), str(target), "--engine", "pandoc"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen == {"source": source, "target": target, "options": None, "engine": "pandoc"}
    assert "cli log" in captured.out
    assert f"Utworzono EPUB: {target}" in captured.out
