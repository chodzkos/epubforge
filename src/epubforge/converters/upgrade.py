"""Modernizacja pakietu EPUB 2 → EPUB 3.

Operacja jest **minimalna i punktowa**: ruszamy wyłącznie pakiet OPF, tworzymy
dokument nawigacyjny ``nav.xhtml`` (z modelu TOC wczytanego z NCX) i opcjonalnie
usuwamy NCX. Dokumentów TREŚCI nie dotykamy — DOCTYPE XHTML 1.1 jest legalny w
EPUB 3, a im mniejszy zakres edycji, tym mniejsze ryzyko uszkodzenia książki.

Wszystkie parsowania idą przez utwardzony parser (``core._xml_safe``), a edycja
OPF trzyma się wzorca :meth:`Metadata.to_opf`: nie ruszamy elementów, których nie
celujemy jawnie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import (
    parse_untrusted,
    parse_untrusted_document,
    serialize_document,
)
from epubforge.toc import TocEntry, read_toc, write_toc
from epubforge.toc._xml import (
    EPUB_TYPE,
    XHTML_NS,
    first_by_localname,
    resolve_internal,
)

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"
_OPF_EVENT = f"{{{OPF_NS}}}event"
_NCX_MEDIA_TYPE = "application/x-dtbncx+xml"

# Mapa typów `<guide><reference>` (EPUB 2) → wartości `epub:type` (EPUB 3).
# Typy spoza mapy są pomijane z notą w raporcie (roadmapa, Etap 23 pkt 3).
_GUIDE_TO_EPUB_TYPE = {
    "cover": "cover",
    "toc": "toc",
    "text": "bodymatter",
    "title-page": "titlepage",
    "titlepage": "titlepage",
    "copyright-page": "copyright-page",
    "index": "index",
    "glossary": "glossary",
    "bibliography": "bibliography",
    "preface": "preface",
    "foreword": "foreword",
    "dedication": "dedication",
    "epigraph": "epigraph",
    "acknowledgements": "acknowledgments",
    "loi": "loi",
    "lot": "lot",
    "notes": "endnotes",
}


@dataclass
class UpgradeReport:
    """Wynik modernizacji EPUB 2 → 3.

    Attributes:
        already_epub3: ``True``, gdy wejście było już EPUB 3 (operacja to no-op).
        transformations: opisy wykonanych transformacji (kolejność wykonania).
        skipped: noty o rzeczach pominiętych (np. nieznane typy ``guide``).
    """

    already_epub3: bool = False
    transformations: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def upgrade_to_epub3(
    epub: Epub, *, keep_ncx: bool = True, now: datetime | None = None
) -> UpgradeReport:
    """Modernizuje otwarty EPUB 2 do EPUB 3 (zmiany trafiają do bufora ``epub``).

    Args:
        epub: otwarty EPUB (zapis utrwala dopiero ``epub.save()``).
        keep_ncx: gdy ``True`` (domyślnie) zostawia NCX dla starszych czytników;
            ``False`` usuwa plik NCX, jego wpis w manifeście i atrybut ``spine@toc``.
        now: znacznik ``dcterms:modified`` (UTC); ``None`` = bieżący czas.

    Returns:
        :class:`UpgradeReport`. Dla wejścia już w EPUB 3 zwraca
        ``already_epub3=True`` bez żadnych zmian.
    """
    report = UpgradeReport()
    root = parse_untrusted(epub.read_file(epub.opf_path))
    if str(root.get("version", "")).startswith("3"):
        report.already_epub3 = True
        return report

    # Spis i NCX odczytujemy PRZED edycją OPF (manifest wciąż zawiera wpis NCX).
    entries, _source = read_toc(epub)
    ncx_path = _ncx_internal_path(epub)
    guide_refs = _capture_guide(root)

    root.set("version", "3.0")
    report.transformations.append("package version → 3.0")
    _apply_metadata_fixes(root, now, report)
    if guide_refs and _remove_guide(root):
        report.transformations.append("usunięto <guide> (→ landmarks w nav)")
    ncx_dropped = not keep_ncx and _drop_ncx_from_opf(root)
    epub.write_file(epub.opf_path, serialize_document(root))

    _write_navigation(epub, entries, guide_refs, report)

    if ncx_dropped and ncx_path is not None:
        epub.delete_file(ncx_path)
        report.transformations.append("usunięto NCX (plik + manifest + spine@toc)")
    return report


def _apply_metadata_fixes(
    root: etree._Element, now: datetime | None, report: UpgradeReport
) -> None:
    """Wykonuje punktowe naprawy metadanych OPF (identyfikator, daty, dcterms)."""
    if _fix_unique_identifier(root):
        report.transformations.append("unique-identifier wskazuje istniejący dc:identifier")
    if _fix_dates(root):
        report.transformations.append("dc:date: usunięto opf:event, zostawiono datę publikacji")
    _set_dcterms_modified(root, now)
    report.transformations.append('dodano <meta property="dcterms:modified">')


def _write_navigation(
    epub: Epub,
    entries: list[TocEntry],
    guide_refs: list[tuple[str, str, str]],
    report: UpgradeReport,
) -> None:
    """Tworzy nav.xhtml (TOC z NCX) i dokleja do niego landmarks z guide."""
    toc_entries = entries or _fallback_entries(epub)
    write_toc(epub, toc_entries, write_nav=True, write_ncx=False)
    report.transformations.append('utworzono nav.xhtml (properties="nav") ze spisu NCX')

    landmarks, skipped = _landmarks_from_guide(guide_refs)
    report.skipped.extend(skipped)
    if landmarks:
        _append_landmarks(epub, landmarks)
        report.transformations.append(f"dodano landmarks ({len(landmarks)} pozycji)")


# ── Naprawy OPF ──────────────────────────────────────────────────────────────


def _metadata_el(root: etree._Element) -> etree._Element | None:
    """Zwraca element ``<metadata>`` pakietu OPF (albo ``None``)."""
    return root.find(f"{{{OPF_NS}}}metadata")


def _collect_ids(root: etree._Element) -> set[str]:
    """Zbiera wartości atrybutu ``id`` w całym dokumencie OPF."""
    return {value for el in root.iter() if isinstance(el.tag, str) and (value := el.get("id"))}


def _unique_id(base: str, existing: set[str]) -> str:
    """Zwraca ``base`` lub ``base-N`` niekolidujące z ``existing``."""
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _fix_unique_identifier(root: etree._Element) -> bool:
    """Zapewnia, że ``package@unique-identifier`` wskazuje istniejący dc:identifier."""
    metadata_el = _metadata_el(root)
    if metadata_el is None:
        return False
    idents = metadata_el.findall(f"{{{DC_NS}}}identifier")
    if not idents:
        return False
    uid = root.get("unique-identifier")
    if uid and any(ident.get("id") == uid for ident in idents):
        return False  # już poprawne

    target = idents[0]
    target_id = target.get("id")
    if not target_id:
        # Preferuj zadeklarowaną nazwę (uid), jeśli wolna; inaczej syntetyzuj.
        target_id = (
            uid
            if uid and uid not in _collect_ids(root)
            else _unique_id("pub-id", _collect_ids(root))
        )
        target.set("id", target_id)
    root.set("unique-identifier", target_id)
    return True


def _fix_dates(root: etree._Element) -> bool:
    """Sprowadza ``dc:date`` do jednej daty publikacji bez atrybutu ``opf:event``."""
    metadata_el = _metadata_el(root)
    if metadata_el is None:
        return False
    dates = metadata_el.findall(f"{{{DC_NS}}}date")
    if not dates:
        return False
    keeper = next((d for d in dates if d.get(_OPF_EVENT) in (None, "publication")), dates[0])
    changed = False
    if keeper.get(_OPF_EVENT) is not None:
        del keeper.attrib[_OPF_EVENT]
        changed = True
    for date in dates:
        if date is not keeper:
            metadata_el.remove(date)
            changed = True
    return changed


def _set_dcterms_modified(root: etree._Element, now: datetime | None) -> None:
    """Ustawia ``<meta property="dcterms:modified">`` w formacie ``CCYY-MM-DDThh:mm:ssZ``."""
    metadata_el = _metadata_el(root)
    if metadata_el is None:
        return
    moment = now if now is not None else datetime.now(timezone.utc)
    moment = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    stamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for meta in list(metadata_el.findall(f"{{{OPF_NS}}}meta")):
        if meta.get("property") == "dcterms:modified":
            metadata_el.remove(meta)
    meta = etree.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
    meta.set("property", "dcterms:modified")
    meta.text = stamp


def _capture_guide(root: etree._Element) -> list[tuple[str, str, str]]:
    """Zwraca listę ``(type, href, title)`` z ``<guide>`` (href względny do OPF)."""
    guide = root.find(f"{{{OPF_NS}}}guide")
    if guide is None:
        return []
    refs: list[tuple[str, str, str]] = []
    for ref in guide.findall(f"{{{OPF_NS}}}reference"):
        ref_type, href = ref.get("type"), ref.get("href")
        if ref_type and href:
            refs.append((ref_type, href, ref.get("title") or ""))
    return refs


def _remove_guide(root: etree._Element) -> bool:
    """Usuwa element ``<guide>`` z pakietu (jego treść wędruje do landmarks)."""
    guide = root.find(f"{{{OPF_NS}}}guide")
    if guide is None:
        return False
    root.remove(guide)
    return True


def _drop_ncx_from_opf(root: etree._Element) -> bool:
    """Usuwa wpis NCX z manifestu i atrybut ``toc`` ze spine."""
    removed = False
    manifest = root.find(f"{{{OPF_NS}}}manifest")
    if manifest is not None:
        for item in list(manifest):
            if item.get("media-type") == _NCX_MEDIA_TYPE:
                manifest.remove(item)
                removed = True
    spine = root.find(f"{{{OPF_NS}}}spine")
    if spine is not None and spine.get("toc"):
        del spine.attrib["toc"]
        removed = True
    return removed


# ── Nawigacja (nav.xhtml / landmarks) ────────────────────────────────────────


def _ncx_internal_path(epub: Epub) -> str | None:
    """Zwraca ścieżkę wewnętrzną pliku NCX (lub ``None``)."""
    ncx_item = next((it for it in epub.manifest if it.media_type == _NCX_MEDIA_TYPE), None)
    if ncx_item is None:
        return None
    path, _ = resolve_internal(epub.opf_dir(), ncx_item.href)
    return path


def _fallback_entries(epub: Epub) -> list[TocEntry]:
    """Awaryjny jednopozycyjny spis (brak NCX/nav) — bez ruszania treści."""
    by_id = {item.id: item for item in epub.manifest}
    for idref in epub.spine:
        item = by_id.get(idref)
        if item is None:
            continue
        path, _ = resolve_internal(epub.opf_dir(), item.href)
        return [TocEntry(title=epub.metadata.title or "Start", href=path)]
    return []


def _landmarks_from_guide(
    guide_refs: list[tuple[str, str, str]],
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Mapuje guide na ``(epub_type, href, title)``; nieznane typy → noty."""
    landmarks: list[tuple[str, str, str]] = []
    skipped: list[str] = []
    for ref_type, href, title in guide_refs:
        epub_type = _GUIDE_TO_EPUB_TYPE.get(ref_type.lower())
        if epub_type is None:
            skipped.append(f"pominięto nieznany typ guide: {ref_type}")
            continue
        landmarks.append((epub_type, href, title or epub_type))
    return landmarks, skipped


def _append_landmarks(epub: Epub, landmarks: list[tuple[str, str, str]]) -> None:
    """Dokleja ``<nav epub:type="landmarks">`` do świeżo utworzonego nav.xhtml."""
    nav_item = next((it for it in epub.manifest if "nav" in (it.properties or "").split()), None)
    if nav_item is None:
        return
    nav_path, _ = resolve_internal(epub.opf_dir(), nav_item.href)
    root, doctype = parse_untrusted_document(epub.read_file(nav_path))
    body = first_by_localname(root, "body")
    host = body if body is not None else root

    nav_el = etree.SubElement(host, f"{{{XHTML_NS}}}nav")
    nav_el.set(EPUB_TYPE, "landmarks")
    ol = etree.SubElement(nav_el, f"{{{XHTML_NS}}}ol")
    for epub_type, href, title in landmarks:
        li = etree.SubElement(ol, f"{{{XHTML_NS}}}li")
        anchor = etree.SubElement(li, f"{{{XHTML_NS}}}a")
        anchor.set(EPUB_TYPE, epub_type)
        anchor.set("href", href)
        anchor.text = title
    epub.write_file(nav_path, serialize_document(root, doctype))
