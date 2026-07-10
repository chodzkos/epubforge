"""Receptury EpubForge: deklaratywne pipeline'y fixerow i eksportu."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - wykonywane tylko na Pythonie 3.10
    import tomli as tomllib

from epubforge.converters import ConversionResult, KfxOptions, MobiOptions, to_kfx, to_mobi
from epubforge.core import Epub
from epubforge.core.config import config_dir
from epubforge.fixers import (
    CssFixOptions,
    FontSubsetOptions,
    HyphenationOptions,
    ImageFixOptions,
    TypographyOptions,
    apply_preset,
    fix_css,
    fix_typography,
    get_preset,
    hyphenate,
    optimize_images,
    subset_fonts,
)
from epubforge.i18n import _

StepKind: TypeAlias = Literal["fixer", "export"]
EmitLine: TypeAlias = Callable[[str], None]
ShouldCancel: TypeAlias = Callable[[], bool]
DryRunFormatter: TypeAlias = Callable[[Epub], str]


class RecipeError(ValueError):
    """Blad wczytania lub wykonania receptury."""


class RecipeCancelledError(RuntimeError):
    """Wykonanie receptury zostalo przerwane przez wywolujacego."""


@dataclass(frozen=True)
class PresetOptions:
    """Opcje kroku ``apply_preset``."""

    preset: str
    mode: Literal["append", "replace"] = "append"

    def __post_init__(self) -> None:
        if self.mode not in {"append", "replace"}:
            raise ValueError("mode musi miec wartosc append albo replace")


@dataclass(frozen=True)
class RecipeStep:
    """Pojedynczy krok receptury po walidacji opcji."""

    op: str
    options: object


@dataclass(frozen=True)
class Recipe:
    """Receptura pipeline'u dla plikow EPUB."""

    name: str
    description: str
    steps: tuple[RecipeStep, ...]
    path: Path


@dataclass(frozen=True)
class StepSpec:
    """Jawny wpis rejestru operacji receptur."""

    kind: StepKind
    fn: Callable[..., object]
    options_cls: type[Any]


def _apply_preset_step(epub: Epub, options: PresetOptions) -> None:
    apply_preset(epub, get_preset(options.preset), mode=options.mode)


def _export_mobi_step(source: Path, out_dir: Path, options: MobiOptions) -> ConversionResult:
    target = out_dir / f"{source.stem}.{options.fmt}"
    return to_mobi(source, target, options)


def _export_kfx_step(source: Path, out_dir: Path, options: KfxOptions) -> ConversionResult:
    return to_kfx(source, out_dir, options)


STEP_REGISTRY: dict[str, StepSpec] = {
    "fix_css": StepSpec("fixer", fix_css, CssFixOptions),
    "typography": StepSpec("fixer", fix_typography, TypographyOptions),
    "hyphenate": StepSpec("fixer", hyphenate, HyphenationOptions),
    "optimize_images": StepSpec("fixer", optimize_images, ImageFixOptions),
    "subset_fonts": StepSpec("fixer", subset_fonts, FontSubsetOptions),
    "apply_preset": StepSpec("fixer", _apply_preset_step, PresetOptions),
    "to_mobi": StepSpec("export", _export_mobi_step, MobiOptions),
    "to_kfx": StepSpec("export", _export_kfx_step, KfxOptions),
}


def load_recipe(path: Path) -> Recipe:
    """Wczytuje i waliduje recepture TOML."""
    recipe_path = Path(path)
    fallback_name = recipe_path.stem
    try:
        with recipe_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise RecipeError(
            _("Receptura {name}: niepoprawny TOML: {error}").format(
                name=fallback_name,
                error=exc,
            )
        ) from exc
    except OSError as exc:
        raise RecipeError(
            _("Receptura {name}: nie można wczytać pliku: {error}").format(
                name=fallback_name,
                error=exc,
            )
        ) from exc

    name_value = data.get("name", fallback_name)
    if not isinstance(name_value, str) or not name_value.strip():
        raise RecipeError(
            _("Receptura {name}: pole name musi być niepustym tekstem").format(name=fallback_name)
        )
    name = name_value.strip()

    description_value = data.get("description", "")
    if description_value is None:
        description = ""
    elif isinstance(description_value, str):
        description = description_value.strip()
    else:
        raise RecipeError(
            _("Receptura {name}: pole description musi być tekstem").format(name=name)
        )

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise RecipeError(
            _("Receptura {name}: pole steps musi zawierać co najmniej jeden krok").format(name=name)
        )

    steps = tuple(
        _parse_step(name, index, raw_step) for index, raw_step in enumerate(raw_steps, start=1)
    )
    return Recipe(name=name, description=description, steps=steps, path=recipe_path)


