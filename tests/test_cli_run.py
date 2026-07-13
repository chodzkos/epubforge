"""Testy gałęzi błędów/edge komendy ``epubforge run`` (:mod:`epubforge.cli.run`).

Skupiamy się na ścieżkach walidacji argumentów i listowania receptur — reszta
(przepływ eksportu) jest pokryta przez ``test_recipes*``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from epubforge.cli import run as cli_run
from epubforge.recipes import Recipe, RecipeError


def _args(**overrides: object) -> argparse.Namespace:
    """Buduje Namespace z domyślnymi polami komendy run (nadpisywalny)."""
    base = {
        "list": False,
        "recipe": None,
        "files": [],
        "dry_run": False,
        "out_dir": None,
        "diff_full": False,
        "output_layout": "preserve",
        "force": False,
        "jobs": 1,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_run_missing_recipe_returns_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Brak nazwy receptury → kod 2 i komunikat na stderr."""
    assert cli_run.run(_args(recipe=None, files=[Path("b.epub")])) == 2
    assert "podaj nazwę receptury" in capsys.readouterr().err


def test_run_missing_files_returns_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Brak plików wejściowych → kod 2 i komunikat na stderr."""
    assert cli_run.run(_args(recipe="kindle", files=[])) == 2
    assert "co najmniej jeden plik" in capsys.readouterr().err


def test_run_unknown_recipe_returns_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``resolve_recipe`` rzucający RecipeError → kod 1 i komunikat."""

    def boom(_name: str) -> Recipe:
        raise RecipeError("nie ma takiej receptury")

    monkeypatch.setattr(cli_run, "resolve_recipe", boom)
    assert cli_run.run(_args(recipe="brak", files=[Path("b.epub")])) == 1
    assert "nie ma takiej receptury" in capsys.readouterr().err


def test_run_list_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--list`` deleguje do ``_list_recipes`` (kod z niego)."""
    monkeypatch.setattr(cli_run, "_list_recipes", lambda: 7)
    assert cli_run.run(_args(list=True)) == 7


def test_list_recipes_empty(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brak receptur → kod 0 i informacja."""
    monkeypatch.setattr(cli_run, "discover_recipes", list)
    assert cli_run._list_recipes() == 0
    assert "Brak dostępnych receptur" in capsys.readouterr().out


def test_list_recipes_prints_names_and_descriptions(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Receptury są wypisane; opis dołączany po tabie, gdy jest."""
    recipes = [
        Recipe(name="kindle", description="pod Kindle", steps=[], path=Path("kindle.toml")),
        Recipe(name="czysty", description="", steps=[], path=Path("czysty.toml")),
    ]
    monkeypatch.setattr(cli_run, "discover_recipes", lambda: recipes)
    assert cli_run._list_recipes() == 0
    out = capsys.readouterr().out
    assert "kindle\tpod Kindle" in out
    assert "czysty" in out


def test_list_recipes_error_returns_one(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Błąd odkrywania receptur → kod 1 i komunikat."""

    def boom() -> list[Recipe]:
        raise RecipeError("katalog receptur uszkodzony")

    monkeypatch.setattr(cli_run, "discover_recipes", boom)
    assert cli_run._list_recipes() == 1
    assert "katalog receptur uszkodzony" in capsys.readouterr().err
