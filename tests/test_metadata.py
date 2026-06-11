"""Testy metadanych Dublin Core (:mod:`epubforge.core.metadata`)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from epubforge.cli.main import main
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


def test_cli_meta_sets_series(sample_epub: Path) -> None:
    """CLI `meta --series --series-index` zapisuje cykl do EPUB."""
    code = main(["meta", str(sample_epub), "--series", "Wiedźmin", "--series-index", "2"])
    assert code == 0
    with Epub(sample_epub) as epub:
        meta = epub.metadata
    assert meta.series == "Wiedźmin"
    assert meta.series_index == 2.0
