"""Konwersja EPUB do KFX.

Główny silnik to Calibre ``ebook-convert`` z wtyczką KFX Output. Kindle
Previewer 3 jest obsługiwany jako fallback eksperymentalny, ponieważ bywa
bardziej wrażliwy na formatowanie EPUB.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from epubforge.converters.to_epub import ConversionResult
from epubforge.core import Epub
from epubforge.core.detection import Tool, Tools
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.fixers import CssFixOptions, fix_css

KfxEngine = Literal["calibre", "kindle-previewer", "auto"]

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_KP3_WARNING = (
    "WARNING: Kindle Previewer 3 engine is EXPERIMENTAL. "
    "Calibre with KFX Output is the primary and recommended KFX engine."
)


@dataclass
class KfxOptions:
    """Opcje konwersji EPUB do KFX.

    Attributes:
        engine: ``auto`` wybiera Calibre, jeśli wykryto wtyczkę KFX Output;
            w przeciwnym razie używa eksperymentalnego Kindle Previewer 3.
        fix_epub_first: czy przed konwersją uruchomić podstawowy CSS fixer.
    """

    engine: KfxEngine = "auto"
    fix_epub_first: bool = True


def to_kfx(
    source: Path,
    target_dir: Path,
    options: KfxOptions | None = None,
) -> ConversionResult:
    """Konwertuje EPUB do KFX i zwraca ścieżkę utworzonego pliku.

    Args:
        source: wejściowy plik EPUB.
        target_dir: katalog docelowy, w którym powstanie ``source.stem + ".kfx"``.
        options: opcje konwersji; ``None`` oznacza domyślne.

    Raises:
        ConverterNotFoundError: gdy wymagany silnik lub wtyczka są niedostępne.
        ConversionError: gdy subprocess zwróci błąd lub KP3 nie utworzy pliku KFX.
    """
    actual_options = options if options is not None else KfxOptions()
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}.kfx"

    if actual_options.fix_epub_first:
        _fix_epub(source)

    engine, tool = _resolve_engine(actual_options.engine)
    if engine == "calibre":
        log = _convert_with_calibre(tool, source, target)
    else:
        log = _convert_with_kindle_previewer(tool, source, target)
    return ConversionResult(success=True, output_path=target, log=log, engine=engine)


def _fix_epub(source: Path) -> None:
    """Uruchamia podstawowy CSS fixer przed konwersją."""
    with Epub(source) as epub:
        fix_css(epub, CssFixOptions())
        epub.save()


def _resolve_engine(engine: KfxEngine) -> tuple[Literal["calibre", "kindle-previewer"], Tool]:
    """Wybiera i weryfikuje silnik KFX."""
    if engine == "calibre":
        return "calibre", _require_calibre_with_kfx()
    if engine == "kindle-previewer":
        return "kindle-previewer", _require_kindle_previewer()

    if Tools.calibre_kfx_plugin():
        return "calibre", _require_calibre_with_kfx()
    return "kindle-previewer", _require_kindle_previewer()


def _require_calibre_with_kfx() -> Tool:
    """Zwraca ``ebook-convert`` i wymaga wtyczki KFX Output."""
    tool = Tools.calibre_ebook_convert()
    if not (tool.available and tool.path is not None):
        raise ConverterNotFoundError("Nie znaleziono Calibre ebook-convert.")
    if not Tools.calibre_kfx_plugin():
        raise ConverterNotFoundError(
            "Nie znaleziono wtyczki Calibre KFX Output. "
            "Zainstaluj wtyczkę albo użyj engine='kindle-previewer' jako experimental."
        )
    return tool


def _require_kindle_previewer() -> Tool:
    """Zwraca Kindle Previewer 3 albo zgłasza czytelny błąd."""
    tool = Tools.kindle_previewer()
    if tool.available and tool.path is not None:
        return tool
    raise ConverterNotFoundError("Nie znaleziono Kindle Previewer 3.")


def _convert_with_calibre(tool: Tool, source: Path, target: Path) -> str:
    """Konwertuje przez Calibre + KFX Output."""
    if tool.path is None:
        raise ConverterNotFoundError("Calibre ebook-convert nie ma ustawionej ścieżki.")
    command = [str(tool.path), str(source), str(target)]
    return _run_converter(command, "calibre")


def _convert_with_kindle_previewer(tool: Tool, source: Path, target: Path) -> str:
    """Konwertuje przez eksperymentalny Kindle Previewer 3 i przenosi plik KFX."""
    if tool.path is None:
        raise ConverterNotFoundError("Kindle Previewer 3 nie ma ustawionej ścieżki.")

    with tempfile.TemporaryDirectory(prefix="epubforge-kp3-") as temp:
        tempdir = Path(temp)
        command = [str(tool.path), "-convert", str(source), "-outdir", str(tempdir)]
        process_log = _run_converter(command, "kindle-previewer")
        found = sorted(tempdir.rglob("*.kfx"))
        if not found:
            raise ConversionError(
                f"Kindle Previewer 3 nie utworzył pliku KFX: {_log_fragment(process_log)}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(found[0]), target)
    return _combined_log(_KP3_WARNING, process_log)


def _run_converter(command: list[str], engine: Literal["calibre", "kindle-previewer"]) -> str:
    """Uruchamia konwerter i zwraca połączony log stdout/stderr."""
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
        raise ConversionError(
            f"Konwersja do KFX przez {engine} nie powiodła się "
            f"(kod wyjścia {result.returncode}): {_log_fragment(log)}"
        )
    return log


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
