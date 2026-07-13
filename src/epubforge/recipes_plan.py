"""Preflight planowania ścieżek wyjściowych receptur — wykrywanie kolizji.

Zanim batch/receptura cokolwiek zapisze, przewidujemy WSZYSTKIE ścieżki wyjściowe
kroków eksportu i wykrywamy kolizje:

* ``input-collision`` — dwa różne wejścia o tym samym ``stem`` mapują na tę samą
  ścieżkę (np. ``a/book.epub`` i ``b/book.epub`` → ``out/book.mobi``);
* ``duplicate-step`` — powtórzone kroki eksportu tego samego wejścia dają ten sam plik;
* ``exists`` — plik wyjściowy już istnieje na dysku (chyba że ``--force``).

Domyślnie wywołujący przerywa PRZED pierwszym zapisem z listą konfliktów. Lista jest
**deterministyczna** (sortowana po ścieżce), więc wynik nie zależy od kolejności
wejść ani workerów. ``--output-layout unique`` eliminuje ``input-collision`` przez
podkatalog per wejście.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from epubforge.recipes import (
    STEP_REGISTRY,
    OutputLayout,
    Recipe,
    RecipeStep,
    effective_out_dir,
    export_output_path,
)

ConflictKind: TypeAlias = Literal["input-collision", "duplicate-step", "exists"]


@dataclass(frozen=True)
class PlannedOutput:
    """Pojedyncza przewidziana ścieżka wyjściowa (źródło + operacja + cel)."""

    source: Path
    op: str
    path: Path


@dataclass(frozen=True)
class OutputConflict:
    """Wykryta kolizja ścieżki wyjściowej."""

    path: Path
    kind: ConflictKind
    sources: tuple[Path, ...]


@dataclass(frozen=True)
class OutputPlan:
    """Wynik preflightu: przewidziane wyjścia i wykryte kolizje."""

    outputs: tuple[PlannedOutput, ...]
    conflicts: tuple[OutputConflict, ...]


def _export_steps(recipe: Recipe) -> list[RecipeStep]:
    """Kroki eksportu receptury (w kolejności)."""
    return [step for step in recipe.steps if STEP_REGISTRY[step.op].kind == "export"]


def _dedup_sources(sources: Sequence[Path]) -> list[Path]:
    """Usuwa duplikaty wejść po ścieżce kanonicznej, zachowując pierwsze wystąpienie."""
    seen: set[str] = set()
    unique: list[Path] = []
    for source in sources:
        key = str(Path(source).resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append(Path(source))
    return unique


def plan_recipe_outputs(
    recipe: Recipe,
    sources: Sequence[Path],
    out_dir: Path | None,
    *,
    layout: OutputLayout = "preserve",
    force: bool = False,
) -> OutputPlan:
    """Buduje plan wszystkich ścieżek wyjściowych eksportu i wykrywa kolizje.

    Args:
        recipe: receptura (bierzemy z niej kroki eksportu).
        sources: pliki wejściowe (duplikaty ścieżek są ignorowane).
        out_dir: katalog docelowy; ``None`` = katalog obok każdego wejścia.
        layout: ``preserve`` (płasko) albo ``unique`` (podkatalog per wejście).
        force: gdy ``True``, istniejące pliki nie są traktowane jak konflikt.

    Returns:
        :class:`OutputPlan` z przewidzianymi wyjściami i listą kolizji.
    """
    planned: list[PlannedOutput] = []
    export_steps = _export_steps(recipe)
    for source in _dedup_sources(sources):
        base = out_dir if out_dir is not None else source.parent
        target_dir = effective_out_dir(source, base, layout)
        for step in export_steps:
            planned.append(
                PlannedOutput(source, step.op, export_output_path(step, source, target_dir))
            )
    return OutputPlan(tuple(planned), _detect_conflicts(planned, force=force))


def _detect_conflicts(
    planned: Sequence[PlannedOutput], *, force: bool
) -> tuple[OutputConflict, ...]:
    """Grupuje wyjścia po ścieżce kanonicznej i zwraca kolizje w deterministycznej kolejności."""
    by_path: dict[str, list[PlannedOutput]] = {}
    for output in planned:
        by_path.setdefault(str(output.path.resolve(strict=False)), []).append(output)

    conflicts: list[OutputConflict] = []
    for key in sorted(by_path):  # sortowanie po ścieżce → wynik niezależny od kolejności wejść
        group = by_path[key]
        path = group[0].path
        contributors = tuple(sorted({output.source for output in group}, key=str))
        if len(group) > 1:
            kind: ConflictKind = "input-collision" if len(contributors) > 1 else "duplicate-step"
            conflicts.append(OutputConflict(path, kind, contributors))
        elif path.exists() and not force:
            conflicts.append(OutputConflict(path, "exists", contributors))
    return tuple(conflicts)


def describe_conflict(conflict: OutputConflict) -> str:
    """Zwraca czytelny, jednoliniowy opis kolizji (dla CLI/GUI)."""
    sources = ", ".join(str(source) for source in conflict.sources)
    if conflict.kind == "input-collision":
        return f"{conflict.path}: kolizja wejść o tym samym stem ({sources})"
    if conflict.kind == "duplicate-step":
        return f"{conflict.path}: powtórzony krok eksportu dla {sources}"
    return f"{conflict.path}: plik już istnieje (użyj --force, aby nadpisać) — z {sources}"
