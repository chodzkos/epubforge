"""Testy taksonomii tagów (:mod:`epubforge.bookmeta.taxonomy`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.bookmeta.taxonomy import (
    MAX_TAGS,
    MappedTag,
    Taxonomy,
    limit_tags,
    load_taxonomy,
    map_subjects,
)


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    """Wbudowana taksonomia (bez pliku użytkownika)."""
    return load_taxonomy()


def test_builtin_loads_all_categories(taxonomy: Taxonomy) -> None:
    """Wbudowany plik ma tagi we wszystkich czterech kategoriach."""
    for category in ("gatunek", "epoka", "miejsce", "tematy"):
        assert taxonomy.canonical_tags(category), f"brak tagów w {category}"
    assert len(taxonomy.entries) >= 30


def test_map_real_subjects(taxonomy: Taxonomy) -> None:
    """Realne deskryptory BN i kategorie LC mapują się na kanoniczne tagi."""
    mapped = map_subjects(
        [
            "Fantasy",
            "Komiksy",
            "Czarodziejki i czarodzieje",
            "1939-1945",
            "Informatyka, matematyka",
        ],
        taxonomy,
    )
    tags = {m.tag for m in mapped.mapped}
    assert "fantasy" in tags
    assert "komiks" in tags
    assert "magia" in tags  # "Czarodziejki i czarodzieje" -> magia
    assert "II wojna światowa" in tags  # "1939-1945"
    assert "naukowa" in tags  # "Informatyka, matematyka"


def test_unmapped_go_to_proposals(taxonomy: Taxonomy) -> None:
    """Temat bez odpowiednika trafia do unmapped (propozycja poza taksonomią)."""
    mapped = map_subjects(["Wiedźmin", "Fantasy"], taxonomy)
    assert "Wiedźmin" in mapped.unmapped
    assert any(m.tag == "fantasy" for m in mapped.mapped)


def test_synonyms_collapse_to_canonical(taxonomy: Taxonomy) -> None:
    """Warianty synonimiczne sprowadzają się do jednego kanonu."""
    for variant in ("sci-fi", "SF", "science fiction", "Fantastyka naukowa"):
        assert taxonomy.resolve_canonical(variant, "gatunek") == "science fiction"


def test_map_dedups_by_canonical(taxonomy: Taxonomy) -> None:
    """Różne warianty tego samego tagu dają jeden wpis w wyniku."""
    mapped = map_subjects(["Science fiction", "sci-fi", "fantastyka naukowa"], taxonomy)
    assert [m.tag for m in mapped.mapped] == ["science fiction"]


def test_resolve_rejects_out_of_taxonomy(taxonomy: Taxonomy) -> None:
    """Tag spoza listy → None (dla walidacji AI)."""
    assert taxonomy.resolve_canonical("kuchnia molekularna", "gatunek") is None
    assert taxonomy.resolve_canonical("fantasy", "epoka") is None  # zła kategoria


def test_limit_tags_priority() -> None:
    """Limit zachowuje priorytet gatunek → epoka/miejsce → tematy."""
    tags = [
        MappedTag("space opera", "tematy"),
        MappedTag("science fiction", "gatunek"),
        MappedTag("kosmos", "miejsce"),
    ]
    limited = limit_tags(tags, limit=2)
    assert [t.tag for t in limited] == ["science fiction", "kosmos"]  # gatunek, potem miejsce


def test_limit_caps_at_max() -> None:
    """Limit domyślnie tnie do MAX_TAGS."""
    tags = [MappedTag(f"t{i}", "tematy") for i in range(20)]
    assert len(limit_tags(tags)) == MAX_TAGS


def test_user_file_takes_precedence(tmp_path: Path) -> None:
    """Podany plik użytkownika jest wczytywany zamiast wbudowanego."""
    custom = tmp_path / "taxonomy_pl.toml"
    custom.write_text(
        '[[gatunek]]\ntag = "moja kategoria"\nsynonyms = ["alias"]\nmaps = ["Źródło X"]\n',
        encoding="utf-8",
    )
    tax = load_taxonomy(custom)
    assert tax.canonical_tags("gatunek") == ["moja kategoria"]
    assert tax.resolve_canonical("alias", "gatunek") == "moja kategoria"
    assert tax.match("Źródło X") is not None
