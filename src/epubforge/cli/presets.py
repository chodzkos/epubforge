"""Subkomenda CLI ``epubforge presets`` — biblioteka presetów CSS."""

from __future__ import annotations

import argparse

from epubforge.fixers import list_presets
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``presets`` (z pod-komendą ``list``)."""
    parser = subparsers.add_parser("presets", help=_("Biblioteka presetów CSS"))
    nested = parser.add_subparsers(dest="presets_command")
    list_parser = nested.add_parser("list", help=_("Wypisz dostępne presety CSS"))
    list_parser.set_defaults(func=run_list)
    parser.set_defaults(func=_run_default)


def run_list(_args: argparse.Namespace) -> int:
    """Wypisuje tabelę presetów (id, nazwa, opis) w bieżącym języku."""
    presets = list_presets()
    rows = [(preset.id, preset.display_name(), preset.display_description()) for preset in presets]
    id_header, name_header, desc_header = _("ID"), _("Nazwa"), _("Opis")
    id_width = max([len(id_header), *(len(row[0]) for row in rows)])
    name_width = max([len(name_header), *(len(row[1]) for row in rows)])

    print(f"{id_header:<{id_width}}  {name_header:<{name_width}}  {desc_header}")
    for preset_id, name, description in rows:
        print(f"{preset_id:<{id_width}}  {name:<{name_width}}  {description}")
    return 0


def _run_default(args: argparse.Namespace) -> int:
    """Bez pod-komendy: wypisuje listę presetów (domyślne zachowanie)."""
    if getattr(args, "presets_command", None) is None:
        return run_list(args)
    return 0
