"""Subkomenda CLI ``epubforge run`` — receptury TOML."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from epubforge.cli._batch import format_dry_run, run_batch
from epubforge.i18n import _
from epubforge.recipes import Recipe, RecipeError, discover_recipes, resolve_recipe, run_recipe


@dataclass(frozen=True)
class _RunPayload:
    """Picklowalne opcje pracy dla pojedynczego pliku."""

    recipe: Recipe
    out_dir: Path | None
    dry_run: bool
    diff_full: bool


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``run`` w głównym parserze argparse."""
    parser = subparsers.add_parser("run", help=_("Uruchom recepturę TOML na plikach EPUB"))
    parser.add_argument("recipe", nargs="?", help=_("Nazwa receptury albo ścieżka .toml"))
    parser.add_argument("files", type=Path, nargs="*", help=_("Pliki EPUB do przetworzenia"))
    parser.add_argument("--out-dir", type=Path, help=_("Katalog wyników eksportu"))
    parser.add_argument(
        "--list",
        action="store_true",
        help=_("Wypisz dostępne receptury i zakończ"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Pokaż zmiany fixerów bez zapisu; kroki eksportu zostaną pominięte"),
    )
    parser.add_argument(
        "--diff-full",
        action="store_true",
        help=_("Nie skracaj diffów w trybie --dry-run"),
    )
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        default=1,
        help=_("Liczba równoległych procesów roboczych (domyślnie: 1)"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia recepturę z argumentów CLI."""
    if args.list:
        return _list_recipes()
    if not args.recipe:
        print(_("Błąd: podaj nazwę receptury albo ścieżkę .toml"), file=sys.stderr)
        return 2
    if not args.files:
        print(_("Błąd: podaj co najmniej jeden plik EPUB"), file=sys.stderr)
        return 2

    try:
        recipe = resolve_recipe(args.recipe)
    except RecipeError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    payload = _RunPayload(
        recipe=recipe,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
        diff_full=args.diff_full,
    )
    return run_batch(args.files, jobs=args.jobs, handler=_run_recipe_for_path, payload=payload)


def _run_recipe_for_path(path: Path, raw_payload: object) -> str:
    """Przetwarza jeden EPUB dla batch runnera."""
    payload = cast(_RunPayload, raw_payload)
    lines: list[str] = [
        _("Receptura {recipe}: {path}").format(recipe=payload.recipe.name, path=path)
    ]

    def emit_line(line: str) -> None:
        lines.append(line)

    output_dir = payload.out_dir if payload.out_dir is not None else path.parent
    outputs = run_recipe(
        payload.recipe,
        path,
        output_dir,
        emit_line,
        dry_run=payload.dry_run,
        dry_run_formatter=lambda epub: format_dry_run(epub, diff_full=payload.diff_full),
    )
    if outputs:
        rendered = ", ".join(str(output) for output in outputs)
        lines.append(_("Wyniki eksportu: {paths}").format(paths=rendered))
    return "\n".join(lines)


def _list_recipes() -> int:
    try:
        recipes = discover_recipes()
    except RecipeError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    if not recipes:
        print(_("Brak dostępnych receptur"))
        return 0

    for recipe in recipes:
        if recipe.description:
            print(f"{recipe.name}\t{recipe.description}")
        else:
            print(recipe.name)
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(_("--jobs musi być większe od zera"))
    return parsed
