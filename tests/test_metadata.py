"""Testy metadanych Dublin Core (:mod:`epubforge.core.metadata`)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from epubforge.cli.main import main
from epubforge.core import (
    Epub,
    Metadata,
    get_number_of_pages,
    remove_number_of_pages,
    set_number_of_pages,
    supports_number_of_pages,
)

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"


def _required_attr(element: etree._Element, name: str) -> str:
    """Zwraca wymagany atrybut XML z asercją pomocną też dla type checkera."""
    value = element.get(name)
    assert value is not None
    return value


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
        _required_attr(item, "id")
        for item in before.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item")
    )
    spine_before = [
        ref.get("idref") for ref in before.findall(f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref")
    ]

    meta = Metadata.from_opf(opf_bytes)
    meta.title = "Cokolwiek innego"
    after = etree.fromstring(meta.to_opf(opf_bytes))
    manifest_after = sorted(
        _required_attr(item, "id")
        for item in after.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item")
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


def test_epub_metadata_setter_updates_memory_without_persisting(sample_epub: Path) -> None:
    """Setter aktualizuje OPF w buforze, ale nie zapisuje źródła ani backupu."""
    source_before = sample_epub.read_bytes()

    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Tytuł po edycji"
        meta.creators = ["Pierwszy", "Drugi"]
        epub.metadata = meta

        assert epub.metadata.title == "Tytuł po edycji"
        assert epub.metadata.creators == ["Pierwszy", "Drugi"]
        assert epub.opf_path in epub.pending_changes().modified
        assert sample_epub.read_bytes() == source_before
        assert not sample_epub.with_suffix(".epub.bak").exists()

        with Epub(sample_epub) as reopened:
            assert reopened.metadata.title == "Przykładowa książka"

    with Epub(sample_epub) as reopened_after_close:
        assert reopened_after_close.metadata.title == "Przykładowa książka"


def test_epub_metadata_explicit_save_persists(sample_epub: Path) -> None:
    """Jawne save utrwala metadata i tworzy backup przy nadpisaniu."""
    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Tytuł po edycji"
        epub.metadata = meta
        epub.save()

    with Epub(sample_epub) as reopened:
        assert reopened.metadata.title == "Tytuł po edycji"
    assert sample_epub.with_suffix(".epub.bak").is_file()


def test_epub_metadata_save_as_keeps_source_unchanged(sample_epub: Path, tmp_path: Path) -> None:
    """Jawny save-as zapisuje metadata do kopii bez modyfikowania źródła."""
    source_before = sample_epub.read_bytes()
    output = tmp_path / "metadata-copy.epub"

    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Tytuł w kopii"
        epub.metadata = meta
        epub.save(output)

    assert sample_epub.read_bytes() == source_before
    with Epub(sample_epub) as source:
        assert source.metadata.title == "Przykładowa książka"
    with Epub(output) as copied:
        assert copied.metadata.title == "Tytuł w kopii"


def test_epub_metadata_multiple_assignments_last_one_wins(sample_epub: Path) -> None:
    """Kilka przypisań pozostaje w buforze, a jawny save utrwala ostatnie."""
    with Epub(sample_epub) as epub:
        first = epub.metadata
        first.title = "Pierwszy tytuł"
        epub.metadata = first
        second = epub.metadata
        second.title = "Ostatni tytuł"
        epub.metadata = second
        assert epub.metadata.title == "Ostatni tytuł"
        epub.save()

    with Epub(sample_epub) as reopened:
        assert reopened.metadata.title == "Ostatni tytuł"


def test_epub_metadata_setter_keeps_spine(sample_epub: Path) -> None:
    """Buforowana zmiana metadanych nie psuje spine ani manifestu."""
    with Epub(sample_epub) as epub:
        meta = epub.metadata
        meta.title = "Inny"
        epub.metadata = meta
        assert epub.spine == ["chapter1"]
        assert {item.id for item in epub.manifest} == {"nav", "chapter1"}


# ── Seria / cykl (EPUB 2 Calibre + EPUB 3) ──────────────────────────────────────

_CALIBRE_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:x</dc:identifier>
    <dc:title>Krew elfów</dc:title>
    <dc:creator>Andrzej Sapkowski</dc:creator>
    <meta name="calibre:series" content="Wiedźmin"/>
    <meta name="calibre:series_index" content="3"/>
  </metadata>
  <manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="a"/></spine>
</package>
""".encode()

