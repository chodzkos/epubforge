"""Testy walidacji parsera receptur (``load_recipe``/``_parse_step``) — gałęzie błędów.

Każdy niepoprawny kształt TOML musi dać czytelny ``RecipeError`` (a nie krach),
bo receptury bywają pisane ręcznie. Uzupełnia szczęśliwą ścieżkę z ``test_recipes``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.recipes import RecipeError, load_recipe, resolve_recipe


def _write(tmp_path: Path, content: str, name: str = "r.toml") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_invalid_toml_raises(tmp_path: Path) -> None:
    """Niepoprawny TOML → RecipeError o niepoprawnym TOML."""
    with pytest.raises(RecipeError, match="niepoprawny TOML"):
        load_recipe(_write(tmp_path, "to nie jest = = toml"))


def test_unreadable_path_raises(tmp_path: Path) -> None:
    """Ścieżka będąca katalogiem → RecipeError (błąd odczytu)."""
    directory = tmp_path / "asdir.toml"
    directory.mkdir()
    with pytest.raises(RecipeError, match="nie można wczytać pliku"):
        load_recipe(directory)


def test_empty_name_raises(tmp_path: Path) -> None:
    """Puste pole name → RecipeError."""
    with pytest.raises(RecipeError, match="pole name"):
        load_recipe(_write(tmp_path, 'name = "  "\n[[steps]]\nop = "fix_css"\n'))


def test_non_text_description_raises(tmp_path: Path) -> None:
    """description nie-tekstowe → RecipeError."""
    with pytest.raises(RecipeError, match="pole description"):
        load_recipe(_write(tmp_path, 'name = "r"\ndescription = 5\n[[steps]]\nop = "fix_css"\n'))


def test_missing_steps_raises(tmp_path: Path) -> None:
    """Brak steps → RecipeError."""
    with pytest.raises(RecipeError, match="pole steps"):
        load_recipe(_write(tmp_path, 'name = "r"\n'))


def test_empty_steps_raises(tmp_path: Path) -> None:
    """Pusta lista steps → RecipeError."""
    with pytest.raises(RecipeError, match="pole steps"):
        load_recipe(_write(tmp_path, 'name = "r"\nsteps = []\n'))


def test_unknown_step_key_raises(tmp_path: Path) -> None:
    """Nieznane pole kroku → RecipeError."""
    toml = 'name = "r"\n[[steps]]\nop = "fix_css"\nfoo = 1\n'
    with pytest.raises(RecipeError, match="nieznane pola kroku"):
        load_recipe(_write(tmp_path, toml))


def test_empty_op_raises(tmp_path: Path) -> None:
    """Puste pole op → RecipeError."""
    with pytest.raises(RecipeError, match="pole op"):
        load_recipe(_write(tmp_path, 'name = "r"\n[[steps]]\nop = ""\n'))


def test_unknown_op_raises(tmp_path: Path) -> None:
    """Nieznana operacja → RecipeError."""
    with pytest.raises(RecipeError, match="nieznana operacja"):
        load_recipe(_write(tmp_path, 'name = "r"\n[[steps]]\nop = "nieistnieje"\n'))


def test_options_not_table_raises(tmp_path: Path) -> None:
    """options nie-tabelą → RecipeError."""
    toml = 'name = "r"\n[[steps]]\nop = "fix_css"\noptions = 5\n'
    with pytest.raises(RecipeError, match="sekcja options"):
        load_recipe(_write(tmp_path, toml))


def test_unknown_option_raises(tmp_path: Path) -> None:
    """Nieznana opcja kroku → RecipeError."""
    toml = 'name = "r"\n[[steps]]\nop = "fix_css"\n[steps.options]\nnieznana = true\n'
    with pytest.raises(RecipeError, match="nieznane opcje"):
        load_recipe(_write(tmp_path, toml))


def test_invalid_option_value_raises(tmp_path: Path) -> None:
    """Zła wartość opcji (zły typ) → RecipeError o niepoprawnych opcjach."""
    toml = 'name = "r"\n[[steps]]\nop = "apply_preset"\n[steps.options]\npreset = 5\nmode = 7\n'
    with pytest.raises(RecipeError, match="niepoprawne opcje"):
        load_recipe(_write(tmp_path, toml))


def test_resolve_unknown_name_raises(tmp_path: Path) -> None:
    """resolve_recipe po nieznanej nazwie → RecipeError z listą dozwolonych."""
    with pytest.raises(RecipeError, match="Nieznana receptura"):
        resolve_recipe("na-pewno-nie-ma-takiej-receptury")


def test_load_recipe_valid_roundtrip(tmp_path: Path) -> None:
    """Poprawna receptura z jednym krokiem fixer wczytuje się bez błędu."""
    toml = 'name = "moja"\ndescription = "opis"\n[[steps]]\nop = "fix_css"\n'
    recipe = load_recipe(_write(tmp_path, toml))
    assert recipe.name == "moja"
    assert recipe.description == "opis"
    assert len(recipe.steps) == 1
    assert recipe.steps[0].op == "fix_css"
