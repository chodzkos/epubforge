"""Kaskada tagowania — łączy taksonomię (deterministycznie) z AI (opt-in).

Trzy źródła w kolejności:

1. **mapowanie taksonomii** na tematach z providerów (deskryptory BN, kategorie
   LC/GB) — zawsze, bez AI;
2. **AI na opisie + spisie treści** — tylko gdy tagów z kroku 1 jest mniej niż 3;
3. **AI na próbce treści** (początek spine) — tylko gdy nie ma opisu.

AI jest zawsze opcjonalne: brak/awaria endpointu → krok 1 działa dalej, a błąd jest
raportowany do GUI (:class:`TaggingResult.ai_error`). Wynik to lista propozycji z
kategorią i źródłem; zapis do ``dc:subject`` wg polityki scalania.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from epubforge.bookmeta.ai import AIConfig, AIError, TagSuggestion, UrlOpen, suggest_tags
from epubforge.bookmeta.taxonomy import Taxonomy, limit_tags, map_subjects

if TYPE_CHECKING:
    from epubforge.core.epub import Epub

# Polityki scalania proponowanych tagów z istniejącymi ``dc:subject``.
MERGE_POLICIES: tuple[str, ...] = ("keep", "append", "replace")
DEFAULT_POLICY = "append"

# Próg z kroku 2 kaskady: poniżej tylu tagów deterministycznych sięgamy po AI.
_MIN_DETERMINISTIC_TAGS = 3
# Domyślny limit słów próbki treści dla AI (krok 3).
_SAMPLE_MAX_WORDS = 5000

# Źródła propozycji (do wyświetlenia w GUI).
SOURCE_TAXONOMY = "taksonomia"
SOURCE_AI = "AI"

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class TagProposal:
    """Pojedyncza propozycja tagu do zapisu w ``dc:subject``.

    Attributes:
        tag: proponowany tag (kanoniczny lub otwarty byt).
        category: kategoria (``gatunek``/``epoka``/``miejsce``/``tematy``/``postać``/
            ``organizacja``/``poza taksonomią``).
        source: skąd pochodzi (:data:`SOURCE_TAXONOMY` / :data:`SOURCE_AI`).
    """

    tag: str
    category: str
    source: str


@dataclass
class TaggingResult:
    """Wynik kaskady tagowania.

    Attributes:
        proposals: propozycje tagów (zdeduplikowane, w kolejności priorytetu).
        ai_used: czy skorzystano z AI.
        ai_error: komunikat, gdy AI zawiodło (pusty, gdy OK lub AI nieużywane).
    """

    proposals: list[TagProposal] = field(default_factory=list)
    ai_used: bool = False
    ai_error: str = ""


def suggest_tags_cascade(
    subjects: list[str],
    description: str,
    toc: str,
    taxonomy: Taxonomy,
    ai_config: AIConfig,
    *,
    content_sample: str = "",
    use_ai: bool = True,
    urlopen: UrlOpen | None = None,
) -> TaggingResult:
    """Uruchamia kaskadę tagowania (taksonomia + opcjonalnie AI).

    Args:
        subjects: surowe tematy z metadanych/providerów (deskryptory BN, kategorie LC/GB).
        description: opis książki (sterują nim kroki 2 i 3).
        toc: spis treści (tytuły rozdziałów) — wejście AI kroku 2.
        taxonomy: załadowana taksonomia.
        ai_config: konfiguracja backendu AI.
        content_sample: próbka treści dla kroku 3 (gdy brak opisu).
        use_ai: czy w ogóle wolno użyć AI (opt-in z GUI).
        urlopen: atrapa ``urlopen`` do testów.

    Returns:
        :class:`TaggingResult` z propozycjami i statusem AI.
    """
    mapped = map_subjects(subjects, taxonomy)
    proposals: list[TagProposal] = [
        TagProposal(tag=m.tag, category=m.category, source=SOURCE_TAXONOMY)
        for m in limit_tags(mapped.mapped)
    ]
    result = TaggingResult(proposals=proposals)
    if not use_ai:
        return result

    if len(proposals) < _MIN_DETERMINISTIC_TAGS:
        _run_ai_stage(result, description, toc, "", taxonomy, ai_config, urlopen)
    if not description and content_sample and not result.ai_error:
        _run_ai_stage(result, "", toc, content_sample, taxonomy, ai_config, urlopen)
    return result


def apply_policy(
    existing: list[str], selected: list[str], policy: str = DEFAULT_POLICY
) -> list[str]:
    """Scala wybrane tagi z istniejącymi ``dc:subject`` wg polityki.

    * ``keep`` — zachowaj istniejące bez zmian, gdy jakieś są; inaczej użyj wybranych;
    * ``append`` (domyślnie) — istniejące + wybrane (bez duplikatów);
    * ``replace`` — tylko wybrane (istniejące odrzucone).

    Args:
        existing: obecne tagi (``dc:subject``).
        selected: tagi wybrane przez użytkownika.
        policy: jedna z :data:`MERGE_POLICIES` (nieznana → ``append``).

    Returns:
        Nowa, zdeduplikowana lista tagów.
    """
    if policy == "replace":
        return _dedup(selected)
    if policy == "keep":
        return _dedup(existing) if existing else _dedup(selected)
    return _dedup([*existing, *selected])


def extract_content_sample(epub: Epub, max_words: int = _SAMPLE_MAX_WORDS) -> str:
    """Zwraca próbkę tekstu z początku spine (do klasyfikacji AI bez opisu).

    Czyta kolejne dokumenty spine, usuwa znaczniki HTML i skleja tekst do
    ``max_words`` słów. Odczyt defensywny — brakujący dokument jest pomijany.
    """
    manifest_by_id = {item.id: item for item in epub.manifest}
    opf_dir = epub.opf_dir()
    words: list[str] = []
    for idref in epub.spine:
        item = manifest_by_id.get(idref)
        if item is None:
            continue
        internal = posixpath.join(opf_dir, item.href) if opf_dir else item.href
        try:
            data = epub.read_file(internal)
        except (KeyError, OSError):
            continue
        text = _TAG_RE.sub(" ", data.decode("utf-8", "replace"))
        words.extend(text.split())
        if len(words) >= max_words:
            break
    return " ".join(words[:max_words])


def _run_ai_stage(
    result: TaggingResult,
    description: str,
    toc: str,
    sample_text: str,
    taxonomy: Taxonomy,
    ai_config: AIConfig,
    urlopen: UrlOpen | None,
) -> None:
    """Wykonuje jeden krok AI i dokłada propozycje do wyniku (błąd → zapis w result)."""
    try:
        suggestion = suggest_tags(
            description, toc, taxonomy, ai_config, sample_text=sample_text, urlopen=urlopen
        )
    except AIError as exc:
        result.ai_error = str(exc)
        return
    result.ai_used = True
    _merge_suggestion(result.proposals, suggestion)


def _merge_suggestion(proposals: list[TagProposal], suggestion: TagSuggestion) -> None:
    """Dokłada tagi AI do listy propozycji (bez duplikatów po nazwie tagu)."""
    known = {p.tag for p in proposals}
    for category in ("gatunek", "epoka", "miejsce", "tematy"):
        for tag in getattr(suggestion, category):
            if tag not in known:
                known.add(tag)
                proposals.append(TagProposal(tag=tag, category=category, source=SOURCE_AI))
    for tag in suggestion.postacie:
        if tag not in known:
            known.add(tag)
            proposals.append(TagProposal(tag=tag, category="postać", source=SOURCE_AI))
    for tag in suggestion.organizacje:
        if tag not in known:
            known.add(tag)
            proposals.append(TagProposal(tag=tag, category="organizacja", source=SOURCE_AI))


def _dedup(tags: list[str]) -> list[str]:
    """Usuwa duplikaty tagów, zachowując kolejność."""
    result: list[str] = []
    for tag in tags:
        cleaned = " ".join(tag.split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result
