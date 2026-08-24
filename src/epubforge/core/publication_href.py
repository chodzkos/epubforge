"""Wspólny resolver publication href → kanoniczna ścieżka wpisu ZIP.

Warstwa ``core``: bez Qt, bez schematu ``epub-preview``. Jedna polityka dla
manifestu OPF, fixerów, TOC i map mediów podglądu.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote_to_bytes, urlsplit

from epubforge.core.epub import Epub
from epubforge.core.exceptions import InvalidPublicationHrefError, MissingPublicationMemberError

_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_MALFORMED_ESCAPE_RE = re.compile(r"%(?![0-9a-fA-F]{2})")
_DANGEROUS_ESCAPE_RE = re.compile(r"%(?:25)*(?:00|2e|2f|5c)", re.IGNORECASE)


def resolve_publication_member(base_internal_path: str, href: str) -> str:
    """Rozwiązuje publication href względem bazy do ścieżki wpisu ZIP.

    ``base_internal_path`` to plik (np. ``OEBPS/content.opf``) albo katalog
    z końcowym ``/`` (np. ``OEBPS/``). Wynik nie ma wiodącego slasha.

    Polityka (fail-closed):

    * odrzuca NUL, backslash, ścieżkę absolutną, dysk Windows, UNC i schemat URI;
    * zdejmuje query i fragment (semantyka publication href, nie URL podglądu);
    * wykonuje dokładnie jeden poziom percent-decode;
    * pozwala na legalny ``..`` wewnątrz namespace ZIP;
    * odrzuca wyjście ponad root oraz residualne niebezpieczne escape
      (w tym wielowarstwowy encode w stylu ``%252e``).
    """
    if "\x00" in href or "\x00" in base_internal_path:
        raise InvalidPublicationHrefError("Publication href zawiera znak NUL.")
    if "\\" in href or "\\" in base_internal_path:
        raise InvalidPublicationHrefError("Publication href nie może zawierać backslash.")

    try:
        parsed = urlsplit(href)
    except ValueError as exc:
        raise InvalidPublicationHrefError("Niepoprawny publication href.") from exc
    if parsed.scheme or parsed.netloc:
        raise InvalidPublicationHrefError("Publication href nie może mieć schematu ani authority.")

    raw_path = parsed.path
    if not raw_path:
        return _same_document_path(base_internal_path)
    if raw_path.startswith("/") or _DRIVE_RE.match(raw_path):
        raise InvalidPublicationHrefError("Publication href nie może być ścieżką absolutną.")
    if _MALFORMED_ESCAPE_RE.search(raw_path):
        raise InvalidPublicationHrefError("Publication href ma niepoprawną sekwencję procentową.")

    try:
        decoded = unquote_to_bytes(raw_path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidPublicationHrefError("Publication href nie jest poprawnym UTF-8.") from exc

    if _DANGEROUS_ESCAPE_RE.search(decoded):
        raise InvalidPublicationHrefError(
            "Publication href zostawia niebezpieczne kodowanie procentowe."
        )
    if "\x00" in decoded or "\\" in decoded:
        raise InvalidPublicationHrefError("Publication href po dekodowaniu jest niebezpieczny.")
    if decoded.startswith("/") or _DRIVE_RE.match(decoded) or _SCHEME_RE.match(decoded):
        raise InvalidPublicationHrefError("Publication href po dekodowaniu jest absolutny.")

    combined = posixpath.normpath(posixpath.join(_base_dir(base_internal_path), decoded))
    if combined in {".", ".."} or combined.startswith("../") or combined.startswith("/"):
        raise InvalidPublicationHrefError("Publication href wychodzi poza przestrzeń archiwum.")
    if _DRIVE_RE.match(combined):
        raise InvalidPublicationHrefError("Publication href nie może być ścieżką absolutną.")
    return combined


def resolve_from_directory(base_dir: str, href: str) -> str:
    """Rozwiązuje href względem katalogu (wrapper dla historycznego ``opf_dir``)."""
    if base_dir and not base_dir.endswith("/"):
        return resolve_publication_member(f"{base_dir}/", href)
    return resolve_publication_member(base_dir, href)


def read_publication_member(epub: Epub, internal_path: str) -> bytes:
    """Czyta wpis archiwum albo zgłasza kontrolowany błąd brakującego zasobu."""
    try:
        return epub.read_file(internal_path)
    except KeyError as exc:
        raise MissingPublicationMemberError(
            f"Brak zasobu publikacji w archiwum: {internal_path}."
        ) from exc


def _base_dir(base_internal_path: str) -> str:
    """Zwraca katalog bazy: trailing ``/`` oznacza katalog, inaczej plik."""
    if base_internal_path.endswith("/"):
        directory = posixpath.normpath(base_internal_path.rstrip("/"))
        return "" if directory == "." else directory
    directory = posixpath.dirname(base_internal_path)
    return "" if directory in {".", ""} else directory


def _same_document_path(base_internal_path: str) -> str:
    """Pusty path (sam fragment/query) oznacza dokument bazowy albo katalog TOC."""
    if base_internal_path.endswith("/"):
        directory = posixpath.normpath(base_internal_path.rstrip("/"))
        return "" if directory in {".", ""} else directory
    if not base_internal_path or posixpath.normpath(base_internal_path) in {".", ""}:
        return ""
    return posixpath.normpath(base_internal_path)
