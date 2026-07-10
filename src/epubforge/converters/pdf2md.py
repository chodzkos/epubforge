"""Silnik konwersji PDF → EPUB przez pdf2md (PDF → Markdown → Pandoc).

Dwuetapowa ścieżka: najpierw ``pdf2md convert`` zamienia PDF na Markdown (z
wyciąganiem obrazów do ``book_images/``), potem istniejąca ścieżka Pandoc składa
Markdown w EPUB z ``--resource-path`` wskazującym katalog tymczasowy, żeby obrazy
osadziły się w książce. Cały pośredni materiał żyje w ``TemporaryDirectory``.

Moduł importuje prymitywy z :mod:`epubforge.converters.to_epub` (builder Pandoc,
runner, dataclasses). Zależność jest jednokierunkowa: ``to_epub`` woła tutejsze
funkcje leniwie, więc nie ma cyklu importów.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from epubforge.converters._streaming import ProgressSink, run_command_streaming
from epubforge.converters.to_epub import (
    ConversionResult,
    ConvertOptions,
    _build_pandoc_command,
    _combined_log,
    _require_pandoc,
    _run_converter,
)
from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.core.streaming import CancelCheck, LineSink, ProcessResult
from epubforge.i18n import _

# Stała nazwa pośredniego Markdownu (stem „book" → obrazy w „book_images/",
# które Pandoc rozwiązuje przez ``--resource-path`` katalogu tymczasowego).
_MD_NAME = "book.md"


def _markdown_command(source: Path, md_target: Path, tool: Tool) -> list[str]:
    """Buduje polecenie ``pdf2md convert`` (PDF → Markdown + wyciąganie obrazów)."""
    if tool.path is None:
        raise ConverterNotFoundError("Narzędzie pdf2md nie ma ustawionej ścieżki.")
    return [str(tool.path), "convert", str(source), "-o", str(md_target), "--extract-images"]


def _pandoc_epub_command(
    md_source: Path, target: Path, options: ConvertOptions, resource_dir: Path
) -> list[str]:
    """Buduje polecenie Pandoc md → EPUB z ``--resource-path`` na katalog z obrazami."""
    pandoc = _require_pandoc()
    if pandoc.path is None:
        raise ConverterNotFoundError("Nie znaleziono Pandoc do złożenia EPUB z Markdownu pdf2md.")
    command = _build_pandoc_command(pandoc.path, md_source, target, options)
    # Referencje obrazów w md są względne (``book_images/…``); Pandoc musi znać
    # katalog bazowy, żeby je odnaleźć i osadzić w EPUB-ie.
    command.extend(["--resource-path", str(resource_dir)])
    return command


def _require_markdown_output(md_target: Path) -> None:
    """Sprawdza, że pdf2md rzeczywiście utworzył Markdown (inaczej brak silnika)."""
    if not md_target.is_file():
        raise ConversionError(
            _(
                "pdf2md nie utworzył pliku Markdown — sprawdź, czy zainstalowano silnik "
                "konwersji pdf2md (np. pymupdf4llm)."
            )
        )


def convert_pdf2md(source: Path, target: Path, options: ConvertOptions, tool: Tool) -> str:
    """Konwertuje PDF przez pdf2md → Markdown → Pandoc EPUB (blokująco). Zwraca log."""
    with tempfile.TemporaryDirectory(prefix="epubforge-pdf2md-") as tmp:
        tmpdir = Path(tmp)
        md_target = tmpdir / _MD_NAME
        log_md = _run_converter(_markdown_command(source, md_target, tool), "pdf2md")
        _require_markdown_output(md_target)
        log_epub = _run_converter(
            _pandoc_epub_command(md_target, target, options, tmpdir), "pandoc"
        )
    return _combined_log(log_md, log_epub)


def _check_stream_step(result: ProcessResult, engine: str) -> bool:
    """Zwraca ``True`` przy anulowaniu; przy kodzie ≠ 0 zgłasza ConversionError."""
    if result.cancelled:
        return True
    if result.returncode != 0:
        raise ConversionError(
            _("Konwersja przez {engine} nie powiodła się (kod wyjścia {code}).").format(
                engine=engine, code=result.returncode
            )
        )
    return False


def convert_pdf2md_streaming(
    source: Path,
    target: Path,
    options: ConvertOptions,
    tool: Tool,
    *,
    on_line: LineSink,
    on_progress: ProgressSink | None,
    should_cancel: CancelCheck | None,
) -> ConversionResult:
    """Strumieniowy wariant :func:`convert_pdf2md` — log na żywo i anulowanie."""
    cancelled = ConversionResult(
        success=False, output_path=target, log="", engine="pdf2md", cancelled=True
    )
    with tempfile.TemporaryDirectory(prefix="epubforge-pdf2md-") as tmp:
        tmpdir = Path(tmp)
        md_target = tmpdir / _MD_NAME
        step_md = run_command_streaming(
            _markdown_command(source, md_target, tool), on_line, on_progress, should_cancel
        )
        if _check_stream_step(step_md, "pdf2md"):
            return cancelled
        _require_markdown_output(md_target)
        step_epub = run_command_streaming(
            _pandoc_epub_command(md_target, target, options, tmpdir),
            on_line,
            on_progress,
            should_cancel,
        )
        if _check_stream_step(step_epub, "pandoc"):
            return cancelled
    return ConversionResult(success=True, output_path=target, log="", engine="pdf2md")
