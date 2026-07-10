"""Testy silnika pdf2md (PDF → Markdown → EPUB).

Zewnętrzne binaria są mockowane — nie uruchamiamy pdf2md ani Pandoc w CI.
Test integracyjny (marker ``integration``) jest pomijany, gdy w ``PATH`` nie ma
``pdf2md``.
"""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from epubforge.converters import ConvertOptions, to_epub, to_epub_streaming
from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.core.streaming import ProcessResult

converter = importlib.import_module("epubforge.converters.to_epub")
pdf2md_module = importlib.import_module("epubforge.converters.pdf2md")


def _tool(name: str, path: str) -> Tool:
    """Buduje dostępne narzędzie do testów."""
    return Tool(name=name, path=Path(path), version=f"{name} 1.0", available=True)


def _missing_tool(name: str) -> Tool:
    """Buduje niedostępne narzędzie do testów."""
    return Tool(name=name, path=None, version="", available=False)


def _path_arg(path: str) -> str:
    """Zwraca ścieżkę tak, jak trafi do argumentów subprocess na danej platformie."""
    return str(Path(path))


def _fake_run(
    calls: list[list[str]],
    *,
    create_markdown: bool = True,
    stdout: str = "ok",
    stderr: str = "",
    returncode: int = 0,
) -> Callable[..., SimpleNamespace]:
    """Mock ``subprocess.run``; przy komendzie pdf2md może utworzyć plik Markdown."""

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if create_markdown and "convert" in command:
            out = Path(command[command.index("-o") + 1])
            out.write_text("# Tytuł\n\n![](book_images/rys.png)\n", encoding="utf-8")
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return run


def _use_pdf2md(
    monkeypatch: pytest.MonkeyPatch, *, pdf2md: bool = True, pandoc: bool = True
) -> None:
    """Podmienia detektory Tools dla pdf2md i Pandoc."""
    monkeypatch.setattr(
        converter.Tools,
        "pdf2md",
        staticmethod(lambda: _tool("pdf2md", "/bin/pdf2md") if pdf2md else _missing_tool("pdf2md")),
    )
    monkeypatch.setattr(
        converter.Tools,
        "pandoc",
        staticmethod(lambda: _tool("pandoc", "/bin/pandoc") if pandoc else _missing_tool("pandoc")),
    )


def _make_pdf(tmp_path: Path) -> Path:
    """Tworzy atrapę pliku PDF (zawartość nieistotna dla mocków)."""
    source = tmp_path / "book.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    return source


# ── Budowa łańcucha komend ────────────────────────────────────────────────────


def test_pdf2md_builds_two_step_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """engine=pdf2md buduje pdf2md convert → md, a potem Pandoc md → EPUB."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch)
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))
    source = _make_pdf(tmp_path)
    target = tmp_path / "book.epub"

    result = to_epub(source, target, engine="pdf2md")

    assert result.engine == "pdf2md"
    assert len(calls) == 2
    step_md = calls[0]
    assert step_md[0] == _path_arg("/bin/pdf2md")
    assert step_md[1] == "convert"
    assert step_md[2] == str(source)
    assert step_md[3] == "-o"
    assert step_md[-1] == "--extract-images"
    md_path = step_md[4]
    assert md_path.endswith("book.md")


def test_pdf2md_pandoc_step_gets_resource_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drugi krok to Pandoc na Markdownie z ``--resource-path`` na katalog obrazów."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch)
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))
    source = _make_pdf(tmp_path)
    target = tmp_path / "book.epub"

    to_epub(source, target, ConvertOptions(epub_version="epub3"), engine="pdf2md")

    md_path = calls[0][4]
    step_epub = calls[1]
    assert step_epub[0] == _path_arg("/bin/pandoc")
    assert step_epub[1] == md_path
    assert "--output" in step_epub and str(target) in step_epub
    assert "--resource-path" in step_epub
    resource_dir = step_epub[step_epub.index("--resource-path") + 1]
    # Katalog zasobów = katalog pośredniego Markdownu (tam leży book_images/).
    assert Path(md_path).parent == Path(resource_dir)


# ── Rozstrzyganie silnika (auto) ──────────────────────────────────────────────


def test_auto_pdf_prefers_pdf2md_when_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto dla PDF wybiera pdf2md, gdy jest wykryty."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch)
    monkeypatch.setattr(
        converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))

    result = to_epub(_make_pdf(tmp_path), tmp_path / "book.epub")

    assert result.engine == "pdf2md"
    assert calls[0][1] == "convert"


def test_auto_pdf_falls_back_to_calibre_without_pdf2md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bez pdf2md auto dla PDF działa identycznie jak wcześniej — jeden krok Calibre."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch, pdf2md=False)
    monkeypatch.setattr(
        converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls))

    result = to_epub(_make_pdf(tmp_path), tmp_path / "book.epub")

    assert result.engine == "calibre"
    assert len(calls) == 1  # brak łańcucha md → jedno wywołanie ebook-convert
    assert calls[0][0] == _path_arg("/bin/ebook-convert")


# ── Błędy ─────────────────────────────────────────────────────────────────────


def test_pdf2md_rejects_non_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """engine=pdf2md dla nie-PDF → ConversionError (silnik obsługuje tylko PDF)."""
    _use_pdf2md(monkeypatch)
    with pytest.raises(ConversionError, match="wyłącznie pliki PDF"):
        to_epub(tmp_path / "book.md", tmp_path / "book.epub", engine="pdf2md")


def test_pdf2md_missing_tool_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak pdf2md przy jawnym engine=pdf2md → ConverterNotFoundError."""
    _use_pdf2md(monkeypatch, pdf2md=False)
    with pytest.raises(ConverterNotFoundError, match="pdf2md"):
        to_epub(_make_pdf(tmp_path), tmp_path / "book.epub", engine="pdf2md")


