"""Subkomenda CLI ``epubforge fix``."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from epubforge.cli._batch import add_batch_arguments, format_dry_run, run_batch
from epubforge.core import Epub, EpubError
from epubforge.fixers import (
    CssFixOptions,
    CssPreset,
    FontSubsetError,
    FontSubsetOptions,
    ImageFixOptions,
    ImageOptimizationError,
    PresetError,
    apply_preset,
    fix_css,
    get_preset,
    optimize_images,
    subset_fonts,
)
from epubforge.i18n import _


@dataclass(frozen=True)
class _FixPayload:
    """Picklowalne opcje pracy dla pojedynczego pliku."""

    options: CssFixOptions
    preset: CssPreset | None
    preset_mode: str
    image_options: ImageFixOptions | None
    font_options: FontSubsetOptions | None
    dry_run: bool
    diff_full: bool


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``fix`` w głównym parserze argparse."""
    parser = subparsers.add_parser("fix", help=_("Normalizuj CSS w EPUB"))
    add_batch_arguments(parser, file_help=_("Pliki EPUB do modyfikacji"))
    parser.add_argument("--remove-colors", action="store_true", help=_("Usuń kolory i tła z CSS"))
    parser.add_argument("--remove-fonts", action="store_true", help=_("Usuń fonty z CSS i EPUB"))
    parser.add_argument(
        "--no-reset",
        dest="inject_reset",
        action="store_false",
        default=True,
        help=_("Nie dodawaj resetu margin/padding"),
    )
    parser.add_argument(
        "--replace-justify",
        action="store_true",
        help=_("Zamień text-align: justify na left"),
    )
    parser.add_argument("--book-margin", type=int, help=_("Dodaj @page margin w px"))
    parser.add_argument(
        "--keep-hyphenation-headers",
        dest="skip_hyphenation_headers",
        action="store_false",
        default=True,
        help=_("Nie dodawaj reguły h1-h3 { hyphens: none }"),
    )
    parser.add_argument(
        "--optimize-images",
        action="store_true",
        help=_("Optymalizuj obrazy JPEG/PNG (skalowanie + rekompresja; wymaga epubforge[images])"),
    )
    parser.add_argument(
        "--max-px",
        type=int,
        default=1200,
        help=_("Maksymalny dłuższy bok obrazu w px (0 = bez skalowania; domyślnie 1200)"),
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=75,
        help=_("Jakość zapisu JPEG 1-95 (domyślnie 75)"),
    )
    parser.add_argument(
        "--grayscale",
        action="store_true",
        help=_("Konwertuj obrazy do skali szarości (pod e-ink)"),
    )
    parser.add_argument(
        "--subset-fonts",
        action="store_true",
        help=_(
            "Przytnij fonty do użytych znaków (wymaga epubforge[fonts]). "
            "UWAGA: część licencji fontów zabrania modyfikacji — sprawdź licencję."
        ),
    )
    parser.add_argument("--preset", help=_("Dołącz preset CSS o podanym ID (zob. presets list)"))
    parser.add_argument(
        "--preset-mode",
        choices=("append", "replace"),
        default="append",
        help=_("Tryb presetu: dołącz obok istniejących arkuszy albo zastąp je"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Pokaż diff zmian bez zapisywania EPUB-a"),
    )
    parser.add_argument(
        "--diff-full",
        action="store_true",
        help=_("Nie skracaj diffów w trybie --dry-run"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia normalizację CSS z argumentów CLI."""
    options = CssFixOptions(
        remove_colors=args.remove_colors,
        remove_fonts=args.remove_fonts,
        inject_reset=args.inject_reset,
        replace_justify="left" if args.replace_justify else "keep",
        inject_book_margin_px=args.book_margin,
        skip_hyphenation_headers=args.skip_hyphenation_headers,
    )
    try:
        preset = get_preset(args.preset) if args.preset else None
    except PresetError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    image_options = (
        ImageFixOptions(
            max_px=args.max_px if args.max_px > 0 else None,
            jpeg_quality=args.jpeg_quality,
            grayscale=args.grayscale,
        )
        if args.optimize_images
        else None
    )

    font_options = FontSubsetOptions() if args.subset_fonts else None

    payload = _FixPayload(
        options=options,
        preset=preset,
        preset_mode=args.preset_mode,
        image_options=image_options,
        font_options=font_options,
        dry_run=args.dry_run,
        diff_full=args.diff_full,
    )
    return run_batch(
        args.files,
        jobs=args.jobs,
        handler=_run_fix_for_path,
        payload=payload,
    )


def _run_fix_for_path(path: Path, raw_payload: object) -> str:
    """Przetwarza jeden EPUB dla batch runnera."""
    payload = cast(_FixPayload, raw_payload)
    try:
        with Epub(path) as epub:
            fix_css(epub, payload.options)
            if payload.preset is not None:
                apply_preset(epub, payload.preset, mode=payload.preset_mode)
            if payload.image_options is not None:
                optimize_images(epub, payload.image_options)
            if payload.font_options is not None:
                subset_fonts(epub, payload.font_options)
            if payload.dry_run:
                return format_dry_run(epub, diff_full=payload.diff_full)
            epub.save()
    except (EpubError, ImageOptimizationError, FontSubsetError) as exc:
        raise RuntimeError(exc) from exc
    return _("Zaktualizowano EPUB: {path}").format(path=path)
