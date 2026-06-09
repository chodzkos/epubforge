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


def _dc(tag: str) -> str:
    """Zwraca w pełni kwalifikowaną nazwę tagu Dublin Core (Clark notation)."""
    return f"{{{DC_NS}}}{tag}"


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
    """

    title: str = ""
    creators: list[str] = field(default_factory=list)
    language: str = "en"
    identifier: str = ""
    publisher: str = ""
    date: str = ""
    description: str = ""
    subjects: list[str] = field(default_factory=list)

    @classmethod
    def from_opf(cls, opf_xml: bytes) -> Metadata:
        """Parsuje metadane z bajtów pliku OPF.

        Args:
            opf_xml: surowa zawartość pliku OPF (bajty, UTF-8).

        Returns:
            Wypełniona instancja :class:`Metadata`. Brakujące pola pozostają
            puste (``language`` domyślnie ``"en"`` tylko gdy nieobecny).
        """
        root = etree.fromstring(opf_xml)
        language = _first_text(root, "language")
        return cls(
            title=_first_text(root, "title"),
            creators=_all_texts(root, "creator"),
            language=language or "en",
            identifier=_first_text(root, "identifier"),
            publisher=_first_text(root, "publisher"),
            date=_first_text(root, "date"),
            description=_first_text(root, "description"),
            subjects=_all_texts(root, "subject"),
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
        root = etree.fromstring(existing_opf)
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
