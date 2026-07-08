"""Utwardzony parser XML dla niezaufanej treści z plików EPUB.

EPUB to archiwum dostarczone przez użytkownika — jego XML (``container.xml``,
OPF, NCX, XHTML) jest **niezaufany**. Domyślny parser lxml rozwija encje ogólne
i potrafi sięgnąć po zasoby zewnętrzne (DTD, encje ``SYSTEM file://``, sieć), co
otwiera projekt na ataki XXE oraz rozwijanie encji (billion laughs / kwadratowe
rozdmuchanie encji rekurencyjnych).

Ten moduł centralizuje **jedną** utwardzoną konfigurację parsera i udostępnia ją
wszystkim ścieżkom parsującym treść EPUB, tak by hardening nie rozjeżdżał się
między modułami (wcześniej część miejsc parsowała bez zabezpieczeń).

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

from typing import cast

from lxml import etree


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


def parse_untrusted(data: bytes) -> etree._Element:
    """Parsuje niezaufany dokument XML z pliku EPUB utwardzonym parserem.

    Args:
        data: surowe bajty dokumentu XML (np. ``container.xml`` lub OPF).

    Returns:
        Element główny sparsowanego drzewa.

    Raises:
        lxml.etree.XMLSyntaxError: gdy dokument jest niepoprawny składniowo.
    """
    return etree.fromstring(data, parser=hardened_parser())


def parse_untrusted_document(data: bytes) -> tuple[etree._Element, str]:
    """Parsuje niezaufany dokument XHTML/HTML (tryb recover) i zwraca DOCTYPE.

    Przeznaczone dla treści dokumentów EPUB, które w praktyce bywają niepoprawne
    składniowo — stąd ``recover=True`` (utwardzenie bez zmian). Zwraca też DOCTYPE,
    by serializacja mogła go zachować (``tostring`` gubi doctype bez jawnego
    argumentu — patrz :func:`serialize_document`).

    Args:
        data: surowe bajty dokumentu XHTML/HTML.

    Returns:
        Krotka ``(element_główny, doctype)``; ``doctype`` jest pustym łańcuchem,
        gdy dokument go nie miał.

    Raises:
        ValueError: gdy dokument jest pusty lub nieparsowalny nawet w trybie recover.
    """
    root = cast(
        "etree._Element | None",
        etree.fromstring(data, parser=hardened_parser(recover=True)),
    )
    if root is None:
        raise ValueError("Pusty lub nieparsowalny dokument XML.")
    doctype = getattr(root.getroottree().docinfo, "doctype", "") or ""
    return root, doctype


def serialize_document(root: etree._Element, doctype: str = "") -> bytes:
    """Serializuje element do bajtów z deklaracją XML i (opcjonalnym) DOCTYPE.

    Wzorzec z ``toc/_xml.serialize_xml`` — jawny ``doctype`` jest konieczny, bo
    ``etree.tostring`` gubi DOCTYPE bez tego argumentu.
    """
    if doctype:
        return etree.tostring(root, xml_declaration=True, encoding="utf-8", doctype=doctype)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")
