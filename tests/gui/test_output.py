"""Testy wspólnej logiki domyślnego katalogu wyjściowego."""

from __future__ import annotations

from pathlib import Path

from epubforge.gui.output import (
    LAST_OUTPUT_DIR_KEY,
    remember_output_dir,
    remembered_output_dir,
    resolve_output_dir,
)


def test_resolve_uses_source_parent_when_none() -> None:
    """Brak katalogu (None) → katalog pliku źródłowego."""
    source = Path("/books/sub/in.epub")
    assert resolve_output_dir(None, source) == Path("/books/sub")


def test_resolve_uses_explicit_dir() -> None:
    """Wskazany katalog jest używany bez zmian."""
    source = Path("/books/sub/in.epub")
    assert resolve_output_dir(Path("/out"), source) == Path("/out")


def test_remembered_empty_by_default() -> None:
    """Brak zapisanego katalogu → pusty łańcuch."""
    assert remembered_output_dir({}) == ""
    assert remembered_output_dir({LAST_OUTPUT_DIR_KEY: 123}) == ""


def test_remembered_returns_saved() -> None:
    """Zapisany katalog jest odczytywany."""
    assert remembered_output_dir({LAST_OUTPUT_DIR_KEY: "/out"}) == "/out"


def test_remember_saves_non_empty() -> None:
    """Niepuste pole jest zapamiętywane w configu."""
    config: dict[str, object] = {}
    remember_output_dir(config, "/out")
    assert config[LAST_OUTPUT_DIR_KEY] == "/out"


def test_remember_ignores_empty() -> None:
    """Puste pole nie nadpisuje configu."""
    config: dict[str, object] = {}
    remember_output_dir(config, "   ")
    assert LAST_OUTPUT_DIR_KEY not in config
