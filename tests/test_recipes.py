"""Testy receptur TOML i runnera pipeline'ow."""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.converters import ConversionResult, MobiOptions
from epubforge.core import Epub
from epubforge.fixers import CssFixOptions, TypographyOptions
from epubforge.recipes import (
    STEP_REGISTRY,
    RecipeError,
    StepSpec,
    discover_recipes,
    load_recipe,
    run_recipe,
)


def _write_recipe(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_recipe_validates_steps_and_options(tmp_path: Path) -> None:
    """Poprawna receptura TOML zamienia opcje na dataclasses z rejestru."""
    path = _write_recipe(
        tmp_path / "ok.toml",
        """
name = "ok"
description = "test"

[[steps]]
op = "fix_css"
[steps.options]
remove_colors = true
replace_justify = "left"

[[steps]]
op = "typography"
[steps.options]
language = "pl"
""",
    )

    recipe = load_recipe(path)

    assert recipe.name == "ok"
    assert recipe.description == "test"
    assert recipe.steps[0].op == "fix_css"
    assert isinstance(recipe.steps[0].options, CssFixOptions)
    assert isinstance(recipe.steps[1].options, TypographyOptions)


def test_load_recipe_unknown_op_reports_allowed_values(tmp_path: Path) -> None:
    """Nieznany op daje RecipeError z nazwą receptury, krokiem i listą dozwolonych."""
    path = _write_recipe(
        tmp_path / "bad-op.toml",
        """
name = "bad"

[[steps]]
op = "to_epub"
""",
    )

    with pytest.raises(RecipeError) as error:
        load_recipe(path)

    message = str(error.value)
    assert "bad" in message
    assert "krok 1" in message
    assert "to_epub" in message
    assert "fix_css" in message
    assert "to_mobi" in message


def test_load_recipe_unknown_option_reports_allowed_values(tmp_path: Path) -> None:
    """Nieznana opcja kroku daje czytelny błąd z polami OptionsClass."""
    path = _write_recipe(
        tmp_path / "bad-option.toml",
        """
name = "bad"

[[steps]]
op = "fix_css"
[steps.options]
typo = true
""",
    )

    with pytest.raises(RecipeError) as error:
        load_recipe(path)

    message = str(error.value)
    assert "bad" in message
    assert "krok 1" in message
    assert "typo" in message
    assert "remove_colors" in message


def test_run_recipe_uses_one_fix_phase_then_mocked_export(
    tmp_path: Path,
    sample_epub: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runner zapisuje EPUB po fixerach i przekazuje zapisany plik do eksportu."""
    recipe_path = _write_recipe(
        tmp_path / "export.toml",
        """
name = "export"

[[steps]]
op = "fix_css"

[[steps]]
op = "to_mobi"
[steps.options]
fmt = "mobi"
""",
    )
    exported_sources: list[Path] = []

    def fake_fix(epub: Epub, _options: CssFixOptions) -> None:
        chapter = "OEBPS/text/chapter1.xhtml"
        epub.write_file(chapter, epub.read_file(chapter) + b"\n<!-- recipe-test -->")

    def fake_export(source: Path, out_dir: Path, options: MobiOptions) -> ConversionResult:
        exported_sources.append(source)
        target = out_dir / f"{source.stem}.{options.fmt}"
        target.write_bytes(b"mobi")
        return ConversionResult(success=True, output_path=target, log="ok", engine="fake")

    monkeypatch.setitem(STEP_REGISTRY, "fix_css", StepSpec("fixer", fake_fix, CssFixOptions))
    monkeypatch.setitem(STEP_REGISTRY, "to_mobi", StepSpec("export", fake_export, MobiOptions))
    recipe = load_recipe(recipe_path)
    lines: list[str] = []

    outputs = run_recipe(recipe, sample_epub, tmp_path / "out", lines.append)

    assert outputs == (tmp_path / "out" / "book.mobi",)
    assert outputs[0].read_bytes() == b"mobi"
    assert exported_sources == [sample_epub]
    assert sample_epub.with_suffix(".epub.bak").is_file()
    assert any("Zapisano EPUB" in line for line in lines)
    assert any("Utworzono" in line for line in lines)


def test_user_recipe_overrides_builtin_by_name(tmp_path: Path) -> None:
    """Własna receptura z tą samą nazwą przykrywa wbudowaną."""
    user_dir = tmp_path / "recipes"
    user_dir.mkdir()
    _write_recipe(
        user_dir / "kindle-pl.toml",
        """
name = "kindle-pl"
description = "custom"

[[steps]]
op = "fix_css"
""",
    )

    recipes = {recipe.name: recipe for recipe in discover_recipes(user_dir=user_dir)}

    assert recipes["kindle-pl"].description == "custom"
    assert recipes["kindle-pl"].path == user_dir / "kindle-pl.toml"
    assert "czytnik-epub" in recipes
