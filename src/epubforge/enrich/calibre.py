"""Hurtowe wzbogacanie biblioteki Calibre przez ``calibredb`` (bez pluginu).

Odczyt (``calibredb list --for-machine``) → dopasowanie przez :mod:`epubforge.bookmeta`
→ zapis (``calibredb set_metadata --field …``). **Nigdy** nie dotykamy plików
biblioteki bezpośrednio na dysku — wyłącznie przez ``calibredb``, który zarządza
bazą i plikami spójnie.

``calibredb`` wymaga **zamkniętego GUI Calibre** (blokada bazy). Preflight
(:func:`preflight`) wykrywa blokadę i zgłasza czytelny błąd zamiast tajemniczego
komunikatu Calibre.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy
from epubforge.core import Metadata
from epubforge.core.detection import Tools
from epubforge.enrich.engine import Fetcher, default_fetcher, plan_enrichment
from epubforge.enrich.model import (
    ACTION_CHANGED,
    MATCH_NONE,
    TAGS_FIELD,
    BookOutcome,
    EnrichOptions,
    EnrichSummary,
)
from epubforge.i18n import _

# Flaga ukrywająca okno konsoli na Windows (jak w core/detection).
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_TIMEOUT = 120

# Sygnatura wstrzykiwanego ``subprocess.run`` (dla testów).
Runner = Callable[..., "subprocess.CompletedProcess[str]"]
ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]

# Mapowanie pól Metadata → nazwy pól ``calibredb set_metadata``.
_CALIBRE_FIELD_MAP = {
    "title": "title",
    "creators": "authors",
    "publisher": "publisher",
    "date": "pubdate",
    "description": "comments",
    "series": "series",
    "language": "languages",
    TAGS_FIELD: "tags",
}


class CalibreError(Exception):
    """Problem z ``calibredb`` (brak narzędzia, zablokowana baza, błąd komendy)."""


@dataclass
class CalibreBook:
    """Rekord książki odczytany z biblioteki Calibre."""

    id: int
    title: str
    authors: list[str]
    isbn: str
    tags: list[str]

    def to_metadata(self) -> Metadata:
        """Buduje :class:`Metadata` z pól Calibre (do dopasowania i planu zmian)."""
        return Metadata(
            title=self.title,
            creators=list(self.authors),
            identifier=self.isbn,
            subjects=list(self.tags),
        )


def enrich_library(
    library: Path,
    options: EnrichOptions,
    *,
    fetcher: Fetcher | None = None,
    taxonomy: Taxonomy | None = None,
    runner: Runner = subprocess.run,
    on_progress: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[BookOutcome], EnrichSummary]:
    """Wzbogaca bibliotekę Calibre; ``CalibreError`` przy blokadzie bazy lub braku narzędzia."""
    preflight(library, runner=runner)
    books = list_books(library, runner=runner)
    fetch = fetcher if fetcher is not None else default_fetcher
    tax = taxonomy
    if tax is None and options.want_tags:
        tax = load_taxonomy()

    outcomes: list[BookOutcome] = []
    for index, book in enumerate(books):
        if should_cancel is not None and should_cancel():
            break
        outcomes.append(_enrich_book(library, book, options, fetch, tax, runner))
        if on_progress is not None:
            on_progress(index + 1, len(books))
    return outcomes, EnrichSummary.from_outcomes(outcomes)


def preflight(library: Path, *, runner: Runner = subprocess.run) -> None:
    """Sprawdza dostępność biblioteki; blokada bazy (otwarte GUI) → ``CalibreError`` i STOP."""
    result = _run(["list", "--for-machine", "--limit", "1"], library, runner)
    if result.returncode != 0:
        raise CalibreError(
            _(
                "Nie udało się otworzyć biblioteki Calibre. Zamknij program Calibre "
                "(blokuje bazę) i spróbuj ponownie.\nSzczegóły: {details}"
            ).format(details=(result.stderr or "").strip() or _("nieznany błąd"))
        )


def list_books(library: Path, *, runner: Runner = subprocess.run) -> list[CalibreBook]:
    """Odczytuje książki (id, tytuł, autorzy, isbn, tagi) z biblioteki."""
    result = _run(
        ["list", "--for-machine", "--fields", "id,title,authors,isbn,tags"], library, runner
    )
    if result.returncode != 0:
        raise CalibreError(
            _("calibredb list zwrócił błąd: {details}").format(
                details=(result.stderr or "").strip()
            )
        )
    try:
        rows = json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, ValueError) as exc:
        raise CalibreError(_("Niepoprawna odpowiedź calibredb: {error}").format(error=exc)) from exc
    return [_parse_book(row) for row in rows if isinstance(row, dict)]


def set_metadata(
    library: Path, book_id: int, fields: dict[str, str], *, runner: Runner = subprocess.run
) -> None:
    """Zapisuje pola książki przez ``calibredb set_metadata --field name:value``."""
    args = ["set_metadata", str(book_id)]
    for name, value in fields.items():
        args.extend(["--field", f"{name}:{value}"])
    result = _run(args, library, runner)
    if result.returncode != 0:
        raise CalibreError(
            _("calibredb set_metadata (id={id}) zwrócił błąd: {details}").format(
                id=book_id, details=(result.stderr or "").strip()
            )
        )


def _enrich_book(
    library: Path,
    book: CalibreBook,
    options: EnrichOptions,
    fetcher: Fetcher,
    taxonomy: Taxonomy | None,
    runner: Runner,
) -> BookOutcome:
    """Wzbogaca jedną książkę Calibre (zapis pomijany w dry-run)."""
    metadata = book.to_metadata()
    fetched = fetcher(metadata, None)
    if fetched.record is None:
        return BookOutcome(str(book.id), MATCH_NONE, from_cache=fetched.from_cache)
    plan = plan_enrichment(metadata, None, fetched.record, options, taxonomy)
    changed = [c.field for c in plan.changes if c.action == ACTION_CHANGED]
    skipped = [c.field for c in plan.changes if c.action != ACTION_CHANGED]
    if not options.dry_run and changed:
        fields = _calibre_fields(plan.metadata, changed)
        if fields:
            set_metadata(library, book.id, fields, runner=runner)
    return BookOutcome(
        str(book.id),
        fetched.match,
        source=fetched.record.source,
        changed=changed,
        skipped=skipped,
        from_cache=fetched.from_cache,
    )


def _calibre_fields(metadata: Metadata, changed: list[str]) -> dict[str, str]:
    """Buduje mapę pól ``calibredb set_metadata`` dla zmienionych atrybutów."""
    fields: dict[str, str] = {}
    for attr in changed:
        if attr == "page_count":
            continue  # Calibre nie ma standardowej kolumny liczby stron
        if attr == "identifier":
            if metadata.identifier:
                fields["identifiers"] = f"isbn:{metadata.identifier}"
            continue
        calibre_name = _CALIBRE_FIELD_MAP.get(attr)
        if calibre_name is not None:
            fields[calibre_name] = _calibre_value(metadata, attr)
    return fields


def _calibre_value(metadata: Metadata, attr: str) -> str:
    """Zwraca wartość pola w formacie akceptowanym przez ``calibredb``."""
    if attr == "creators":
        return " & ".join(metadata.creators)
    if attr == TAGS_FIELD:
        return ",".join(metadata.subjects)
    return str(getattr(metadata, attr, "") or "")


def _parse_book(row: dict[str, Any]) -> CalibreBook:
    """Buduje :class:`CalibreBook` z wiersza ``calibredb --for-machine`` (defensywnie)."""
    return CalibreBook(
        id=int(row.get("id", 0) or 0),
        title=str(row.get("title", "") or ""),
        authors=_as_list(row.get("authors")),
        isbn=str(row.get("isbn", "") or ""),
        tags=_as_list(row.get("tags")),
    )


def _as_list(value: Any) -> list[str]:
    """Normalizuje pole Calibre do listy stringów (lista lub ``a & b`` / ``a,b``)."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        separator = "&" if "&" in value else ","
        return [part.strip() for part in value.split(separator) if part.strip()]
    return []


def _run(args: list[str], library: Path, runner: Runner) -> subprocess.CompletedProcess[str]:
    """Uruchamia ``calibredb <args> --library-path LIBRARY`` (ukryte okno na Windows)."""
    executable = _calibredb_executable()
    command = [str(executable), args[0], "--library-path", str(library), *args[1:]]
    try:
        return runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CalibreError(
            _("Nie udało się uruchomić calibredb: {error}").format(error=exc)
        ) from exc


def _calibredb_executable() -> Path:
    """Zwraca ścieżkę do ``calibredb`` albo ``CalibreError`` z instrukcją instalacji."""
    tool = Tools.calibredb()
    if tool.path is None:
        raise CalibreError(
            _("Nie wykryto calibredb. Zainstaluj Calibre i upewnij się, że jest w PATH.")
        )
    return tool.path
