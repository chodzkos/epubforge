"""Konwersja popularnych formatów wejściowych do EPUB.

Moduł jest cienką, testowalną warstwą nad Pandoc i Calibre ``ebook-convert``:
buduje polecenie, uruchamia subprocess z przechwyceniem logów i zwraca wynik
bez wykonywania walidacji samego EPUB-a.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from epubforge.converters._streaming import ProgressSink, run_command_streaming
from epubforge.converters.kindle_drm import has_kindle_drm
from epubforge.core.detection import Tool, Tools
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.core.metadata import Metadata
from epubforge.core.streaming import CancelCheck, LineSink
from epubforge.i18n import _

EpubVersion = Literal["epub2", "epub3"]
Engine = Literal["pandoc", "calibre", "auto"]

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_PDF_EXTENSIONS = {".pdf"}
# Formaty Kindle — wyłącznie Calibre (Pandoc ich nie czyta), z detekcją DRM.
KINDLE_INPUT_EXTENSIONS = {".mobi", ".azw3", ".azw", ".prc"}

# Rozszerzenia wejściowe obsługiwane przez konwersję do EPUB (źródło prawdy dla UI/CLI).
SUPPORTED_INPUT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".docx",
        ".odt",
        ".rtf",
        ".html",
        ".htm",
        ".pdf",
        ".fb2",
        ".lit",
        ".mobi",
        ".azw3",
        ".azw",
        ".prc",
    }
)


def _drm_error() -> ConversionError:
    """Buduje uprzejmy błąd dla plików zabezpieczonych DRM."""
    return ConversionError(
        _("Plik jest zabezpieczony DRM — konwersja niemożliwa. EpubForge nie usuwa zabezpieczeń.")
    )


@dataclass
class ConvertOptions:
    """Opcje konwersji wejścia do EPUB.

    Attributes:
        epub_version: docelowa wersja EPUB dla silników, które ją wspierają.
        metadata: opcjonalne metadane przekazywane do konwertera.
        cover_image: opcjonalna okładka.
        toc: czy prosić silnik o wygenerowanie spisu treści.
        toc_depth: maksymalna głębokość spisu treści.
        css: opcjonalny plik CSS do dołączenia przez Pandoc.
    """

    epub_version: EpubVersion = "epub3"
    metadata: Metadata | None = None
    cover_image: Path | None = None
    toc: bool = True
    toc_depth: int = 3
    css: Path | None = None


@dataclass(frozen=True)
class ConversionResult:
    """Wynik konwersji.

    Attributes:
        success: ``True`` dla udanej konwersji; błędy techniczne są wyjątkami,
            ale anulowanie (``cancelled=True``) zwraca ``success=False``.
        output_path: ścieżka do utworzonego EPUB-a (przy anulowaniu może nie istnieć).
        log: połączone stdout/stderr procesu.
        engine: faktycznie użyty silnik (``pandoc`` albo ``calibre``).
        cancelled: ``True`` gdy konwersję przerwano na żądanie użytkownika.
    """

    success: bool
    output_path: Path
    log: str
    engine: str
    cancelled: bool = False


def to_epub(
    source: Path,
    target: Path,
    options: ConvertOptions | None = None,
    engine: Engine = "auto",
) -> ConversionResult:
    """Konwertuje plik wejściowy do EPUB przez Pandoc albo Calibre.

    Args:
        source: plik wejściowy (TXT, Markdown, DOCX, HTML, PDF itd.).
        target: docelowa ścieżka EPUB.
        options: opcje konwersji; ``None`` oznacza domyślne.
        engine: ``pandoc``, ``calibre`` albo automatyczny wybór.

    Raises:
        ConverterNotFoundError: gdy wymagane narzędzie nie jest dostępne.
        ConversionError: gdy proces konwersji zwróci kod różny od zera.

    Returns:
        :class:`ConversionResult` z logiem procesu i faktycznie użytym silnikiem.
    """
    actual_options = options if options is not None else ConvertOptions()
    # DRM sprawdzamy PRZED doborem silnika i uruchomieniem Calibre.
    if source.suffix.lower() in KINDLE_INPUT_EXTENSIONS and has_kindle_drm(source):
        raise _drm_error()
    actual_engine, tool = _resolve_engine(source, engine)
    command = _build_command(actual_engine, tool, source, target, actual_options)
    log = _run_converter(command, actual_engine)
    return ConversionResult(success=True, output_path=target, log=log, engine=actual_engine)


def to_epub_streaming(
    source: Path,
    target: Path,
    options: ConvertOptions | None = None,
    engine: Engine = "auto",
    *,
    on_line: LineSink,
    on_progress: ProgressSink | None = None,
    should_cancel: CancelCheck | None = None,
) -> ConversionResult:
    """Strumieniowy wariant :func:`to_epub` — log na żywo, postęp i anulowanie.

    Buduje tę samą komendę co :func:`to_epub`, ale uruchamia ją strumieniowo:
    linie logu idą do ``on_line`` na bieżąco, procenty Calibre do ``on_progress``,
    a ``should_cancel`` pozwala przerwać proces potomny.

    Returns:
        :class:`ConversionResult`; przy anulowaniu ``success=False`` i
        ``cancelled=True`` (plik docelowy może nie powstać).
    """
    actual_options = options if options is not None else ConvertOptions()
    if source.suffix.lower() in KINDLE_INPUT_EXTENSIONS and has_kindle_drm(source):
        raise _drm_error()
    actual_engine, tool = _resolve_engine(source, engine)
    command = _build_command(actual_engine, tool, source, target, actual_options)

    result = run_command_streaming(command, on_line, on_progress, should_cancel)
    if result.cancelled:
        return ConversionResult(
            success=False, output_path=target, log="", engine=actual_engine, cancelled=True
        )
    if result.returncode != 0:
        raise ConversionError(
            _("Konwersja przez {engine} nie powiodła się (kod wyjścia {code}).").format(
                engine=actual_engine, code=result.returncode
            )
        )
    return ConversionResult(success=True, output_path=target, log="", engine=actual_engine)


def _resolve_engine(source: Path, engine: Engine) -> tuple[Literal["pandoc", "calibre"], Tool]:
    """Wybiera i weryfikuje dostępność silnika konwersji."""
    suffix = source.suffix.lower()
    if engine == "pandoc":
        if suffix in KINDLE_INPUT_EXTENSIONS:
            raise ConversionError(
                _("Pandoc nie obsługuje formatów Kindle (MOBI/AZW3/AZW/PRC) — użyj Calibre.")
            )
        return "pandoc", _require_pandoc()
    if engine == "calibre":
        return "calibre", _require_calibre()

    # Formaty Kindle i PDF wymuszają Calibre (Pandoc ich nie czyta).
    if suffix in _PDF_EXTENSIONS or suffix in KINDLE_INPUT_EXTENSIONS:
        return "calibre", _require_calibre()

    pandoc = Tools.pandoc()
    if pandoc.available and pandoc.path is not None:
        return "pandoc", pandoc

    calibre = Tools.calibre_ebook_convert()
    if calibre.available and calibre.path is not None:
        return "calibre", calibre

    raise ConverterNotFoundError(
        "Nie znaleziono Pandoc ani Calibre ebook-convert. "
        "Zainstaluj Pandoc lub Calibre albo skonfiguruj ścieżkę narzędzia."
    )


def _require_pandoc() -> Tool:
    """Zwraca Pandoc albo zgłasza czytelny błąd."""
    tool = Tools.pandoc()
    if tool.available and tool.path is not None:
        return tool
    raise ConverterNotFoundError(
        "Nie znaleziono Pandoc. Zainstaluj Pandoc albo użyj engine='calibre'."
    )


def _require_calibre() -> Tool:
    """Zwraca Calibre ``ebook-convert`` albo zgłasza czytelny błąd."""
    tool = Tools.calibre_ebook_convert()
    if tool.available and tool.path is not None:
        return tool
    raise ConverterNotFoundError(
        "Nie znaleziono Calibre ebook-convert. Zainstaluj Calibre albo użyj engine='pandoc'."
    )


def _build_command(
    engine: Literal["pandoc", "calibre"],
    tool: Tool,
    source: Path,
    target: Path,
    options: ConvertOptions,
) -> list[str]:
    """Buduje komendę dla wybranego silnika."""
    if tool.path is None:
        raise ConverterNotFoundError(f"Narzędzie {tool.name} nie ma ustawionej ścieżki.")
    if engine == "pandoc":
        return _build_pandoc_command(tool.path, source, target, options)
    return _build_calibre_command(tool.path, source, target, options)


def _build_pandoc_command(
    executable: Path,
    source: Path,
    target: Path,
    options: ConvertOptions,
) -> list[str]:
    """Buduje polecenie Pandoc."""
    command = [
        str(executable),
        str(source),
        "--to",
        options.epub_version,
        "--output",
        str(target),
    ]
    if options.toc:
        command.extend(["--toc", "--toc-depth", str(options.toc_depth)])
    if options.css is not None:
        command.extend(["--css", str(options.css)])
    if options.cover_image is not None:
        command.extend(["--epub-cover-image", str(options.cover_image)])
    command.extend(_pandoc_metadata_args(options.metadata))
    return command


def _build_calibre_command(
    executable: Path,
    source: Path,
    target: Path,
    options: ConvertOptions,
) -> list[str]:
    """Buduje polecenie Calibre ``ebook-convert``."""
    command = [
        str(executable),
        str(source),
        str(target),
        "--epub-version",
        options.epub_version.removeprefix("epub"),
    ]
    if options.cover_image is not None:
        command.extend(["--cover", str(options.cover_image)])
    command.extend(_calibre_metadata_args(options.metadata))
    return command


def _pandoc_metadata_args(metadata: Metadata | None) -> list[str]:
    """Mapuje metadane Dublin Core na argumenty ``pandoc --metadata``."""
    if metadata is None:
        return []

    args: list[str] = []
    values: list[tuple[str, str]] = [
        ("title", metadata.title),
        ("lang", metadata.language),
        ("identifier", metadata.identifier),
        ("publisher", metadata.publisher),
        ("date", metadata.date),
        ("description", metadata.description),
    ]
    for key, value in values:
        if value:
            args.extend(["--metadata", f"{key}={value}"])
    for creator in metadata.creators:
        if creator:
            args.extend(["--metadata", f"author={creator}"])
    for subject in metadata.subjects:
        if subject:
            args.extend(["--metadata", f"subject={subject}"])
    return args


def _calibre_metadata_args(metadata: Metadata | None) -> list[str]:
    """Mapuje metadane Dublin Core na argumenty ``ebook-convert``."""
    if metadata is None:
        return []

    args: list[str] = []
    if metadata.title:
        args.extend(["--title", metadata.title])
    if metadata.creators:
        args.extend(["--authors", " & ".join(metadata.creators)])
    if metadata.language:
        args.extend(["--language", metadata.language])
    if metadata.publisher:
        args.extend(["--publisher", metadata.publisher])
    if metadata.date:
        args.extend(["--pubdate", metadata.date])
    if metadata.description:
        args.extend(["--comments", metadata.description])
    if metadata.subjects:
        args.extend(["--tags", ",".join(metadata.subjects)])
    return args


def _run_converter(command: list[str], engine: Literal["pandoc", "calibre"]) -> str:
    """Uruchamia proces konwersji i zwraca połączony log stdout/stderr."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConverterNotFoundError(
            f"Nie udało się uruchomić konwertera {engine}: {command[0]}"
        ) from exc
    except OSError as exc:
        raise ConversionError(f"Nie udało się uruchomić konwertera {engine}: {exc}") from exc

    log = _combined_log(result.stdout, result.stderr)
    if result.returncode != 0:
        if "drm" in log.lower():  # Calibre sygnalizuje DRM w stderr
            raise _drm_error()
        raise ConversionError(
            f"Konwersja przez {engine} nie powiodła się "
            f"(kod wyjścia {result.returncode}): {_log_fragment(log)}"
        )
    return log


def _combined_log(stdout: str | None, stderr: str | None) -> str:
    """Łączy stdout i stderr, zachowując czytelny separator tylko gdy potrzebny."""
    parts = [part.strip() for part in (stdout, stderr) if part]
    return "\n".join(parts)


def _log_fragment(log: str, limit: int = 1000) -> str:
    """Zwraca końcowy fragment logu do komunikatu błędu."""
    stripped = log.strip()
    if not stripped:
        return "brak logu procesu"
    if len(stripped) <= limit:
        return stripped
    return f"...{stripped[-limit:]}"
