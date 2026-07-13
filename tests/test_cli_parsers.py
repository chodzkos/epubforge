"""Testy spójności parserów CLI: ``default`` ⊆ ``choices`` oraz tryby ``--engine``.

Kryterium ergonomii: każda wartość domyślna opcji z ``choices`` musi być też
akceptowalna JAWNIE (czyli należeć do ``choices``). Introspekcja idzie po całym
drzewie subkomend zbudowanym przez :func:`epubforge.cli.main.build_parser`, więc
guard łapie rozbieżność w dowolnym parserze (regresja jak F-09 dla ``kfx``).
"""

from __future__ import annotations

import argparse

import pytest

from epubforge.cli.main import build_parser


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Zwraca mapę nazwa_subkomendy → jej parser (z akcji ``_SubParsersAction``)."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _choice_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Akcje opcji z jawnym ``choices`` (pomija pozycyjne subkomend i store_true)."""
    return [action for action in parser._actions if action.choices is not None]


def test_all_choice_defaults_are_valid_choices() -> None:
    """W KAŻDEJ subkomendzie: default opcji z choices należy do tych choices.

    To gwarantuje, że wartość domyślną można podać także jawnie — argparse waliduje
    członkostwo w ``choices``, więc default spoza listy byłby odrzucony przy jawnym
    podaniu (dokładnie błąd F-09: ``--engine auto`` odrzucane mimo ``default='auto'``).
    """
    parser = build_parser()
    offenders: list[str] = []
    for name, sub in _subparsers(parser).items():
        for action in _choice_actions(sub):
            default = action.default
            if default is None or default is argparse.SUPPRESS:
                continue
            if default not in action.choices:
                offenders.append(f"{name} --{action.dest}: default {default!r} ∉ {action.choices}")
    assert offenders == [], "; ".join(offenders)


def test_kfx_default_engine_is_auto() -> None:
    """Brak flagi ``--engine`` → domyślnie ``auto`` (zachowanie niezmienione)."""
    args = build_parser().parse_args(["kfx", "book.epub"])
    assert args.engine == "auto"


@pytest.mark.parametrize("engine", ["auto", "calibre", "kindle-previewer"])
def test_kfx_engine_accepted_explicitly(engine: str) -> None:
    """Każdy tryb (w tym jawne ``--engine auto``) jest akceptowany przez parser."""
    args = build_parser().parse_args(["kfx", "book.epub", "--engine", engine])
    assert args.engine == engine


def test_kfx_engine_rejects_unknown_value() -> None:
    """Nieznany silnik jest odrzucany (argparse kończy SystemExit 2)."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["kfx", "book.epub", "--engine", "nonexistent"])
    assert exc.value.code == 2


def test_kfx_help_documents_all_engine_modes() -> None:
    """Snapshot pomocy ``kfx`` wymienia wszystkie tryby silnika."""
    help_text = _subparsers(build_parser())["kfx"].format_help()
    for engine in ("auto", "calibre", "kindle-previewer"):
        assert engine in help_text
