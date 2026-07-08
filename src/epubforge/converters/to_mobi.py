"""Konwersja EPUB do formatów Kindle MOBI/AZW3.

Główny i zalecany silnik to Calibre ``ebook-convert`` (nowoczesny, aktywnie
rozwijany). ``kindlegen`` jest obsługiwany jako opcjonalny, **wycofany** silnik
Amazona (utknął na 2.9) — wciąż produkuje poprawne MOBI, ale nie jest rozwijany.

``kindlegen`` przyjmuje jedynie nazwę pliku wyjściowego (bez ścieżki) i tworzy go
obok pliku źródłowego — dlatego wynik jest po konwersji przenoszony do celu,
analogicznie do obsługi Kindle Previewer w :mod:`epubforge.converters.to_kfx`.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from epubforge.converters.to_epub import ConversionResult
from epubforge.core import Epub
from epubforge.core.detection import Tool, Tools
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.fixers import CssFixOptions, fix_css

MobiFormat = Literal["mobi", "azw3"]
MobiEngine = Literal["calibre", "kindlegen", "auto"]

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_KINDLEGEN_NOTE = (
    "NOTE: kindlegen is officially discontinued by Amazon (stuck at 2.9). "
    "Calibre ebook-convert is the recommended MOBI/AZW3 engine."
)


@dataclass
class MobiOptions:
    """Opcje konwersji EPUB do MOBI/AZW3.

    Attributes:
        fmt: docelowy format (``mobi`` albo ``azw3``).
        engine: ``calibre`` (zalecany), ``kindlegen`` (wycofany) lub ``auto``
            (Calibre jeśli dostępny, w przeciwnym razie kindlegen).
        fix_epub_first: czy przed konwersją uruchomić podstawowy CSS fixer.
            Fixer działa na KOPII źródła w katalogu tymczasowym, więc wejściowy
            plik EPUB użytkownika NIE jest modyfikowany (i nie powstaje ``.bak``).
    """

    fmt: MobiFormat = "mobi"
    engine: MobiEngine = "calibre"
    fix_epub_first: bool = True


def to_mobi(
    source: Path,
    target: Path,
    options: MobiOptions | None = None,
) -> ConversionResult:
    """Konwertuje EPUB do MOBI/AZW3 przez Calibre albo kindlegen.

    Args:
        source: wejściowy plik EPUB.
        target: docelowa ścieżka pliku (np. ``out/book.mobi``).
        options: opcje konwersji; ``None`` oznacza domyślne (MOBI, Calibre).

    Raises:
        ConverterNotFoundError: gdy wymagany silnik nie jest dostępny.
        ConversionError: gdy proces zawiedzie lub kindlegen nie utworzy pliku.

    Returns:
        :class:`ConversionResult` ze ścieżką wyniku, logiem i użytym silnikiem.
    """
    actual_options = options if options is not None else MobiOptions()
    source = Path(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    with contextlib.ExitStack() as stack:
        conv_source = source
        if actual_options.fix_epub_first:
            conv_source = stack.enter_context(_fix_epub(source))

        engine, tool = _resolve_engine(actual_options.engine)
        if engine == "calibre":
            log = _convert_with_calibre(tool, conv_source, target)
        else:
            log = _convert_with_kindlegen(tool, conv_source, target)
    return ConversionResult(success=True, output_path=target, log=log, engine=engine)


@contextlib.contextmanager
def _fix_epub(source: Path) -> Iterator[Path]:
    """Uruchamia CSS fixer na KOPII źródła i udostępnia ją do konwersji.

    CSS fixer utrwala zmiany przez :meth:`Epub.save`, które bez argumentu
    NADPISUJE otwarty plik i tworzy obok kopię ``.bak``. Dlatego kopiujemy EPUB
    do katalogu tymczasowego i poprawiamy kopię — wejściowy plik użytkownika
    pozostaje nietknięty. Katalog tymczasowy (wraz z ``.bak`` kopii) jest usuwany
    po wyjściu z kontekstu, czyli już po zakończeniu konwersji.

    Yields:
        Ścieżka do poprawionej kopii EPUB, której należy użyć jako źródła konwersji.
    """
    with tempfile.TemporaryDirectory(prefix="epubforge-fix-") as tmp:
        copy = Path(tmp) / source.name
        shutil.copy2(source, copy)
        with Epub(copy) as epub:
            fix_css(epub, CssFixOptions())
            epub.save()
        yield copy


def _resolve_engine(engine: MobiEngine) -> tuple[Literal["calibre", "kindlegen"], Tool]:
    """Wybiera i weryfikuje silnik konwersji do MOBI/AZW3."""
    if engine == "calibre":
        return "calibre", _require_calibre()
    if engine == "kindlegen":
        return "kindlegen", _require_kindlegen()

    calibre = Tools.calibre_ebook_convert()
    if calibre.available and calibre.path is not None:
        return "calibre", calibre
    return "kindlegen", _require_kindlegen()


def _require_calibre() -> Tool:
    """Zwraca Calibre ``ebook-convert`` albo zgłasza czytelny błąd."""
    tool = Tools.calibre_ebook_convert()
    if tool.available and tool.path is not None:
        return tool
    raise ConverterNotFoundError(
        "Nie znaleziono Calibre ebook-convert. Zainstaluj Calibre albo użyj engine='kindlegen'."
    )


def _require_kindlegen() -> Tool:
    """Zwraca ``kindlegen`` albo zgłasza czytelny błąd."""
    tool = Tools.kindlegen()
    if tool.available and tool.path is not None:
        return tool
    raise ConverterNotFoundError(
        "Nie znaleziono kindlegen (wycofany przez Amazon). Użyj engine='calibre'."
    )


def _convert_with_calibre(tool: Tool, source: Path, target: Path) -> str:
    """Konwertuje przez Calibre ``ebook-convert`` (format z rozszerzenia celu)."""
    if tool.path is None:
        raise ConverterNotFoundError("Calibre ebook-convert nie ma ustawionej ścieżki.")
    command = [str(tool.path), str(source), str(target)]
    returncode, log = _run(command, "calibre")
    if returncode != 0:
        raise ConversionError(
            f"Konwersja do {target.suffix.lstrip('.')} przez calibre nie powiodła się "
            f"(kod wyjścia {returncode}): {_log_fragment(log)}"
        )
    return log


def _convert_with_kindlegen(tool: Tool, source: Path, target: Path) -> str:
    """Konwertuje przez kindlegen i przenosi wynik do celu.

    ``kindlegen`` zwraca kod 1 przy samych ostrzeżeniach (plik i tak powstaje),
    dlatego o powodzeniu decyduje istnienie pliku wynikowego, nie kod wyjścia.
    """
    if tool.path is None:
        raise ConverterNotFoundError("kindlegen nie ma ustawionej ścieżki.")

    out_name = target.name
    command = [str(tool.path), str(source), "-o", out_name]
    _, log = _run(command, "kindlegen")

    produced = source.parent / out_name
    if not produced.is_file():
        found = sorted(source.parent.rglob(out_name))
        if not found:
            raise ConversionError(f"kindlegen nie utworzył pliku {out_name}: {_log_fragment(log)}")
        produced = found[0]

    if produced.resolve() != target.resolve():
        shutil.move(str(produced), str(target))
    return _combined_log(_KINDLEGEN_NOTE, log)


def _run(command: list[str], engine: Literal["calibre", "kindlegen"]) -> tuple[int, str]:
    """Uruchamia proces i zwraca ``(kod_wyjścia, log)``; błędy startu jako wyjątki."""
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
    return result.returncode, _combined_log(result.stdout, result.stderr)


def _combined_log(*parts: str | None) -> str:
    """Łączy niepuste fragmenty logu."""
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _log_fragment(log: str, limit: int = 1000) -> str:
    """Zwraca końcowy fragment logu do komunikatu błędu."""
    stripped = log.strip()
    if not stripped:
        return "brak logu procesu"
    if len(stripped) <= limit:
        return stripped
    return f"...{stripped[-limit:]}"