def discover_recipes(user_dir: Path | None = None) -> list[Recipe]:
    """Zwraca receptury wbudowane i użytkownika; użytkownik przykrywa nazwą."""
    recipes: dict[str, Recipe] = {}
    for recipe in _load_recipe_dir(_builtin_dir()):
        recipes[recipe.name] = recipe

    recipe_dir = Path(user_dir) if user_dir is not None else config_dir() / "recipes"
    for recipe in _load_recipe_dir(recipe_dir):
        recipes[recipe.name] = recipe
    return [recipes[name] for name in sorted(recipes)]


def resolve_recipe(reference: str | Path) -> Recipe:
    """Wczytuje recepture ze ścieżki TOML albo wyszukuje po nazwie."""
    text = str(reference)
    path = Path(reference)
    if path.suffix.lower() == ".toml" or path.exists():
        return load_recipe(path)

    recipes = {recipe.name: recipe for recipe in discover_recipes()}
    try:
        return recipes[text]
    except KeyError as exc:
        raise RecipeError(
            _("Nieznana receptura {name}. Dozwolone: {allowed}").format(
                name=text,
                allowed=", ".join(sorted(recipes)) or _("brak"),
            )
        ) from exc


def run_recipe(
    recipe: Recipe,
    epub_path: Path,
    out_dir: Path,
    emit_line: EmitLine,
    should_cancel: ShouldCancel | None = None,
    *,
    dry_run: bool = False,
    dry_run_formatter: DryRunFormatter | None = None,
) -> tuple[Path, ...]:
    """Uruchamia recepture dla jednego EPUB-a.

    Faza fixerow pracuje na jednym otwartym :class:`Epub` i zapisuje raz na koncu.
    Faza eksportu dostaje zapisana sciezke EPUB-a; eksportery nie modyfikuja wejscia.
    """
    source = Path(epub_path)
    target_dir = Path(out_dir)
    fixer_steps = _steps_by_kind(recipe.steps, "fixer")
    export_steps = _steps_by_kind(recipe.steps, "export")
    saved_path = source

    if fixer_steps:
        with Epub(source) as epub:
            for index, step in fixer_steps:
                _raise_if_cancelled(should_cancel)
                emit_line(_("Krok {index}: {op}").format(index=index, op=step.op))
                _run_fixer_step(step, epub)

            if dry_run:
                emit_line(_format_dry_run(epub, formatter=dry_run_formatter))
                _emit_dry_run_export_note(export_steps, emit_line)
                return ()

            _raise_if_cancelled(should_cancel)
            saved_path = epub.save()
            emit_line(_("Zapisano EPUB: {path}").format(path=saved_path))
    elif dry_run:
        emit_line(_("Dry-run: receptura nie ma kroków fixerów; nic nie zapisano"))
        _emit_dry_run_export_note(export_steps, emit_line)
        return ()

    if not export_steps:
        return ()

    target_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, step in export_steps:
        _raise_if_cancelled(should_cancel)
        emit_line(_("Krok {index}: {op}").format(index=index, op=step.op))
        result = _run_export_step(step, saved_path, target_dir)
        outputs.append(result.output_path)
        emit_line(
            _("Utworzono: {path} ({engine})").format(
                path=result.output_path,
                engine=result.engine,
            )
        )
    return tuple(outputs)