def test_pdf2md_nonzero_exit_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Niezerowy kod wyjścia pdf2md → ConversionError (log fragment w komunikacie)."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch)
    monkeypatch.setattr(
        converter.subprocess,
        "run",
        _fake_run(calls, create_markdown=False, stderr="blad wewnetrzny silnika", returncode=3),
    )
    with pytest.raises(ConversionError, match="pdf2md"):
        to_epub(_make_pdf(tmp_path), tmp_path / "book.epub", engine="pdf2md")
    assert len(calls) == 1  # Pandoc nie ruszył po błędzie pdf2md


def test_pdf2md_without_markdown_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pdf2md kończy się OK, ale nie tworzy Markdownu (brak silnika) → ConversionError."""
    calls: list[list[str]] = []
    _use_pdf2md(monkeypatch)
    monkeypatch.setattr(converter.subprocess, "run", _fake_run(calls, create_markdown=False))
    with pytest.raises(ConversionError, match="Markdown"):
        to_epub(_make_pdf(tmp_path), tmp_path / "book.epub", engine="pdf2md")


# ── Wariant strumieniowy ──────────────────────────────────────────────────────


def test_pdf2md_streaming_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Strumieniowy pdf2md przechodzi oba kroki i zwraca sukces."""
    _use_pdf2md(monkeypatch)
    commands: list[list[str]] = []

    def fake_stream(
        command: list[str], on_line: object, on_progress: object, should_cancel: object
    ) -> ProcessResult:
        commands.append(command)
        if "convert" in command:
            Path(command[command.index("-o") + 1]).write_text("# md\n", encoding="utf-8")
        return ProcessResult(returncode=0)

    monkeypatch.setattr(pdf2md_module, "run_command_streaming", fake_stream)

    result = to_epub_streaming(
        _make_pdf(tmp_path), tmp_path / "book.epub", on_line=lambda _t, _l: None
    )

    assert result.success is True
    assert result.engine == "pdf2md"
    assert len(commands) == 2


def test_pdf2md_streaming_cancel_first_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowanie na kroku pdf2md kończy się cancelled bez uruchamiania Pandoca."""
    _use_pdf2md(monkeypatch)
    commands: list[list[str]] = []

    def fake_stream(
        command: list[str], on_line: object, on_progress: object, should_cancel: object
    ) -> ProcessResult:
        commands.append(command)
        return ProcessResult(returncode=-1, cancelled=True)

    monkeypatch.setattr(pdf2md_module, "run_command_streaming", fake_stream)

    result = to_epub_streaming(
        _make_pdf(tmp_path), tmp_path / "book.epub", on_line=lambda _t, _l: None
    )

    assert result.cancelled is True
    assert result.success is False
    assert result.engine == "pdf2md"
    assert len(commands) == 1  # Pandoc nie ruszył


# ── Test integracyjny (pomijany bez pdf2md w PATH) ────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("pdf2md") is None, reason="pdf2md niedostępny w PATH")
def test_pdf2md_integration_roundtrip(tmp_path: Path) -> None:
    """Realna konwersja PDF → EPUB (wymaga pdf2md + silnika + Pandoc)."""
    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc niedostępny w PATH")
    from PIL import Image

    source = tmp_path / "book.pdf"
    Image.new("RGB", (300, 400), "white").save(source, "PDF")
    target = tmp_path / "book.epub"

    result = to_epub(source, target, engine="pdf2md")

    assert result.success is True
    assert target.is_file()
    assert target.stat().st_size > 0
