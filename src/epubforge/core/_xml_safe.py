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

from lxml import etree


def hardened_parser() -> etree.XMLParser:
    """Buduje parser lxml odporny na XXE i rozwijanie encji.

    Zwraca świeżą instancję przy każdym wywołaniu — parsery lxml nie są
    bezpieczne do współdzielenia między wątkami, więc nie trzymamy globalu.

    Returns:
        Skonfigurowany, utwardzony :class:`lxml.etree.XMLParser`.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
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
