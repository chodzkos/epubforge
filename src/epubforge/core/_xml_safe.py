"""Utwardzony parser XML dla niezaufanej treści z plików EPUB.

EPUB to archiwum dostarczone przez użytkownika — jego XML (``container.xml``,
OPF, NCX, XHTML) jest **niezaufany**. Domyślny parser lxml rozwija encje ogólne
i potrafi sięgnąć po zasoby zewnętrzne (DTD, encje ``SYSTEM file://``, sieć), co
otwiera projekt na ataki XXE oraz rozwijanie encji (billion laughs / kwadratowe
rozdmuchanie encji rekurencyjnych).

Ten moduł to **JEDYNE zatwierdzone miejsce** parsowania treści EPUB — poza nim
w kodzie nie tworzymy ``etree.XMLParser`` ani nie wołamy ``etree.fromstring``/
``etree.parse`` (kryterium: wyszukanie tych wywołań poza tym modułem musi być
puste). Dostępne tryby: :func:`parse_untrusted` (strict/recover → element),
:func:`parse_untrusted_document` (recover → ``(element, doctype)``) oraz
:func:`parse_untrusted_tree` (recover → ``ElementTree``). Każdy przyjmuje
``max_bytes`` (domyślnie :data:`DEFAULT_MAX_XML_BYTES`, sprzężony z limitem wpisu
tekstowego EPUB), odrzucając zbyt duży dokument przez :class:`XmlSecurityError`.

Utwardzenie:

* ``resolve_entities=False`` — encje ogólne z DTD nie są rozwijane (pozostają
  jako referencje), więc bomby typu billion laughs się nie „rozdmuchują", a encje
  ``SYSTEM`` nie są dereferencjonowane. Predefiniowane encje XML (``&amp;``,
  ``&lt;``, ``&gt;``, ``&quot;``, ``&apos;``) są nadal poprawnie interpretowane —
  obsługuje je sam lexer, niezależnie od tej flagi;
* ``no_network=True`` — parser nie wykona żadnego żądania sieciowego (blokuje
  zewnętrzne DTD/encje po URL-u);
* ``load_dtd=False`` — zewnętrzny podzbiór DTD nie jest wczytywany;
* ``dtd_validation=False`` — brak walidacji względem DTD (jawnie, dla czytelności).
"""

from __future__ import annotations

from io import BytesIO
from typing import cast

from lxml import etree

from epubforge.core._archive import DEFAULT_LIMITS

# Domyślny limit rozmiaru parsowanego XML — sprzężony z limitem wpisu tekstowego
# EPUB (:data:`ArchiveLimits.max_text_size`), więc „duży XML" jest odcinany tak
# samo przy odczycie wpisu, jak i tu (defense-in-depth). ``None`` = bez limitu.
DEFAULT_MAX_XML_BYTES = DEFAULT_LIMITS.max_text_size


class XmlSecurityError(ValueError):
    """Dokument XML odrzucony przez politykę bezpieczeństwa.

    Dziedziczy po :class:`ValueError` — kod, który dotąd łapał ``ValueError`` z
    :func:`parse_untrusted_document` (pusty/nieparsowalny dokument), nadal działa.
    Zgłaszane przy przekroczeniu limitu rozmiaru oraz dla pustego wyniku recover.
    """


def _check_size(data: bytes, max_bytes: int | None) -> None:
    """Odrzuca zbyt duży dokument PRZED parsowaniem (ochrona przed bombą „dużego XML")."""
    if max_bytes is not None and len(data) > max_bytes:
        raise XmlSecurityError(
            f"Dokument XML przekracza limit rozmiaru ({len(data)} > {max_bytes} B)."
        )


