"""Testy metadanych Dublin Core (:mod:`epubforge.core.metadata`)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from epubforge.core import Epub, Metadata

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"


# ── Odczyt ───────────────────────────────────────────────────────────────────


def test_from_opf_reads_fixture(opf_bytes: bytes) -> None:
    """from_opf wyciąga tytuł, autora, język i identyfikator z fixture."""
    meta = Metadata.from_opf(opf_bytes)
    assert meta.title == "Przykładowa książka"
    assert meta.creators == ["Jan Kowalski"]
    assert meta.language == "pl"
    assert meta.identifier == "urn:uuid:epubforge-sample-0001"


def test_from_opf_missing_fields_empty(opf_bytes: bytes) -> None:
    """Pola nieobecne w OPF pozostają puste."""
    meta = Metadata.from_opf(opf_bytes)
    assert meta.publisher == ""
    assert meta.date == ""
    assert meta.description == ""
    assert meta.subjects == []


# ── Zapis / roundtrip ──────────────────────────────────────────────────────────


def test_to_opf_roundtrip(opf_bytes: bytes) -> None:
    """Zapis i ponowny odczyt zwracają te same wartości."""
    meta = Metadata.from_opf(opf_bytes)
    meta.title = "Nowy tytuł"
    meta.publisher = "Wydawnictwo Testowe"
    meta.date = "2026-06-09"
    meta.subjects = ["fantastyka", "przygoda"]
    new_opf = meta.to_opf(opf_bytes)
    reloaded = Metadata.from_opf(new_opf)
    assert reloaded.title == "Nowy tytuł"
    assert reloaded.publisher == "Wydawnictwo Testowe"
    assert reloaded.date == "2026-06-09"
    assert reloaded.subjects == ["fantastyka", "przygoda"]


def test_polish_characters(opf_bytes: bytes) -> None:
    """Polskie znaki przechodzą zapis i odczyt bez uszkodzenia."""
    meta = Metadata.from_opf(opf_bytes)
    meta.title = "Zażółć gęślą jaźń ĄĘŁŻŹĆ"
    meta.creators = ["Świętosław Łąkowski"]
    new_opf = meta.to_opf(opf_bytes)
    reloaded = Metadata.from_opf(new_opf)
    assert reloaded.title == "Zażółć gęślą jaźń ĄĘŁŻŹĆ"
    assert reloaded.creators == ["Świętosław Łąkowski"]


def test_multiple_creators(opf_bytes: bytes) -> None:
    """Wielu autorów zapisywanych jako osobne dc:creator i czytanych w kolejności."""
    meta = Metadata.from_opf(opf_bytes)
    meta.creators = ["Autor Pierwszy", "Autor Drugi", "Autor Trzeci"]
    new_opf = meta.to_opf(opf_bytes)
    # Trzy fizyczne elementy dc:creator w wyniku.
    root = etree.fromstring(new_opf)
    creators = root.findall(f".//{{{DC_NS}}}creator")
    assert len(creators) == 3
    assert Metadata.from_opf(new_opf).creators == [
        "Autor Pierwszy",
        "Autor Drugi",
        "Autor Trzeci",
    ]


def test_xml_declaration_preserved(opf_bytes: bytes) -> None:
    """Wynik zaczyna się od deklaracji XML z kodowaniem utf-8."""
    out = Metadata().to_opf(opf_bytes)
    head = out[:60].lower()
    assert head.startswith(b"<?xml")
    assert b"utf-8" in head


def test_other_opf_elements_not_modified(opf_bytes: bytes) -> None:
    """Zmiana metadanych nie rusza manifestu ani spine."""
    before = etree.fromstring(opf_bytes)
    manifest_before = sorted(
        item.get("id") for item in before.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item")
    )
    spine_before = [
        ref.get("idref") for ref in before.findall(f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref")
    ]

    meta = Metadata.from_opf(opf_bytes)
    meta.title = "Cokolwiek innego"
    after = etree.fromstring(meta.to_opf(opf_bytes))
    manifest_after = sorted(
        item.get("id") for item in after.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item")
    )
    spine_after = [
        ref.get("idref") for ref in after.findall(f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref")
    ]

    assert manifest_after == manifest_before
    assert spine_after == spine_before


def test_identifier_id_attribute_preserved(opf_bytes: bytes) -> None:
    """Aktualizacja dc:identifier zachowuje jego atrybut id."""
    meta = Metadata.from_opf(opf_bytes)
    meta.identifier = "urn:uuid:nowy-id"
    root = etree.fromstring(meta.to_opf(opf_bytes))
    ident = root.find(f".//{{{DC_NS}}}identifier")
    assert ident is not None
    assert ident.get("id") == "bookid"
    assert ident.text == "urn:uuid:nowy-id"


# ── Integracja z Epub ──────────────────────────────────────────────────────────


def test_epub_metadata_getter(sample_epub: Path) -> None:
    """Epub.metadata zwraca metadane sparsowane z OPF."""
    with Epub(sample_epub) as epub:
        meta = epub.metadata
    assert meta.title == "Przykładowa książka"
    assert meta.creators == ["Jan Kowalski"]


def test_epub_metadata_setter_persists(sample_epub: Path) -> None:
    """Przypisanie Epub.metadata zapisuje zmiany na dysku (z backupem)."""
    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Tytuł po edycji"
        meta.creators = ["Pierwszy", "Drugi"]
        epub.metadata = meta
    # Ponowne otwarcie czyta zapisaną wartość.
    with Epub(sample_epub) as epub:
        reloaded = epub.metadata
    assert reloaded.title == "Tytuł po edycji"
    assert reloaded.creators == ["Pierwszy", "Drugi"]
    assert sample_epub.with_suffix(".epub.bak").is_file()


def test_epub_metadata_setter_keeps_spine(sample_epub: Path) -> None:
    """Zapis metadanych przez Epub nie psuje spine ani manifestu."""
    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Inny"
        epub.metadata = meta
        assert epub.spine == ["chapter1"]
        assert {item.id for item in epub.manifest} == {"nav", "chapter1"}
