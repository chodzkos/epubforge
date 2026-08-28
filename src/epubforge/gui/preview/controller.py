"""Kontroler budujący kompletne, nieruchome snapshoty niezapisanych danych."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import RLock

from lxml import etree

from epubforge.core import Epub, PendingChanges
from epubforge.core._xml_safe import XmlSecurityError, parse_untrusted, parse_untrusted_document
from epubforge.gui.css_inspector_limits import utf8_fits
from epubforge.gui.preview.backend import (
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewSnapshot,
)
from epubforge.gui.preview.reader import PublicationLayout, detect_publication_layout
from epubforge.gui.preview.resources import PreviewSourceChangedError
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.resource_limits import (
    MAX_MAIN_PREVIEW_BYTES,
    MAX_PREVIEW_CSS_BYTES,
    PreviewTextKind,
    find_preview_text_violation,
)
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
        self._lock = RLock()

    def build(
        self,
        *,
        epub: Epub,
        session: PreviewSession,
        current_path: str,
        current_text: str,
        dirty: Mapping[str, str | bytes],
        media_types: Mapping[str, str],
        pending: PendingChanges | None = None,
    ) -> SnapshotResult:
        """Buduje generację, w której tekst edytora ma najwyższy priorytet."""
        with self._lock:
            return self._build_locked(
                epub=epub,
                session=session,
                current_path=current_path,
                current_text=current_text,
                dirty=dirty,
                media_types=media_types,
                pending=pending if pending is not None else epub.pending_changes(),
            )

    def _build_locked(
        self,
        *,
        epub: Epub,
        session: PreviewSession,
        current_path: str,
        current_text: str,
        dirty: Mapping[str, str | bytes],
        media_types: Mapping[str, str],
        pending: PendingChanges,
    ) -> SnapshotResult:
        """Wykonuje ciężkie parsowanie pod blokadą kontrolera, poza wątkiem GUI."""
        is_css = _is_css(current_path, media_types.get(current_path))
        violation = find_preview_text_violation(
            current_path=current_path,
            dirty=dirty,
            pending_sizes={path: len(data) for path, data in pending.modified.items()},
            media_types=media_types,
            document_limit=MAX_MAIN_PREVIEW_BYTES,
            css_limit=MAX_PREVIEW_CSS_BYTES,
        )
        if violation is not None:
            violation_is_css = violation.kind is PreviewTextKind.CSS
            return SnapshotResult(
                None,
                DiagnosticEvent(
                    category=DiagnosticCategory.PREVIEW_LIMIT,
                    message=_("Arkusz CSS jest zbyt duży do bezpiecznego podglądu.")
                    if violation_is_css
                    else _("Dokument jest zbyt duży do bezpiecznego podglądu."),
                    problem_kind="zbyt_duzy_arkusz_css"
                    if violation_is_css
                    else "zbyt_duzy_dokument",
                    internal_path=violation.path,
                    requester=current_path,
                ),
            )
        limit = MAX_PREVIEW_CSS_BYTES if is_css else MAX_MAIN_PREVIEW_BYTES
        if not utf8_fits(current_text, limit):
            return SnapshotResult(
                None,
                DiagnosticEvent(
                    category=DiagnosticCategory.PREVIEW_LIMIT,
                    message=_("Arkusz CSS jest zbyt duży do bezpiecznego podglądu.")
                    if is_css
                    else _("Dokument jest zbyt duży do bezpiecznego podglądu."),
                    problem_kind="zbyt_duzy_arkusz_css" if is_css else "zbyt_duzy_dokument",
                    internal_path=current_path,
                    requester=current_path,
                ),
            )
        overlay: dict[str, str | bytes] = dict(dirty)
        overlay[current_path] = current_text
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
            publication_layout = _publication_layout(epub, xhtml, overlay, pending)
            self._last_layout = publication_layout
        try:
            generation = session.advance(
                epub, document, overlay, media_types, css_only=is_css, pending=pending
            )
        except PreviewSourceChangedError:
            return SnapshotResult(None, _source_changed_diagnostic(current_path))
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
        with self._lock:
            self._last_document = None
            self._last_xhtml = None
            self._last_layout = PublicationLayout()


def _source_changed_diagnostic(internal_path: str) -> DiagnosticEvent:
    """Kontrolowane odrzucenie, gdy źródło zmieniło się podczas snapshotu."""
    return DiagnosticEvent(
        category=DiagnosticCategory.PREVIEW_LIMIT,
        message=_("Plik źródłowy zmienił się podczas przygotowywania podglądu. Odśwież podgląd."),
        problem_kind="zrodlo_zmienione",
        internal_path=internal_path,
        requester=internal_path,
    )


def _publication_layout(
    epub: Epub,
    xhtml: str,
    overlay: Mapping[str, str | bytes],
    pending: PendingChanges,
) -> PublicationLayout:
    """Czyta bieżący OPF (z zamrożonych overlay/pending), a błąd degraduje."""
    try:
        opf_value = overlay.get(epub.opf_path)
        if opf_value is None:
            opf_value = pending.modified.get(epub.opf_path)
        if opf_value is None:
            if epub.opf_path in pending.deleted:
                raise KeyError(epub.opf_path)
            opf = epub.read_source_file_limited(epub.opf_path, MAX_MAIN_PREVIEW_BYTES)
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