def hardened_parser(*, recover: bool = False) -> etree.XMLParser:
    """Buduje parser lxml odporny na XXE i rozwijanie encji.

    Zwraca świeżą instancję przy każdym wywołaniu — parsery lxml nie są
    bezpieczne do współdzielenia między wątkami, więc nie trzymamy globalu.

    Args:
        recover: gdy ``True``, parser odzyskuje drobne nieścisłości składniowe
            (przydatne dla „brudnych" dokumentów XHTML z EPUB-ów). Utwardzenie
            (encje/DTD/sieć) pozostaje bez zmian — ``recover`` dotyczy wyłącznie
            odzyskiwania po błędach składni, nie osłabia ochrony XXE.

    Returns:
        Skonfigurowany, utwardzony :class:`lxml.etree.XMLParser`.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        recover=recover,
    )


def parse_untrusted(
    data: bytes, *, recover: bool = False, max_bytes: int | None = DEFAULT_MAX_XML_BYTES
) -> etree._Element:
    """Parsuje niezaufany dokument XML z pliku EPUB utwardzonym parserem.

    Jedyne zatwierdzone miejsce parsowania treści EPUB (poza tym modułem nie tworzymy
    ``XMLParser``/``fromstring``). Utwardzenie: ``resolve_entities=False``,
    ``no_network=True``, ``load_dtd=False``, ``dtd_validation=False`` (doctype jest
    zachowany, ale NIE wykonywany).

    Args:
        data: surowe bajty dokumentu XML (np. ``container.xml``, OPF, XHTML).
        recover: ``False`` = tryb strict (błędna składnia → ``XMLSyntaxError``);
            ``True`` = best-effort dla „brudnych" XHTML z EPUB-ów.
        max_bytes: górny limit rozmiaru (domyślnie :data:`DEFAULT_MAX_XML_BYTES`,
            sprzężony z limitem wpisu EPUB); ``None`` wyłącza kontrolę.

    Returns:
        Element główny sparsowanego drzewa.

    Raises:
        lxml.etree.XMLSyntaxError: w trybie strict, gdy dokument jest niepoprawny.
        XmlSecurityError: gdy przekroczono ``max_bytes`` albo wynik recover jest pusty.
    """
    _check_size(data, max_bytes)
    root = cast(
        "etree._Element | None",
        etree.fromstring(data, parser=hardened_parser(recover=recover)),
    )
    if root is None:
        raise XmlSecurityError("Pusty lub nieparsowalny dokument XML.")
    return root


def parse_untrusted_document(
    data: bytes, *, max_bytes: int | None = DEFAULT_MAX_XML_BYTES
) -> tuple[etree._Element, str]:
    """Parsuje niezaufany dokument XHTML/HTML (tryb recover) i zwraca DOCTYPE.

    Przeznaczone dla treści dokumentów EPUB, które w praktyce bywają niepoprawne
    składniowo — stąd tryb recover. Zwraca też DOCTYPE (zachowany, nie wykonany),
    by serializacja mogła go odtworzyć (``tostring`` gubi doctype bez jawnego
    argumentu — patrz :func:`serialize_document`).

    Args:
        data: surowe bajty dokumentu XHTML/HTML.
        max_bytes: górny limit rozmiaru (jak w :func:`parse_untrusted`).

    Returns:
        Krotka ``(element_główny, doctype)``; ``doctype`` jest pustym łańcuchem,
        gdy dokument go nie miał.

    Raises:
        XmlSecurityError: przy przekroczeniu ``max_bytes`` lub pustym wyniku recover.
    """
    root = parse_untrusted(data, recover=True, max_bytes=max_bytes)
    doctype = getattr(root.getroottree().docinfo, "doctype", "") or ""
    return root, doctype


def parse_untrusted_tree(
    data: bytes, *, max_bytes: int | None = DEFAULT_MAX_XML_BYTES
) -> etree._ElementTree:
    """Parsuje niezaufany XML do :class:`ElementTree` (recover) — dla kodu na drzewie.

    Wariant dla miejsc operujących na całym drzewie (``getroot()``, serializacja z
    zachowaniem DOCTYPE dla dokumentu). Utwardzenie identyczne jak w
    :func:`parse_untrusted`.

    Raises:
        XmlSecurityError: przy przekroczeniu ``max_bytes``.
    """
    _check_size(data, max_bytes)
    return etree.parse(BytesIO(data), parser=hardened_parser(recover=True))


def serialize_document(root: etree._Element, doctype: str = "") -> bytes:
    """Serializuje element do bajtów z deklaracją XML i (opcjonalnym) DOCTYPE.

    Wzorzec z ``toc/_xml.serialize_xml`` — jawny ``doctype`` jest konieczny, bo
    ``etree.tostring`` gubi DOCTYPE bez tego argumentu.
    """
    if doctype:
        return etree.tostring(root, xml_declaration=True, encoding="utf-8", doctype=doctype)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")