_EPUB3_SERIES_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:x</dc:identifier>
    <dc:title>Krew elfów</dc:title>
    <meta property="belongs-to-collection" id="c01">Wiedźmin</meta>
    <meta refines="#c01" property="collection-type">series</meta>
    <meta refines="#c01" property="group-position">2</meta>
  </metadata>
  <manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="a"/></spine>
</package>
""".encode()


def test_read_series_calibre_format() -> None:
    """Odczyt serii z formatu Calibre (EPUB 2)."""
    meta = Metadata.from_opf(_CALIBRE_OPF)
    assert meta.series == "Wiedźmin"
    assert meta.series_index == 3.0


def test_read_series_epub3_format() -> None:
    """Odczyt serii z formatu EPUB 3 (belongs-to-collection)."""
    meta = Metadata.from_opf(_EPUB3_SERIES_OPF)
    assert meta.series == "Wiedźmin"
    assert meta.series_index == 2.0


def test_no_series_yields_empty(opf_bytes: bytes) -> None:
    """Brak serii w OPF → series='' i series_index=None."""
    meta = Metadata.from_opf(opf_bytes)
    assert meta.series == ""
    assert meta.series_index is None


def test_series_roundtrip_epub3(opf_bytes: bytes) -> None:
    """Zapis serii + numeru i ponowny odczyt zwraca te same wartości."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Wiedźmin"
    meta.series_index = 2.0
    reloaded = Metadata.from_opf(meta.to_opf(opf_bytes))
    assert reloaded.series == "Wiedźmin"
    assert reloaded.series_index == 2.0


def test_series_index_float_preserved(opf_bytes: bytes) -> None:
    """Numer tomu ułamkowy (1.5) przechodzi roundtrip."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Cykl"
    meta.series_index = 1.5
    out = meta.to_opf(opf_bytes)
    assert b'content="1.5"' in out  # bez zbędnych zer
    assert Metadata.from_opf(out).series_index == 1.5


def test_series_index_int_without_trailing_zero(opf_bytes: bytes) -> None:
    """Numer całkowity zapisywany bez '.0' (2.0 → '2')."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Cykl"
    meta.series_index = 2.0
    out = meta.to_opf(opf_bytes)
    assert b'content="2"' in out
    assert b'content="2.0"' not in out


def test_to_opf_writes_both_formats_for_epub3(opf_bytes: bytes) -> None:
    """Dla EPUB 3 zapisywane są oba warianty: Calibre i belongs-to-collection."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Wiedźmin"
    meta.series_index = 2.0
    root = etree.fromstring(meta.to_opf(opf_bytes))
    metas = root.findall(f".//{{{OPF_NS}}}meta")
    names = {m.get("name") for m in metas}
    props = {m.get("property") for m in metas}
    assert "calibre:series" in names
    assert "belongs-to-collection" in props


def test_to_opf_calibre_only_for_epub2() -> None:
    """Dla EPUB 2 zapisywany jest tylko wariant Calibre (bez belongs-to-collection)."""
    meta = Metadata.from_opf(_CALIBRE_OPF)
    meta.series = "Inny Cykl"
    root = etree.fromstring(meta.to_opf(_CALIBRE_OPF))
    metas = root.findall(f".//{{{OPF_NS}}}meta")
    props = {m.get("property") for m in metas}
    assert "belongs-to-collection" not in props
    assert any(m.get("name") == "calibre:series" for m in metas)


def test_empty_series_removes_meta() -> None:
    """Puste series usuwa istniejące meta serii (oba formaty)."""
    # Start z OPF mającym serię w obu formatach.
    meta = Metadata.from_opf(_EPUB3_SERIES_OPF)
    meta.series = ""
    meta.series_index = None
    root = etree.fromstring(meta.to_opf(_EPUB3_SERIES_OPF))
    metas = root.findall(f".//{{{OPF_NS}}}meta")
    assert all(m.get("property") != "belongs-to-collection" for m in metas)
    assert all(m.get("name") not in {"calibre:series", "calibre:series_index"} for m in metas)


def test_series_polish_chars(opf_bytes: bytes) -> None:
    """Polskie znaki w nazwie cyklu przechodzą roundtrip."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Zażółć gęślą"
    meta.series_index = 1.0
    assert Metadata.from_opf(meta.to_opf(opf_bytes)).series == "Zażółć gęślą"


def test_series_write_keeps_other_metadata(opf_bytes: bytes) -> None:
    """Zapis serii nie rusza tytułu, autorów ani manifestu/spine."""
    meta = Metadata.from_opf(opf_bytes)
    meta.series = "Wiedźmin"
    meta.series_index = 2.0
    reloaded = Metadata.from_opf(meta.to_opf(opf_bytes))
    assert reloaded.title == "Przykładowa książka"
    assert reloaded.creators == ["Jan Kowalski"]
    root = etree.fromstring(meta.to_opf(opf_bytes))
    assert root.find(f".//{{{OPF_NS}}}manifest") is not None
    assert root.find(f".//{{{OPF_NS}}}spine") is not None


