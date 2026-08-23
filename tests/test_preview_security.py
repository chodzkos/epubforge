"""Testy resolvera, sesji, snapshotów i sanityzacji podglądu EPUB."""

from __future__ import annotations

import gc
import weakref
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted
from epubforge.gui.preview.paths import (
    UnsafePreviewPathError,
    build_preview_url,
    normalize_internal_path,
    parse_preview_url,
    resolve_publication_path,
)
from epubforge.gui.preview.registry import PreviewGenerationRegistry
from epubforge.gui.preview.sanitize import CSP_POLICY, sanitize_xhtml
from epubforge.gui.preview.session import PreviewSession

_CHAPTER = "OEBPS/text/chapter1.xhtml"


@pytest.mark.parametrize(
    "url",
    (
        "epub-preview://0123456789abcdef0123456789abcdef/../secret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/%2e%2e/secret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/%252e%252e/secret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/OEBPS%2fsecret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/OEBPS%5csecret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/OEBPS\\secret?rev=1",
        "epub-preview://0123456789abcdef0123456789abcdef/OEBPS/%00x?rev=1",
        "epub-preview:///OEBPS/ch.xhtml?rev=1",
        "file:///etc/passwd",
        "https://example.invalid/book.xhtml",
    ),
)
def test_preview_url_rejects_traversal_and_other_schemes(url: str) -> None:
    """Traversal, separatory, NUL, pusty host i obce schematy są odrzucane."""
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(url)


def test_canonical_preview_authority_is_accepted() -> None:
    """Zwykły 32-znakowy host hex jest jedyną akceptowaną postacią authority."""
    session_id = "0123456789abcdef0123456789abcdef"
    request = parse_preview_url(f"epub-preview://{session_id}/a.xhtml?gen=1&rev=1")
    assert request.session_id == session_id
    assert request.internal_path == "a.xhtml"
    assert request.generation_id == 1
    assert request.revision == 1


@pytest.mark.parametrize(
    "url",
    (
        "epub-preview://[xyz]/a.xhtml?gen=1&rev=1",
        "epub-preview://[0123456789abcdef0123456789abcdef]/a.xhtml?gen=1&rev=1",
        "epub-preview://[::1/a.xhtml?gen=1&rev=1",
    ),
)
def test_malformed_preview_authority_is_rejected_fail_closed(url: str) -> None:
    """Wadliwe authority nie omija kontrolowanego odrzucenia URL-a podglądu."""
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(url)
    registry = PreviewGenerationRegistry()
    assert registry.accepts_url(url) is False
    assert registry.resolve_resource(url) is None


def test_preview_url_decodes_utf8_once_and_ignores_fragment() -> None:
    """UTF-8 jest dekodowany ściśle raz, a fragment nie wybiera zasobu."""
    session_id = "0123456789abcdef0123456789abcdef"
    request = parse_preview_url(
        f"epub-preview://{session_id}/OEBPS/za%C5%BC%C3%B3%C5%82%C4%87.xhtml?gen=7&rev=7#akapit"
    )
    assert request.internal_path == "OEBPS/zażółć.xhtml"
    assert request.revision == 7


@pytest.mark.parametrize(
    "raw_path",
    (
        "OEBPS/%",
        "OEBPS/%2",
        "OEBPS/foo%2Gbar.xhtml",
    ),
)
def test_preview_url_rejects_malformed_percent_escape(raw_path: str) -> None:
    """Własny URL podglądu odrzuca niepełne i nieheksadecymalne escape'y."""
    session_id = "0123456789abcdef0123456789abcdef"
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(f"epub-preview://{session_id}/{raw_path}?gen=1&rev=1")


def test_preview_url_rejects_split_encoded_residual_traversal() -> None:
    """Osobno zakodowane znaki escape'u nie ukrywają traversal w URL-u podglądu."""
    session_id = "0123456789abcdef0123456789abcdef"
    path = "OEBPS/%2525%2532%2565%2525%2532%2565/secret.xhtml"
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(f"epub-preview://{session_id}/{path}?gen=1&rev=1")


def test_preview_url_rejects_residual_traversal_beside_invalid_utf8_escape() -> None:
    """Błędny bajt obok nie może ukryć osobno zakodowanego traversal."""
    session_id = "0123456789abcdef0123456789abcdef"
    path = "OEBPS/x%25FF/%2525%2532%2565%2525%2532%2565/secret.xhtml"
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(f"epub-preview://{session_id}/{path}?gen=1&rev=1")