def _parse_step(recipe_name: str, index: int, raw_step: object) -> RecipeStep:
    if not isinstance(raw_step, dict):
        raise _step_error(
            recipe_name,
            index,
            _("krok musi być tabelą TOML"),
            allowed=("op", "options"),
        )

    step_data = cast(dict[str, object], raw_step)
    unknown_step_keys = sorted(set(step_data) - {"op", "options"})
    if unknown_step_keys:
        raise _step_error(
            recipe_name,
            index,
            _("nieznane pola kroku: {names}").format(names=", ".join(unknown_step_keys)),
            allowed=("op", "options"),
        )

    op_value = step_data.get("op")
    if not isinstance(op_value, str) or not op_value:
        raise _step_error(
            recipe_name,
            index,
            _("pole op musi być niepustym tekstem"),
            allowed=tuple(sorted(STEP_REGISTRY)),
        )
    spec = STEP_REGISTRY.get(op_value)
    if spec is None:
        raise _step_error(
            recipe_name,
            index,
            _("nieznana operacja {op}").format(op=op_value),
            allowed=tuple(sorted(STEP_REGISTRY)),
        )

    raw_options = step_data.get("options", {})
    if not isinstance(raw_options, dict):
        raise _step_error(
            recipe_name,
            index,
            _("sekcja options musi być tabelą TOML"),
            allowed=_allowed_options(spec.options_cls),
        )
    option_data = cast(dict[str, object], raw_options)
    allowed_options = _allowed_options(spec.options_cls)
    unknown_options = sorted(set(option_data) - set(allowed_options))
    if unknown_options:
        raise _step_error(
            recipe_name,
            index,
            _("nieznane opcje dla {op}: {names}").format(
                op=op_value,
                names=", ".join(unknown_options),
            ),
            allowed=allowed_options,
        )

    try:
        options = spec.options_cls(**option_data)
    except (TypeError, ValueError) as exc:
        raise _step_error(
            recipe_name,
            index,
            _("niepoprawne opcje dla {op}: {error}").format(op=op_value, error=exc),
            allowed=allowed_options,
        ) from exc
    return RecipeStep(op=op_value, options=options)


def _run_fixer_step(step: RecipeStep, epub: Epub) -> object:
    spec = STEP_REGISTRY[step.op]
    if spec.kind != "fixer":
        raise RecipeError(_("Operacja {op} nie jest fixerem").format(op=step.op))
    return spec.fn(epub, step.options)


def _run_export_step(step: RecipeStep, source: Path, out_dir: Path) -> ConversionResult:
    spec = STEP_REGISTRY[step.op]
    if spec.kind != "export":
        raise RecipeError(_("Operacja {op} nie jest eksportem").format(op=step.op))
    result = spec.fn(source, out_dir, step.options)
    if not isinstance(result, ConversionResult):
        raise RecipeError(_("Eksport {op} nie zwrócił wyniku konwersji").format(op=step.op))
    return result


def _steps_by_kind(
    steps: Sequence[RecipeStep],
    kind: StepKind,
) -> list[tuple[int, RecipeStep]]:
    return [
        (index, step)
        for index, step in enumerate(steps, start=1)
        if STEP_REGISTRY[step.op].kind == kind
    ]


def _format_dry_run(epub: Epub, *, formatter: DryRunFormatter | None) -> str:
    if formatter is not None:
        return formatter(epub)
    changes = epub.pending_changes()
    return _("{modified} plików zmienionych, {deleted} usuniętych; nic nie zapisano").format(
        modified=len(changes.modified),
        deleted=len(changes.deleted),
    )


def _emit_dry_run_export_note(
    export_steps: Sequence[tuple[int, RecipeStep]],
    emit_line: EmitLine,
) -> None:
    if not export_steps:
        return
    ops = ", ".join(step.op for _index, step in export_steps)
    emit_line(_("Dry-run: pominięto kroki eksportu: {ops}").format(ops=ops))


def _raise_if_cancelled(should_cancel: ShouldCancel | None) -> None:
    if should_cancel is not None and should_cancel():
        raise RecipeCancelledError(_("Przerwano wykonywanie receptury"))


def _step_error(
    recipe_name: str,
    index: int,
    message: str,
    *,
    allowed: Sequence[str],
) -> RecipeError:
    allowed_text = ", ".join(allowed) if allowed else _("brak")
    return RecipeError(
        _("Receptura {name}, krok {index}: {message}. Dozwolone: {allowed}").format(
            name=recipe_name,
            index=index,
            message=message,
            allowed=allowed_text,
        )
    )


def _allowed_options(options_cls: type[Any]) -> tuple[str, ...]:
    if not is_dataclass(options_cls):
        return ()
    return tuple(field.name for field in fields(options_cls) if field.init)


def _builtin_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "recipes_builtin"
    return Path(__file__).resolve().parent / "recipes_builtin"


def _load_recipe_dir(directory: Path) -> list[Recipe]:
    if not directory.is_dir():
        return []
    return [load_recipe(path) for path in sorted(directory.glob("*.toml"))]


__all__ = [
    "STEP_REGISTRY",
    "DryRunFormatter",
    "EmitLine",
    "PresetOptions",
    "Recipe",
    "RecipeCancelledError",
    "RecipeError",
    "RecipeStep",
    "StepSpec",
    "discover_recipes",
    "load_recipe",
    "resolve_recipe",
    "run_recipe",
]
