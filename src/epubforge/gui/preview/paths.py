"""Kanoniczne i wersjonowane adresy własnego schematu podglądu EPUB."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, unquote_to_bytes, urlsplit

from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME

_SESSION_RE = re.compile(r"[0-9a-f]{32}\Z")
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_FORBIDDEN_RAW_ESCAPE_RE = re.compile(r"%(?:00|2f|5c)", re.IGNORECASE)
_DANGEROUS_ESCAPE_RE = re.compile(r"%(?:25)*(?:00|2e|2f|5c)", re.IGNORECASE)
_MALFORMED_ESCAPE_RE = re.compile(r"%(?![0-9a-fA-F]{2})")


class UnsafePreviewPathError(ValueError):
    """Oznacza odrzuconą ścieżkę lub URL zasobu podglądu."""


def _has_residual_dangerous_escape(value: str) -> bool:
    """Wykrywa niebezpieczny escape ukryty pod kolejnymi warstwami kodowania."""
    candidate = value
    while "%" in candidate:
        if _DANGEROUS_ESCAPE_RE.search(candidate):
            return True
        decoded = "".join(
            chr(byte) if byte < 0x80 else "\ufffd" for byte in unquote_to_bytes(candidate)
        )
        if decoded == candidate:
            return False
        candidate = decoded
    return False


@dataclass(frozen=True)
class PreviewRequest:
    """Zweryfikowane żądanie zasobu jednej sesji i generacji."""

    session_id: str
    internal_path: str
    generation_id: int
    revision: int


def normalize_internal_path(raw_path: str, *, percent_decode: bool = False) -> str:
    """Normalizuje względną ścieżkę EPUB w semantyce POSIX."""
    if not raw_path or raw_path.startswith(("/", "\\")):
        raise UnsafePreviewPathError("Ścieżka zasobu musi być względna")
    if "\\" in raw_path or "\x00" in raw_path or _DRIVE_RE.match(raw_path):
        raise UnsafePreviewPathError("Niedozwolony separator lub prefiks dysku")
    if percent_decode:
        if _MALFORMED_ESCAPE_RE.search(raw_path):
            raise UnsafePreviewPathError("Niepoprawna sekwencja procentowa")
        if _FORBIDDEN_RAW_ESCAPE_RE.search(raw_path):
            raise UnsafePreviewPathError("Zakodowany separator lub NUL")
        try:
            decoded = unquote_to_bytes(raw_path).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise UnsafePreviewPathError("Niepoprawne kodowanie UTF-8") from exc
    else:
        decoded = raw_path
    if _has_residual_dangerous_escape(decoded):
        raise UnsafePreviewPathError("Pozostała zakodowana sekwencja traversal")
    if "\\" in decoded or "\x00" in decoded or _DRIVE_RE.match(decoded):
        raise UnsafePreviewPathError("Niedozwolony separator lub prefiks dysku")
    segments = decoded.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise UnsafePreviewPathError("Pusta lub nawigacyjna część ścieżki")
    normalized = posixpath.normpath(decoded)
    if normalized.startswith("../") or normalized == ".." or normalized != decoded:
        raise UnsafePreviewPathError("Ścieżka wychodzi poza publikację lub nie jest kanoniczna")
    return normalized


def resolve_publication_path(reference: str, base_path: str) -> str | None:
    """Rozwiązuje URL względny wyłącznie wewnątrz przestrzeni nazw EPUB.

    Surowe segmenty ``..`` są dozwolone, jeżeli normalizacja nadal kończy się
    wewnątrz publikacji. Schematy, authority, query, ścieżki hosta i niebezpieczne
    kodowanie procentowe są odrzucane bez cichego przepisywania wejścia.
    """
    value = reference.strip()
    if not value or value != reference or "\x00" in value or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.query:
        return None
    if not parsed.path:
        try:
            return normalize_internal_path(base_path.rstrip("/"))
        except UnsafePreviewPathError:
            return None
    if (
        parsed.path.startswith("/")
        or _FORBIDDEN_RAW_ESCAPE_RE.search(parsed.path)
        or _MALFORMED_ESCAPE_RE.search(parsed.path)
    ):
        return None
    try:
        decoded = unquote_to_bytes(parsed.path).decode("utf-8", errors="strict")
        encoded_navigation = any(
            "%" in raw_segment and decoded_segment in (".", "..")
            for raw_segment, decoded_segment in zip(
                parsed.path.split("/"), decoded.split("/"), strict=True
            )
        )
        if (
            "\x00" in decoded
            or "\\" in decoded
            or decoded.startswith("/")
            or _SCHEME_RE.match(decoded)
            or encoded_navigation
            or _has_residual_dangerous_escape(decoded)
        ):
            return None
        canonical_base = normalize_internal_path(base_path.rstrip("/"))
        base_dir = canonical_base if base_path.endswith("/") else posixpath.dirname(canonical_base)
        combined = posixpath.normpath(posixpath.join(base_dir, decoded))
        return normalize_internal_path(combined)
    except (UnicodeDecodeError, UnsafePreviewPathError):
        return None


def parse_preview_url(url: str) -> PreviewRequest:
    """Waliduje URL własnego schematu z parametrami gen i rev."""
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
    if set(query) != {"gen", "rev"} or any(len(values) != 1 for values in query.values()):
        raise UnsafePreviewPathError("Query musi zawierać pojedyncze gen i rev")
    values = (query["gen"][0], query["rev"][0])
    if any(not value.isascii() or not value.isdecimal() for value in values):
        raise UnsafePreviewPathError("Niepoprawna generacja lub rewizja")
    return PreviewRequest(session_id, internal_path, int(values[0]), int(values[1]))


def build_preview_url(
    session_id: str,
    internal_path: str,
    generation_id: int,
    revision: int | None = None,
    *,
    fragment: str | None = None,
) -> str:
    """Buduje kanoniczny URL zasobu z osobną generacją i rewizją."""
    if not _SESSION_RE.fullmatch(session_id):
        raise UnsafePreviewPathError("Niepoprawny identyfikator sesji")
    path = normalize_internal_path(internal_path)
    resource_revision = generation_id if revision is None else revision
    if generation_id < 0 or resource_revision < 0:
        raise UnsafePreviewPathError("Generacja i rewizja nie mogą być ujemne")
    encoded_path = quote(path, safe="/-._~")
    result = (
        f"{EPUB_PREVIEW_SCHEME}://{session_id}/{encoded_path}"
        f"?gen={generation_id}&rev={resource_revision}"
    )
    if fragment:
        result += f"#{quote(fragment, safe='-._~')}"
    return result
