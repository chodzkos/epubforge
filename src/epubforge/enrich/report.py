"""Raport hurtowego wzbogacania — CSV/JSON oraz formatowanie dla terminala."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from epubforge.enrich.model import BookOutcome, EnrichSummary
from epubforge.i18n import _

# Kolumny raportu per książka.
_COLUMNS = ("identifier", "match", "source", "changed", "skipped", "from_cache", "error")


def write_report(path: Path, outcomes: list[BookOutcome], summary: EnrichSummary) -> None:
    """Zapisuje raport do pliku CSV lub JSON (format wg rozszerzenia; domyślnie CSV)."""
    if path.suffix.lower() == ".json":
        _write_json(path, outcomes, summary)
    else:
        _write_csv(path, outcomes)


def _write_csv(path: Path, outcomes: list[BookOutcome]) -> None:
    """Zapisuje wyniki per książka jako CSV (listy pól sklejone przecinkiem)."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_COLUMNS)
        for outcome in outcomes:
            writer.writerow(
                [
                    outcome.identifier,
                    outcome.match,
                    outcome.source,
                    "; ".join(outcome.changed),
                    "; ".join(outcome.skipped),
                    "tak" if outcome.from_cache else "nie",
                    outcome.error,
                ]
            )


def _write_json(path: Path, outcomes: list[BookOutcome], summary: EnrichSummary) -> None:
    """Zapisuje raport jako JSON: podsumowanie + lista wyników per książka."""
    payload = {
        "summary": asdict(summary),
        "books": [asdict(outcome) for outcome in outcomes],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def format_summary(summary: EnrichSummary) -> str:
    """Zwraca jednolinijkowe podsumowanie do wypisania na terminalu."""
    return _(
        "Podsumowanie: {total} książek — znalezione: {found}, nieznalezione: "
        "{not_found}, z cache: {cache}, zmienione: {changed}, błędy: {errors}"
    ).format(
        total=summary.total,
        found=summary.found,
        not_found=summary.not_found,
        cache=summary.from_cache,
        changed=summary.changed,
        errors=summary.errors,
    )


def format_outcome_line(outcome: BookOutcome, *, dry_run: bool) -> str:
    """Formatuje jedną linię planu/wyniku per książka (do dry-run i podglądu)."""
    if outcome.error:
        return _("{id}: BŁĄD — {error}").format(id=outcome.identifier, error=outcome.error)
    if not outcome.found:
        return _("{id}: brak dopasowania").format(id=outcome.identifier)
    verb = _("do zmiany") if dry_run else _("zmienione")
    changed = ", ".join(outcome.changed) if outcome.changed else _("(nic)")
    skipped = ", ".join(outcome.skipped) if outcome.skipped else _("(nic)")
    return _(
        "{id}: dopasowanie {match} ({source}); {verb}: {changed}; pominięte: {skipped}"
    ).format(
        id=outcome.identifier,
        match=outcome.match,
        source=outcome.source or "?",
        verb=verb,
        changed=changed,
        skipped=skipped,
    )
