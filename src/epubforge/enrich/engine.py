"""Silnik hurtowego wzbogacania metadanych EPUB (plan + zastosowanie + batch).

Dla każdej książki: dopasowanie rekordu przez :mod:`epubforge.bookmeta` (ISBN →
fuzzy tytuł/autor → brak), obliczenie planu zmian wg polityk i — poza trybem
dry-run — zapis do OPF. Pobieranie jest **wstrzykiwalne** (parametr ``fetcher``),
więc testy działają bez sieci.

Przebieg jest **sekwencyjny w jednym procesie** — dzięki temu współdzielony rate
limiter i cache providera LC (Etap 28) obowiązują cały hurt (nie omijamy odstępów
między żądaniami).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from epubforge.bookmeta import BookRecord, chain, extract_isbn_from_epub, validate_isbn
from epubforge.bookmeta.match import CONFIDENCE_THRESHOLD
from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy, map_subjects
from epubforge.core import (
    Epub,
    EpubError,
    Metadata,
    get_number_of_pages,
    set_number_of_pages,
)
from epubforge.enrich.model import (
    ACTION_CHANGED,
    ACTION_SKIPPED,
    LIST_FIELDS,
    MATCH_FUZZY,
    MATCH_ISBN,
    MATCH_NONE,
    TAGS_FIELD,
    BookOutcome,
    EnrichOptions,
    EnrichSummary,
    FieldChange,
)

# Sygnatury callbacków.
ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


@dataclass
class FetchOutcome:
    """Wynik dopasowania rekordu do książki (z providerów bookmeta)."""

    record: BookRecord | None
    match: str
    source: str = ""
    from_cache: bool = False


# Fetcher: (metadane, otwarty Epub lub None) → wynik dopasowania.
Fetcher = Callable[[Metadata, "Epub | None"], FetchOutcome]


@dataclass
class EnrichPlan:
    """Plan zmian dla jednej książki: opis zmian + gotowe metadane i liczba stron."""

    changes: list[FieldChange]
    metadata: Metadata
    page_count: int | None


# ── Plan zmian ────────────────────────────────────────────────────────────────────


def plan_enrichment(
    metadata: Metadata,
    existing_pages: int | None,
    record: BookRecord,
    options: EnrichOptions,
    taxonomy: Taxonomy | None,
) -> EnrichPlan:
    """Buduje plan zmian: zaktualizowaną kopię metadanych + listę :class:`FieldChange`.

    Nie modyfikuje wejściowych metadanych — zwraca kopię (z policzoną liczbą stron
    do zapisania w OPF, jeśli dotyczy).
    """
    updated = replace(metadata, creators=list(metadata.creators), subjects=list(metadata.subjects))
    changes: list[FieldChange] = []
    page_count: int | None = None

    for attr in options.fields:
        if attr == "page_count":
            change, page_count = _plan_pages(
                existing_pages, record.page_count, options.field_policy
            )
            changes.append(change)
        elif attr in LIST_FIELDS:
            changes.append(
                _plan_list(updated, attr, _record_list(record, attr), options.field_policy)
            )
        else:
            changes.append(
                _plan_scalar(updated, attr, _record_scalar(record, attr), options.field_policy)
            )

    if options.want_tags and taxonomy is not None:
        changes.append(_plan_tags(updated, record, options.tags_policy, taxonomy))

    return EnrichPlan(changes=changes, metadata=updated, page_count=page_count)


def _plan_scalar(updated: Metadata, attr: str, new: str, policy: str) -> FieldChange:
    """Planuje zmianę pola skalarnego wg polityki (aktualizuje ``updated`` przy zmianie)."""
    old = str(getattr(updated, attr) or "")
    if _accept_scalar(old, new, policy):
        setattr(updated, attr, new)
        return FieldChange(attr, old, new, ACTION_CHANGED)
    return FieldChange(attr, old, new, ACTION_SKIPPED)


def _plan_list(updated: Metadata, attr: str, new: list[str], policy: str) -> FieldChange:
    """Planuje zmianę pola listowego wg polityki (aktualizuje ``updated`` przy zmianie)."""
    old = list(getattr(updated, attr))
    merged = _merge_list(old, new, policy)
    if merged != old:
        setattr(updated, attr, merged)
        return FieldChange(attr, ", ".join(old), ", ".join(merged), ACTION_CHANGED)
    return FieldChange(attr, ", ".join(old), ", ".join(new), ACTION_SKIPPED)


def _plan_tags(
    updated: Metadata, record: BookRecord, policy: str, taxonomy: Taxonomy
) -> FieldChange:
    """Planuje tagi: mapowanie tematów rekordu na taksonomię, scalenie wg polityki."""
    mapped = map_subjects(record.subjects, taxonomy)
    new_tags = [m.tag for m in mapped.mapped]
    old = list(updated.subjects)
    merged = _merge_list(old, new_tags, policy)
    if merged != old:
        updated.subjects = merged
        return FieldChange(TAGS_FIELD, ", ".join(old), ", ".join(merged), ACTION_CHANGED)
    return FieldChange(TAGS_FIELD, ", ".join(old), ", ".join(new_tags), ACTION_SKIPPED)


def _plan_pages(old: int | None, new: int | None, policy: str) -> tuple[FieldChange, int | None]:
    """Planuje liczbę stron; zwraca zmianę oraz wartość do zapisania w OPF (lub ``None``)."""
    old_text = "" if old is None else str(old)
    if new is None or new <= 0:
        return FieldChange("page_count", old_text, old_text, ACTION_SKIPPED), None
    accept = new != old if policy == "overwrite" else old is None
    if accept:
        return FieldChange("page_count", old_text, str(new), ACTION_CHANGED), new
    return FieldChange("page_count", old_text, str(new), ACTION_SKIPPED), None


def _accept_scalar(old: str, new: str, policy: str) -> bool:
    """Czy przyjąć nową wartość skalarną: overwrite gdy różna; fill/append gdy stare puste."""
    if not new:
        return False
    if policy == "overwrite":
        return new != old
    return not old


def _merge_list(old: list[str], new: list[str], policy: str) -> list[str]:
    """Scala listy wg polityki: overwrite=zastąp, fill=uzupełnij gdy pusto, append=dopisz brakujące."""
    if not new:
        return old
    if policy == "overwrite":
        return list(new)
    if policy == "fill":
        return old if old else list(new)
    merged = list(old)
    for item in new:
        if item not in merged:
            merged.append(item)
    return merged


def _record_scalar(record: BookRecord, attr: str) -> str:
    """Zwraca wartość skalarną rekordu odpowiadającą polu Metadata."""
    if attr == "identifier":
        return record.isbn
    return str(getattr(record, attr, "") or "")


def _record_list(record: BookRecord, attr: str) -> list[str]:
    """Zwraca wartość listową rekordu (obecnie tylko ``creators``)."""
    value = getattr(record, attr, [])
    return list(value) if isinstance(value, list) else []


# ── Wzbogacanie plików ─────────────────────────────────────────────────────────────


def enrich_epub(
    path: Path, options: EnrichOptions, fetcher: Fetcher, taxonomy: Taxonomy | None
) -> BookOutcome:
    """Wzbogaca jeden plik EPUB; zwraca :class:`BookOutcome` (zapis pomijany w dry-run)."""
    try:
        with Epub(path) as epub:
            metadata = epub.metadata
            opf_bytes = epub.read_file(epub.opf_path)
            fetched = fetcher(metadata, epub)
            if fetched.record is None:
                return BookOutcome(str(path), MATCH_NONE, from_cache=fetched.from_cache)
            plan = plan_enrichment(
                metadata, get_number_of_pages(opf_bytes), fetched.record, options, taxonomy
            )
            changed = [c.field for c in plan.changes if c.action == ACTION_CHANGED]
            skipped = [c.field for c in plan.changes if c.action == ACTION_SKIPPED]
            if not options.dry_run and (changed):
                _write(epub, plan)
            return BookOutcome(
                str(path),
                fetched.match,
                source=fetched.record.source,
                changed=changed,
                skipped=skipped,
                from_cache=fetched.from_cache,
            )
    except (EpubError, OSError, KeyError) as exc:
        return BookOutcome(str(path), MATCH_NONE, error=str(exc))


def _write(epub: Epub, plan: EnrichPlan) -> None:
    """Zapisuje metadane (Dublin Core + liczba stron) jednym przebiegiem OPF."""
    opf_path = epub.opf_path
    new_opf = plan.metadata.to_opf(epub.read_file(opf_path))
    if plan.page_count is not None:
        with_pages = set_number_of_pages(new_opf, plan.page_count)
        if with_pages is not None:
            new_opf = with_pages
    epub.write_file(opf_path, new_opf)
    epub.save()


def enrich_paths(
    paths: list[Path],
    options: EnrichOptions,
    *,
    fetcher: Fetcher | None = None,
    taxonomy: Taxonomy | None = None,
    on_progress: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[BookOutcome], EnrichSummary]:
    """Wzbogaca pliki/katalogi EPUB sekwencyjnie (wspólny rate limiter/cache LC).

    Args:
        paths: pliki i/lub katalogi (katalogi rozwijane do ``*.epub``).
        options: parametry wzbogacania.
        fetcher: własny dopasowywacz rekordów (testy); domyślnie :func:`default_fetcher`.
        taxonomy: taksonomia dla tagów; domyślnie ładowana, gdy ``want_tags``.
        on_progress: callback ``(zrobione, wszystkie)`` — postęp.
        should_cancel: callback zwracający ``True``, gdy przerwać (kooperacyjnie).

    Returns:
        Lista wyników per książka oraz zbiorcze :class:`EnrichSummary`.
    """
    epubs = collect_epubs(paths)
    fetch = fetcher if fetcher is not None else default_fetcher
    tax = taxonomy
    if tax is None and options.want_tags:
        tax = load_taxonomy()

    outcomes: list[BookOutcome] = []
    for index, path in enumerate(epubs):
        if should_cancel is not None and should_cancel():
            break
        outcomes.append(enrich_epub(path, options, fetch, tax))
        if on_progress is not None:
            on_progress(index + 1, len(epubs))
    return outcomes, EnrichSummary.from_outcomes(outcomes)


def collect_epubs(paths: list[Path]) -> list[Path]:
    """Rozwija ścieżki do listy plików ``.epub`` (katalogi → glob), bez duplikatów."""
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        candidates = sorted(path.glob("*.epub")) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.suffix.lower() != ".epub":
                continue
            key = str(candidate.resolve(strict=False))
            if key not in seen:
                seen.add(key)
                result.append(candidate)
    return result


# ── Domyślny fetcher (sieć przez bookmeta.chain) ────────────────────────────────────


def default_fetcher(metadata: Metadata, epub: Epub | None) -> FetchOutcome:
    """Dopasowuje rekord: ISBN (z metadanych/treści) → fuzzy tytuł/autor → brak.

    Ustawia ``from_cache`` na podstawie przyrostu trafień w cache providera LC.
    """
    before = chain.lubimyczytac_cache_hits()
    outcome = _match_record(metadata, epub)
    outcome.from_cache = chain.lubimyczytac_cache_hits() > before
    return outcome


def _match_record(metadata: Metadata, epub: Epub | None) -> FetchOutcome:
    """Realizuje kolejność dopasowania: ISBN → fuzzy → brak."""
    isbn = validate_isbn(metadata.identifier)
    if isbn is None and epub is not None:
        isbn = extract_isbn_from_epub(epub)
    if isbn:
        record = chain.fetch_by_isbn(isbn)
        match = MATCH_ISBN if record is not None else MATCH_NONE
        return FetchOutcome(record, match, record.source if record else "")
    if metadata.title:
        author = metadata.creators[0] if metadata.creators else ""
        candidates = chain.search_candidates(metadata.title, author)
        if candidates and candidates[0].score >= CONFIDENCE_THRESHOLD:
            record = chain.fetch_candidate(candidates[0])
            if record is not None:
                return FetchOutcome(record, MATCH_FUZZY, record.source)
    return FetchOutcome(None, MATCH_NONE)