@pytest.mark.parametrize("query", ("", "?path=x&rev=1", "?rev=1&rev=2", "?rev=-1"))
def test_preview_url_accepts_only_single_revision_query(query: str) -> None:
    """Query nie może służyć do wyboru pliku ani wielu rewizji."""
    url = f"epub-preview://0123456789abcdef0123456789abcdef/OEBPS/a.xhtml{query}"
    with pytest.raises(UnsafePreviewPathError):
        parse_preview_url(url)


def test_internal_path_is_posix_and_relative() -> None:
    """Normalizator jest niezależny od hosta i nie przyjmuje ścieżek systemowych."""
    assert normalize_internal_path("OEBPS/text/ch.xhtml") == "OEBPS/text/ch.xhtml"
    for path in ("/etc/passwd", "C:/secret", "OEBPS\\secret", "a/../b", "a//b"):
        with pytest.raises(UnsafePreviewPathError):
            normalize_internal_path(path)


@pytest.mark.parametrize(
    ("reference", "expected"),
    (
        ("images/cover%2Ejpg", "OEBPS/text/images/cover.jpg"),
        ("images/foo%2Ebar.png", "OEBPS/text/images/foo.bar.png"),
        ("chapter%2E1.xhtml", "OEBPS/text/chapter.1.xhtml"),
        ("./chapter.xhtml", "OEBPS/text/chapter.xhtml"),
        ("foo%25bar.xhtml", "OEBPS/text/foo%bar.xhtml"),
    ),
)
def test_publication_path_accepts_safe_percent_encoded_characters(
    reference: str, expected: str
) -> None:
    """Pojedynczy decode dopuszcza kropkę wewnątrz nazwy i literalny procent."""
    assert resolve_publication_path(reference, "OEBPS/text/chapter.xhtml") == expected


@pytest.mark.parametrize(
    "reference",
    (
        "%2e/chapter.xhtml",
        "%2E/chapter.xhtml",
        "%2e%2e/secret.xhtml",
        "%2E%2E/secret.xhtml",
        "%2e./secret.xhtml",
        ".%2E/secret.xhtml",
        "images/%2e%2e/secret.xhtml",
        "images/.%2e/secret.xhtml",
        "images/%252e%252e/secret.xhtml",
        "images/%25252e%25252e/secret.xhtml",
        "images%2Fsecret.xhtml",
        "images%2fsecret.xhtml",
        "images%5Csecret.xhtml",
        "images%5csecret.xhtml",
        "%00secret.xhtml",
        "foo%2Gbar.xhtml",
        "invalid%C0%AEutf8.xhtml",
        "invalid%FFutf8.xhtml",
        "%252e%252e/secret.xhtml",
        "%25252e%25252e/secret.xhtml",
        "images%25252Fsecret.xhtml",
        "a/%2525%2532%2565%2525%2532%2565/secret.xhtml",
        "x%25FF/%2525%2532%2565%2525%2532%2565/secret.xhtml",
        "images%2525%2532%2566secret.xhtml",
        "images%2525%2535%2563secret.xhtml",
        "%2525%2530%2530secret.xhtml",
        "images%2F..%2Fsecret.xhtml",
        "images%5C..%5Csecret.xhtml",
        "file:///etc/passwd",
        "C:%5Csecret.txt",
    ),
)
def test_publication_path_rejects_encoded_traversal_and_separators(reference: str) -> None:
    """Traversal, separatory, NUL i niekanoniczne escape'y pozostają fail-closed."""
    assert resolve_publication_path(reference, "OEBPS/text/chapter.xhtml") is None


def test_publication_path_rejects_raw_parent_outside_publication() -> None:
    """Surowy segment nadrzędny nie może wyjść ponad korzeń publikacji."""
    assert resolve_publication_path("../secret.xhtml", "chapter.xhtml") is None


def test_snapshot_precedence_and_generation_isolation(sample_epub: Path) -> None:
    """Overlay wygrywa z buforem i ZIP-em, a stara generacja natychmiast wygasa."""
    epub = Epub(sample_epub)
    epub.open()
    original = epub.read_file(_CHAPTER)
    epub.write_file(_CHAPTER, b"buffer")
    session = PreviewSession.create(epub, sample_epub)
    first = session.advance(epub, _CHAPTER, {_CHAPTER: "overlay-1"})
    assert first.resource_provider.read(_CHAPTER, first.generation_id) == b"overlay-1"
    assert original != b"overlay-1"

    second = session.advance(epub, _CHAPTER, {_CHAPTER: "overlay-2"})
    assert first.resource_provider.read(_CHAPTER, first.generation_id) == b"overlay-1"
    registry = PreviewGenerationRegistry()
    registry.activate(second)
    assert registry.resolve_url(first.document_url) is None
    assert registry.resolve_url(second.document_url) is not None
    epub.close()


