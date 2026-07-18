"""Kanoniczna normalizacja ścieżek własnego schematu podglądu EPUB."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, unquote_to_bytes, urlsplit

from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME

_SESSION_RE = re.compile(r"[0-9a-f]{32}\Z")
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_DANGEROUS_ESCAPE_RE = re.compile(r"%(?:00|2e|2f|5c)", re.IGNORECASE)


class UnsafePreviewPathError(ValueError):
    """Oznacza odrzuconą ścieżkę lub URL zasobu podglądu."""


@dataclass(frozen=True)
class PreviewRequest:
    """Zweryfikowane żądanie zasobu należącego do jednej sesji i generacji."""

    session_id: str
    internal_path: str
    revision: int


def normalize_internal_path(raw_path: str, *, percent_decode: bool = False) -> str:
    """Normalizuje względną ścieżkę EPUB w semantyce POSIX.

    Raises:
        UnsafePreviewPathError: gdy ścieżka jest absolutna, niekanoniczna lub może
            prowadzić poza publikację.
    """
    if not raw_path or raw_path.startswith(("/", "\\")):
        raise UnsafePreviewPathError("Ścieżka zasobu musi być względna")
    if "\\" in raw_path or "\x00" in raw_path or _DRIVE_RE.match(raw_path):
        raise UnsafePreviewPathError("Niedozwolony separator lub prefiks dysku")
    if percent_decode:
        if re.search(r"%(?:2f|5c|00)", raw_path, re.IGNORECASE):
            raise UnsafePreviewPathError("Zakodowany separator lub NUL")
        try:
            decoded = unquote_to_bytes(raw_path).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise UnsafePreviewPathError("Niepoprawne kodowanie UTF-8") from exc
    else:
        decoded = raw_path
    if _DANGEROUS_ESCAPE_RE.search(decoded):
        raise UnsafePreviewPathError("Pozostała zakodowana sekwencja traversal")
    if "\\" in decoded or "\x00" in decoded or _DRIVE_RE.match(decoded):
        raise UnsafePreviewPathError("Niedozwolony separator lub prefiks dysku")
    segments = decoded.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise UnsafePreviewPathError("Pusta lub nawigacyjna część ścieżki")
    normalized = posixpath.normpath(decoded)
    if normalized.startswith("../") or normalized == "..":
        raise UnsafePreviewPathError("Próba wyjścia poza publikację")
    if normalized != decoded:
        raise UnsafePreviewPathError("Ścieżka nie jest kanoniczna")
    return normalized


def parse_preview_url(url: str) -> PreviewRequest:
    """Waliduje pełny URL ``epub-preview://<session>/<path>?rev=N``.

    Fragment jest ignorowany. Query może zawierać wyłącznie pojedynczy,
    nieujemny numer ``rev`` i nigdy nie wybiera pliku.
    """
    parsed = urlsplit(url)
    if parsed.scheme != EPUB_PREVIEW_SCHEME or not parsed.hostname:
        raise UnsafePreviewPathError("Niepoprawny schemat lub pusty host")
    session_id = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafePreviewPathError("Niepoprawny port") from exc
    if not _SESSION_RE.fullmatch(session_id) or parsed.username or port is not None:
        raise UnsafePreviewPathError("Niepoprawny identyfikator sesji")
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise UnsafePreviewPathError("Niepoprawna ścieżka URL")
    internal_path = normalize_internal_path(parsed.path[1:], percent_decode=True)
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise UnsafePreviewPathError("Niepoprawne query") from exc
    if set(query) != {"rev"} or len(query["rev"]) != 1:
        raise UnsafePreviewPathError("Query może zawierać wyłącznie pojedyncze rev")
    raw_revision = query["rev"][0]
    if not raw_revision.isascii() or not raw_revision.isdecimal():
        raise UnsafePreviewPathError("Niepoprawna rewizja zasobu")
    return PreviewRequest(session_id, internal_path, int(raw_revision))


def build_preview_url(session_id: str, internal_path: str, revision: int) -> str:
    """Buduje kanoniczny URL zasobu aktywnej generacji."""
    if not _SESSION_RE.fullmatch(session_id):
        raise UnsafePreviewPathError("Niepoprawny identyfikator sesji")
    path = normalize_internal_path(internal_path)
    if revision < 0:
        raise UnsafePreviewPathError("Rewizja nie może być ujemna")
    encoded_path = quote(path, safe="/-._~")
    return f"{EPUB_PREVIEW_SCHEME}://{session_id}/{encoded_path}?rev={revision}"
