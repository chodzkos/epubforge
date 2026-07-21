"""Kontroler budujący kompletne, nieruchome snapshoty niezapisanych danych."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import XmlSecurityError, parse_untrusted, parse_untrusted_document
from epubforge.gui.preview.backend import (
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewSnapshot,
)
from epubforge.gui.preview.reader import PublicationLayout, detect_publication_layout
from epubforge.gui.preview.session import PreviewSession
from epubforge.i18n import _


@dataclass(frozen=True)
class SnapshotResult:
    """Wynik przygotowania renderu albo diagnostyka ostatniej dobrej wersji."""

    snapshot: PreviewSnapshot | None
    diagnostic: DiagnosticEvent | None = None


class PreviewController:
    """Izoluje GUI od handlera schematu i zamraża wszystkie niezapisane zmiany."""

    def __init__(self) -> None:
        self._last_document: str | None = None
        self._last_xhtml: str | None = None
        self._last_layout = PublicationLayout()

    def build(
        self,
        *,
        epub: Epub,
        session: PreviewSession,
        current_path: str,
        current_text: str,
        dirty: Mapping[str, str | bytes],
        media_types: Mapping[str, str],
    ) -> SnapshotResult:
        """Buduje generację, w której tekst edytora ma najwyższy priorytet."""
        overlay: dict[str, str | bytes] = dict(dirty)
        overlay[current_path] = current_text
        is_css = _is_css(current_path, media_types.get(current_path))
        if is_css:
            if self._last_document is None or self._last_xhtml is None:
                return SnapshotResult(
                    None,
                    DiagnosticEvent(
                        category=DiagnosticCategory.PREVIEW_LIMIT,
                        message=_("Otwórz rozdział przed podglądem zmian CSS."),
                        problem_kind="brak_dokumentu",
                        internal_path=current_path,
                        requester=current_path,
                    ),
                )
            document = self._last_document
            xhtml = self._last_xhtml
            publication_layout = self._last_layout
        else:
            document = current_path
            xhtml = current_text
            try:
                data = xhtml.encode("utf-8")
                if _is_xhtml(current_path, media_types.get(current_path)):
                    parse_untrusted(data)
                else:
                    parse_untrusted_document(data)
            except (etree.XMLSyntaxError, XmlSecurityError, ValueError) as exc:
                return SnapshotResult(
                    None,
                    DiagnosticEvent(
                        category=DiagnosticCategory.BOOK_ERROR,
                        message=_("Niepoprawny XHTML: {error}").format(error=exc),
                        problem_kind="niepoprawny_xhtml",
                        internal_path=current_path,
                        requester=current_path,
                    ),
                )
            self._last_document = document
            self._last_xhtml = xhtml
            publication_layout = _publication_layout(epub, xhtml, overlay)
            self._last_layout = publication_layout
        generation = session.advance(epub, document, overlay, media_types)
        return SnapshotResult(
            PreviewSnapshot(
                xhtml=xhtml,
                epub=epub,
                internal_path=document,
                generation_id=generation.generation_id,
                generation=generation,
                changed_resource=current_path,
                css_only=is_css,
                publication_layout=publication_layout,
            )
        )

    def clear(self) -> None:
        """Usuwa pamięć dokumentu po zamknięciu lub zmianie książki."""
        self._last_document = None
        self._last_xhtml = None
        self._last_layout = PublicationLayout()


def _publication_layout(
    epub: Epub, xhtml: str, overlay: Mapping[str, str | bytes]
) -> PublicationLayout:
    """Czyta bieżący OPF (z dirty overlay), a błąd degraduje do reflowable."""
    try:
        opf_value = overlay.get(epub.opf_path)
        if opf_value is None:
            opf = epub.read_file(epub.opf_path)
        elif isinstance(opf_value, str):
            opf = opf_value.encode("utf-8")
        else:
            opf = bytes(opf_value)
        return detect_publication_layout(opf, xhtml)
    except (KeyError, OSError, RuntimeError, ValueError):
        return PublicationLayout(limitations=("Nie odczytano metadanych publikacji.",))


def _is_css(path: str, media_type: str | None) -> bool:
    """Rozpoznaje arkusz CSS po deklaracji albo rozszerzeniu."""
    return (media_type or "").lower() == "text/css" or path.lower().endswith(".css")


def _is_xhtml(path: str, media_type: str | None) -> bool:
    """Rozpoznaje dokument wymagający ścisłej składni XML."""
    return (media_type or "").lower() == "application/xhtml+xml" or path.lower().endswith(".xhtml")
