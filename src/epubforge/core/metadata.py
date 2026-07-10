"""Metadane Dublin Core plików EPUB — odczyt i zapis.

Metadane EPUB-a żyją w sekcji ``<metadata>`` pliku OPF, w przestrzeni nazw
Dublin Core (``dc:``). Ten moduł czyta je do dataclassy :class:`Metadata`
i potrafi je z powrotem wstrzyknąć do istniejącego OPF-a, **nie ruszając**
pozostałych sekcji (``manifest``, ``spine``).

Backendem jest ``lxml`` — twarda zależność projektu. lxml zachowuje
deklaracje przestrzeni nazw i formatowanie znacznie wierniej niż stdlib,
co jest kluczowe przy edycji w miejscu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted

# Przestrzenie nazw wg specyfikacji OPF/Dublin Core.
DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"

# Pojedyncze pola Dublin Core: nazwa atrybutu dataclassy → lokalna nazwa tagu dc.
_SINGLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "title"),
    ("language", "language"),
    ("identifier", "identifier"),
    ("publisher", "publisher"),
    ("date", "date"),
    ("description", "description"),
)


# Identyfikator kolekcji EPUB 3 (refines wskazuje na ten id).
_COLLECTION_ID = "epubforge-series"

# Właściwość OPF przechowująca liczbę stron wydania papierowego (schema.org).
# Tylko EPUB 3 — składnia ``<meta property="...">`` nie istnieje w EPUB 2.
_NUMBER_OF_PAGES_PROPERTY = "schema:numberOfPages"


def _dc(tag: str) -> str:
    """Zwraca w pełni kwalifikowaną nazwę tagu Dublin Core (Clark notation)."""
    return f"{{{DC_NS}}}{tag}"


def _opf(tag: str) -> str:
    """Zwraca w pełni kwalifikowaną nazwę tagu OPF (Clark notation)."""
    return f"{{{OPF_NS}}}{tag}"


def _to_float(value: str | None) -> float | None:
    """Parsuje numer tomu na float; toleruje liczby całkowite, zwraca None gdy się nie da."""
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _format_index(value: float) -> str:
    """Formatuje numer tomu bez zbędnych zer (2.0 → '2', 1.5 → '1.5')."""
    return str(int(value)) if value.is_integer() else str(value)


def _read_series(root: etree._Element) -> tuple[str, float | None]:
    """Odczytuje serię z OPF, obsługując format Calibre (EPUB 2) i EPUB 3.

    Najpierw próbuje ``calibre:series`` (najczęstszy, kompatybilny), a gdy go
    brak — ``belongs-to-collection`` + ``group-position`` (standard EPUB 3).
    """
    metas = list(root.iterfind(f".//{_opf('meta')}"))

    # Wariant Calibre: <meta name="calibre:series" content="..."/>
    by_name = {m.get("name"): (m.get("content") or "") for m in metas if m.get("name")}
    calibre_series = by_name.get("calibre:series", "")
    if calibre_series:
        return calibre_series, _to_float(by_name.get("calibre:series_index"))

    # Wariant EPUB 3: <meta property="belongs-to-collection" id="..">Nazwa</meta>
    for meta in metas:
        if meta.get("property") != "belongs-to-collection":
            continue
        name = (meta.text or "").strip()
        if not name:
            continue
        collection_id = meta.get("id")
        index: float | None = None
        if collection_id:
            for refine in metas:
                if (
                    refine.get("refines") == f"#{collection_id}"
                    and refine.get("property") == "group-position"
                ):
                    index = _to_float(refine.text)
        return name, index

    return "", None


def _first_text(root: etree._Element, tag: str) -> str:
    """Zwraca tekst pierwszego elementu ``dc:<tag>`` lub pusty łańcuch."""
    el = root.find(f".//{_dc(tag)}")
    if el is not None and el.text:
        return el.text
    return ""


def _all_texts(root: etree._Element, tag: str) -> list[str]:
    """Zwraca teksty wszystkich elementów ``dc:<tag>`` (z pominięciem pustych)."""
    result: list[str] = []
    for el in root.iterfind(f".//{_dc(tag)}"):
        if el.text:
            result.append(el.text)
    return result


def set_number_of_pages(existing_opf: bytes, count: int) -> bytes | None:
    """Wpisuje liczbę stron wydania papierowego do OPF jako meta schema.org.

    Zapis dotyczy **wyłącznie EPUB 3** — element ``<meta property="...">`` nie
    istnieje w EPUB 2, więc dla starszych pakietów funkcja zwraca ``None`` (wywołujący
    powinien pominąć zapis z notą). Istniejące wystąpienia właściwości są usuwane
    przed dopisaniem nowego, więc operacja jest idempotentna.

    Args:
        existing_opf: surowa zawartość obecnego pliku OPF.
        count: liczba stron do zapisania (wartości ``<= 0`` są ignorowane → ``None``).

    Returns:
        Nowa zawartość OPF jako bajty UTF-8 albo ``None`` (EPUB 2, brak sekcji
        ``metadata`` lub niepoprawna liczba).
    """
    if count <= 0:
        return None
    root = parse_untrusted(existing_opf)
    if not str(root.get("version", "")).startswith("3"):
        return None
    metadata_el = root.find(f"{{{OPF_NS}}}metadata")
    if metadata_el is None:
        return None
    for meta in list(metadata_el.findall(_opf("meta"))):
        if meta.get("property") == _NUMBER_OF_PAGES_PROPERTY:
            metadata_el.remove(meta)
    meta_el = etree.SubElement(metadata_el, _opf("meta"))
    meta_el.set("property", _NUMBER_OF_PAGES_PROPERTY)
    meta_el.text = str(count)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


@dataclass
class Metadata:
    """Metadane Dublin Core książki EPUB.

    Attributes:
        title: tytuł (``dc:title``).
        creators: autorzy w kolejności występowania (``dc:creator`` x N).
        language: kod języka, np. ``pl`` (``dc:language``).
        identifier: identyfikator, np. ISBN/UUID (``dc:identifier``).
        publisher: wydawca (``dc:publisher``).
        date: data w formacie ISO 8601 (``dc:date``).
        description: opis (``dc:description``).
        subjects: tematy/tagi (``dc:subject`` x N).
        series: nazwa cyklu/serii (poza Dublin Core; format Calibre + EPUB 3).
        series_index: numer tomu (float, bywa ułamkowy jak 1.5); ``None`` = brak.
    """

    title: str = ""
    creators: list[str] = field(default_factory=list)
    language: str = "en"
    identifier: str = ""
    publisher: str = ""
    date: str = ""
    description: str = ""
    subjects: list[str] = field(default_factory=list)
    series: str = ""
    series_index: float | None = None

    @classmethod
    def from_opf(cls, opf_xml: bytes) -> Metadata:
        """Parsuje metadane z bajtów pliku OPF.

        Args:
            opf_xml: surowa zawartość pliku OPF (bajty, UTF-8).

        Returns:
            Wypełniona instancja :class:`Metadata`. Brakujące pola pozostają
            puste (``language`` domyślnie ``"en"`` tylko gdy nieobecny).
        """
        root = parse_untrusted(opf_xml)
        language = _first_text(root, "language")
        series, series_index = _read_series(root)
        return cls(
            title=_first_text(root, "title"),
            creators=_all_texts(root, "creator"),
            language=language or "en",
            identifier=_first_text(root, "identifier"),
            publisher=_first_text(root, "publisher"),
            date=_first_text(root, "date"),
            description=_first_text(root, "description"),
            subjects=_all_texts(root, "subject"),
            series=series,
            series_index=series_index,
        )

    def to_opf(self, existing_opf: bytes) -> bytes:
        """Wstrzykuje metadane do istniejącego OPF, zachowując resztę dokumentu.

        Sekcje ``manifest`` i ``spine`` oraz nieznane elementy nie są ruszane.
        Pola wielowartościowe (autorzy, tematy) są zastępowane w całości;
        pola pojedyncze są aktualizowane w miejscu (z zachowaniem atrybutów,
        np. ``id`` przy ``dc:identifier``).

        Args:
            existing_opf: surowa zawartość obecnego pliku OPF.

        Returns:
            Nowa zawartość OPF jako bajty UTF-8, z deklaracją XML.
        """
        root = parse_untrusted(existing_opf)
        metadata_el = root.find(f"{{{OPF_NS}}}metadata")
        if metadata_el is None:
            metadata_el = etree.SubElement(root, f"{{{OPF_NS}}}metadata")
            root.insert(0, metadata_el)

        # Pola pojedyncze — aktualizacja w miejscu (lub utworzenie gdy brak).
        for attr_name, tag in _SINGLE_FIELDS:
            value = getattr(self, attr_name)
            self._set_single(metadata_el, tag, value)

        # Pola wielowartościowe — zastąp wszystkie wystąpienia.
        self._set_multi(metadata_el, "creator", self.creators)
        self._set_multi(metadata_el, "subject", self.subjects)

        # Seria — Calibre (zawsze) + EPUB 3 (gdy package version 3.x).
        epub3 = str(root.get("version", "")).startswith("3")
        self._set_series(metadata_el, epub3=epub3)

        return etree.tostring(root, xml_declaration=True, encoding="utf-8")

    @staticmethod
    def _set_single(metadata_el: etree._Element, tag: str, value: str) -> None:
        """Ustawia tekst pierwszego ``dc:<tag>`` (tworzy element gdy brak)."""
        if not value:
            return
        el = metadata_el.find(_dc(tag))
        if el is None:
            el = etree.SubElement(metadata_el, _dc(tag))
        el.text = value

    @staticmethod
    def _set_multi(metadata_el: etree._Element, tag: str, values: list[str]) -> None:
        """Usuwa istniejące ``dc:<tag>`` i wstawia po jednym na każdą wartość."""
        for el in metadata_el.findall(_dc(tag)):
            metadata_el.remove(el)
        for value in values:
            etree.SubElement(metadata_el, _dc(tag)).text = value

    def _set_series(self, metadata_el: etree._Element, *, epub3: bool) -> None:
        """Zapisuje serię (Calibre + opcjonalnie EPUB 3); pusta seria = usunięcie.

        Najpierw usuwa wszystkie istniejące meta serii (oba formaty), żeby zapis
        był idempotentny i nie zostawiał osieroconych wpisów.
        """
        self._remove_series(metadata_el)
        if not self.series:
            return

        index_text = "" if self.series_index is None else _format_index(self.series_index)

        # Wariant Calibre — zawsze (kompatybilność z wieloma czytnikami).
        etree.SubElement(metadata_el, _opf("meta"), name="calibre:series", content=self.series)
        if index_text:
            etree.SubElement(
                metadata_el, _opf("meta"), name="calibre:series_index", content=index_text
            )

        # Wariant EPUB 3 — tylko dla pakietów 3.x.
        if epub3:
            collection = etree.SubElement(metadata_el, _opf("meta"))
            collection.set("property", "belongs-to-collection")
            collection.set("id", _COLLECTION_ID)
            collection.text = self.series

            ctype = etree.SubElement(metadata_el, _opf("meta"))
            ctype.set("refines", f"#{_COLLECTION_ID}")
            ctype.set("property", "collection-type")
            ctype.text = "series"

            if index_text:
                position = etree.SubElement(metadata_el, _opf("meta"))
                position.set("refines", f"#{_COLLECTION_ID}")
                position.set("property", "group-position")
                position.text = index_text

    @staticmethod
    def _remove_series(metadata_el: etree._Element) -> None:
        """Usuwa wszystkie meta serii (Calibre i EPUB 3) z sekcji metadanych."""
        for meta in list(metadata_el.findall(_opf("meta"))):
            name = meta.get("name")
            prop = meta.get("property")
            is_calibre = name in {"calibre:series", "calibre:series_index"}
            is_epub3 = prop in {"belongs-to-collection", "collection-type", "group-position"}
            if is_calibre or is_epub3:
                metadata_el.remove(meta)