def test_set_number_of_pages_epub3(opf_bytes: bytes) -> None:
    """EPUB 3: liczba stron zapisywana jako meta schema:numberOfPages."""
    result = set_number_of_pages(opf_bytes, 330)
    assert result is not None
    root = etree.fromstring(result)
    metas = root.findall(f".//{{{OPF_NS}}}meta")
    pages = [m for m in metas if m.get("property") == "schema:numberOfPages"]
    assert len(pages) == 1
    assert pages[0].text == "330"
    assert get_number_of_pages(result) == 330


def test_get_number_of_pages_missing(opf_bytes: bytes) -> None:
    """Brak właściwości w EPUB 3 daje jednoznaczne ``None``."""
    assert supports_number_of_pages(opf_bytes)
    assert get_number_of_pages(opf_bytes) is None


def test_number_of_pages_requires_opf_package_root() -> None:
    """Sam atrybut version poza korzeniem package nie oznacza EPUB 3."""
    not_opf = b'<metadata xmlns="http://www.idpf.org/2007/opf" version="3.0"/>'
    assert not supports_number_of_pages(not_opf)


def test_set_number_of_pages_idempotent(opf_bytes: bytes) -> None:
    """Ponowny zapis nie mnoży wpisów — nadpisuje istniejący."""
    once = set_number_of_pages(opf_bytes, 100)
    assert once is not None
    twice = set_number_of_pages(once, 200)
    assert twice is not None
    same_again = set_number_of_pages(twice, 200)
    assert same_again == twice
    root = etree.fromstring(twice)
    pages = [
        m
        for m in root.findall(f".//{{{OPF_NS}}}meta")
        if m.get("property") == "schema:numberOfPages"
    ]
    assert len(pages) == 1
    assert pages[0].text == "200"


def test_set_number_of_pages_epub2_skipped(epub2_epub: Path) -> None:
    """EPUB 2: brak składni meta property → zwraca None (zapis pominięty)."""
    with Epub(epub2_epub) as epub:
        opf = epub.read_file(epub.opf_path)
    assert not supports_number_of_pages(opf)
    assert get_number_of_pages(opf) is None
    assert set_number_of_pages(opf, 330) is None
    assert remove_number_of_pages(opf) is None


def test_set_number_of_pages_invalid_count(opf_bytes: bytes) -> None:
    """Niepoprawna liczba stron (<= 0) → None."""
    assert set_number_of_pages(opf_bytes, 0) is None
    assert set_number_of_pages(opf_bytes, -5) is None
    assert set_number_of_pages(opf_bytes, True) is None
    assert set_number_of_pages(opf_bytes, 1.5) is None  # type: ignore[arg-type]


def test_remove_number_of_pages_is_idempotent_and_keeps_foreign_metadata(
    opf_bytes: bytes,
) -> None:
    """Usuwanie stron nie rusza obcych metadanych i drugi przebieg jest no-opem."""
    root = etree.fromstring(opf_bytes)
    metadata = root.find(f"{{{OPF_NS}}}metadata")
    assert metadata is not None
    foreign = etree.SubElement(metadata, f"{{{OPF_NS}}}meta")
    foreign.set("property", "example:foreign")
    foreign.text = "zachowaj"
    source = etree.tostring(root, xml_declaration=True, encoding="utf-8")
    with_pages = set_number_of_pages(source, 123)
    assert with_pages is not None

    once = remove_number_of_pages(with_pages)
    assert once is not None
    twice = remove_number_of_pages(once)
    assert twice == once
    assert get_number_of_pages(once) is None
    after = etree.fromstring(once)
    kept = [
        meta
        for meta in after.findall(f".//{{{OPF_NS}}}meta")
        if meta.get("property") == "example:foreign"
    ]
    assert len(kept) == 1
    assert kept[0].text == "zachowaj"


def test_cli_meta_sets_series(sample_epub: Path) -> None:
    """CLI `meta --series --series-index` zapisuje cykl do EPUB."""
    code = main(["meta", str(sample_epub), "--series", "Wiedźmin", "--series-index", "2"])
    assert code == 0
    with Epub(sample_epub) as epub:
        meta = epub.metadata
    assert meta.series == "Wiedźmin"
    assert meta.series_index == 2.0