def test_snapshot_ignores_explicit_directory_entries(sample_epub: Path, tmp_path: Path) -> None:
    """Jawne wpisy katalogów ZIP nie są traktowane jak zasoby podglądu."""
    epub_path = tmp_path / "directory-entries.epub"
    with zipfile.ZipFile(sample_epub) as source, zipfile.ZipFile(epub_path, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info))
        target.writestr("OEBPS/", b"")
        target.writestr("OEBPS/text/", b"")

    epub = Epub(epub_path)
    epub.open()
    session = PreviewSession.create(epub, epub_path)
    try:
        generation = session.advance(
            epub,
            _CHAPTER,
            {_CHAPTER: epub.read_file(_CHAPTER)},
        )
        assert generation.resource_provider.exists(_CHAPTER)
        assert not generation.resource_provider.exists("OEBPS/")
    finally:
        session.close()
        epub.close()


def test_closed_session_releases_epub_and_invalidates_urls(sample_epub: Path) -> None:
    """Sesja nie trzyma Epub-a i po zamknięciu nie zwraca żadnego zasobu."""
    epub = Epub(sample_epub)
    epub.open()
    epub_ref = weakref.ref(epub)
    session = PreviewSession.create(epub, sample_epub)
    generation = session.advance(epub, _CHAPTER, {_CHAPTER: "x"})
    request = parse_preview_url(generation.document_url)
    assert session.resolve(request) is not None
    session.close()
    epub.close()
    del epub
    gc.collect()
    assert epub_ref() is None
    assert session.resolve(request) is None


def test_second_book_cannot_read_first_origin(sample_epub: Path) -> None:
    """Losowy host izoluje dwie publikacje nawet przy identycznej ścieżce wpisu."""
    first_epub = Epub(sample_epub)
    second_epub = Epub(sample_epub)
    first_epub.open()
    second_epub.open()
    first = PreviewSession.create(first_epub, sample_epub)
    second = PreviewSession.create(second_epub, sample_epub)
    first_generation = first.advance(first_epub, _CHAPTER, {_CHAPTER: "pierwsza"})
    second_generation = second.advance(second_epub, _CHAPTER, {_CHAPTER: "druga"})
    assert first.session_id != second.session_id
    assert second.resolve(parse_preview_url(first_generation.document_url)) is None
    assert second.resolve(parse_preview_url(second_generation.document_url)) is not None
    first_epub.close()
    second_epub.close()


def test_manifest_mime_wins_and_unknown_is_binary(sample_epub: Path) -> None:
    """MIME pochodzi najpierw z OPF, a nieznane rozszerzenie nie staje się aktywne."""
    epub = Epub(sample_epub)
    epub.open()
    session = PreviewSession.create(epub, sample_epub)
    generation = session.advance(epub, _CHAPTER, {_CHAPTER: "x"})
    provider = generation.resource_provider
    assert provider.media_type(_CHAPTER) == "application/xhtml+xml"
    assert provider.media_type("OEBPS/file.exe") == "application/octet-stream"
    epub.close()


def test_sanitizer_removes_active_content_and_adds_csp() -> None:
    """Skrypty, event handlery, formularze, iframe i meta refresh nie przechodzą."""
    source = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head>
      <meta http-equiv="refresh" content="0;url=https://example.invalid"/>
      </head><body onload="steal()"><script>steal()</script><iframe src="file:///x"/>
      <form action="https://example.invalid"><input/></form><p onclick="x()">tekst</p>
      </body></html>"""
    rendered = sanitize_xhtml(source)
    root = parse_untrusted(rendered)
    names = {etree.QName(element).localname for element in root.iter()}
    assert not {"script", "iframe", "form"} & names
    assert all(
        not etree.QName(attribute).localname.lower().startswith("on")
        for element in root.iter()
        for attribute in element.attrib
    )
    assert CSP_POLICY.encode() in rendered


def test_build_url_roundtrip() -> None:
    """Builder i parser zgadzają się co do hosta, ścieżki i rewizji."""
    session_id = "0123456789abcdef0123456789abcdef"
    request = parse_preview_url(build_preview_url(session_id, _CHAPTER, 42))
    assert (request.session_id, request.internal_path, request.revision) == (
        session_id,
        _CHAPTER,
        42,
    )
