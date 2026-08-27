"""Regresje lookupu wpisów EPUB przy równoważności Unicode NFC/NFD."""

from __future__ import annotations

import unicodedata
import zipfile
from pathlib import Path

import pytest

from epubforge.core import Epub
from epubforge.core.exceptions import (
    AmbiguousPublicationMemberError,
    MissingPublicationMemberError,
)
from epubforge.core.member_lookup import locate_archive_member
from epubforge.core.publication_href import (
    read_publication_member,
    resolve_publication_member,
)

_STEM = "żółć"
_NFC_STEM = unicodedata.normalize("NFC", _STEM)
_NFD_STEM = unicodedata.normalize("NFD", _STEM)
_NFC = f"OEBPS/text/{_NFC_STEM}.xhtml"
_NFD = f"OEBPS/text/{_NFD_STEM}.xhtml"
_MIXED = f"OEBPS/text/{_NFC_STEM[0]}{unicodedata.normalize('NFD', _NFC_STEM[1:])}.xhtml"

assert _NFC != _NFD
assert unicodedata.normalize("NFC", _NFD) == _NFC
assert _MIXED not in {_NFC, _NFD}
assert unicodedata.normalize("NFC", _MIXED) == _NFC

_CONTAINER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)
_CHAPTER = (
    b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body><p>x</p></body></html>'
)


def _opf(hrefs: list[str]) -> str:
    items = "".join(
        f'<item id="i{index}" href="{href}" media-type="application/xhtml+xml"/>'
        for index, href in enumerate(hrefs)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f"<manifest>{items}</manifest>"
        '<spine><itemref idref="i0"/></spine></package>'
    )


def _build_epub(
    tmp_path: Path,
    members: dict[str, bytes],
    hrefs: list[str],
    name: str = "book.epub",
) -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER)
        archive.writestr("OEBPS/content.opf", _opf(hrefs))
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def test_nfc_and_nfd_fixtures_are_distinct() -> None:
    """Fixture NFC/NFD musi różnić się kodowo, ale składać się do tego samego NFC."""
    assert _NFC_STEM != _NFD_STEM
    assert unicodedata.normalize("NFC", _NFD_STEM) == _NFC_STEM


def test_locate_exact_nfc_and_nfd_win() -> None:
    """Exact match wygrywa nad równoważnością Unicode."""
    names = {_NFC, _NFD, "OEBPS/text/ascii.xhtml"}
    assert locate_archive_member(_NFC, names) == _NFC
    assert locate_archive_member(_NFD, names) == _NFD
    assert locate_archive_member("OEBPS/text/ascii.xhtml", names) == "OEBPS/text/ascii.xhtml"


def test_locate_unique_nfd_equivalent_of_nfc() -> None:
    """Brak exact NFC przy pojedynczym NFD zwraca ten NFD."""
    assert locate_archive_member(_NFC, {_NFD}) == _NFD


def test_locate_unique_nfc_equivalent_of_nfd() -> None:
    """Brak exact NFD przy pojedynczym NFC zwraca ten NFC."""
    assert locate_archive_member(_NFD, {_NFC}) == _NFC


def test_locate_dual_equivalent_without_exact_is_ambiguous() -> None:
    """Dwa równoważne wpisy bez exact match nie są wybierane arbitralnie."""
    with pytest.raises(AmbiguousPublicationMemberError):
        locate_archive_member(_MIXED, {_NFC, _NFD})


def test_read_file_nfc_finds_exact_nfc(tmp_path: Path) -> None:
    """ZIP NFC + żądanie NFC czyta ten wpis."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        assert epub.read_file(_NFC) == b"NFC-BODY"


def test_read_file_nfd_finds_exact_nfd(tmp_path: Path) -> None:
    """ZIP NFD + żądanie NFD czyta ten wpis."""
    path = _build_epub(tmp_path, {_NFD: b"NFD-BODY"}, [f"text/{_NFD_STEM}.xhtml"])
    with Epub(path) as epub:
        assert epub.read_file(_NFD) == b"NFD-BODY"


def test_read_file_nfc_finds_single_nfd_equivalent(tmp_path: Path) -> None:
    """ZIP NFD + żądanie NFC znajduje jedyny równoważny wpis."""
    path = _build_epub(tmp_path, {_NFD: b"NFD-BODY"}, [f"text/{_NFD_STEM}.xhtml"])
    with Epub(path) as epub:
        assert epub.read_file(_NFC) == b"NFD-BODY"


def test_read_file_nfd_finds_single_nfc_equivalent(tmp_path: Path) -> None:
    """ZIP NFC + żądanie NFD znajduje jedyny równoważny wpis."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        assert epub.read_file(_NFD) == b"NFC-BODY"


def test_read_file_exact_wins_over_equivalent(tmp_path: Path) -> None:
    """Gdy ZIP ma NFC i NFD, exact czyta właściwe ciało, nie aliasuje."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub:
        assert epub.read_file(_NFC) == b"NFC-BODY"
        assert epub.read_file(_NFD) == b"NFD-BODY"
        listed = [name for name in epub.list_files() if name.startswith("OEBPS/text/")]
        assert listed == [_NFC, _NFD]


def test_read_file_dual_equivalent_mixed_form_is_ambiguous(tmp_path: Path) -> None:
    """Mieszana forma przy dwóch równoważnych wpisach nie wybiera pierwszego."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub, pytest.raises(AmbiguousPublicationMemberError):
        epub.read_file(_MIXED)


def test_publication_href_nfc_reads_nfd_member(tmp_path: Path) -> None:
    """Manifest NFC znajduje jedyny member NFD przez warstwę publication."""
    path = _build_epub(tmp_path, {_NFD: b"NFD-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        resolved = resolve_publication_member(epub.opf_path, epub.manifest[0].href)
        assert resolved == _NFC
        assert read_publication_member(epub, resolved) == b"NFD-BODY"


def test_publication_href_nfd_reads_nfc_member(tmp_path: Path) -> None:
    """Manifest NFD znajduje jedyny member NFC przez warstwę publication."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFD_STEM}.xhtml"])
    with Epub(path) as epub:
        resolved = resolve_publication_member(epub.opf_path, epub.manifest[0].href)
        assert resolved == _NFD
        assert read_publication_member(epub, resolved) == b"NFC-BODY"


def test_missing_ascii_member_stays_missing(tmp_path: Path) -> None:
    """Brak równoważności Unicode nie zmienia KeyError dla ASCII."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        with pytest.raises(KeyError):
            epub.read_file("OEBPS/text/missing.xhtml")
        with pytest.raises(MissingPublicationMemberError):
            read_publication_member(epub, "OEBPS/text/missing.xhtml")


def test_write_file_updates_unique_equivalent(tmp_path: Path) -> None:
    """write_file(NFD) przy istniejącym NFC aktualizuje ten wpis, nie tworzy drugiego."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        epub.write_file(_NFD, b"UPDATED")
        assert epub.read_file(_NFC) == b"UPDATED"
        listed = [name for name in epub.list_files() if name.startswith("OEBPS/text/")]
        assert listed == [_NFC]
        pending = epub.pending_changes()
        assert list(pending.modified) == [_NFC]
        assert _NFD not in pending.modified


def test_write_file_dual_members_keeps_exact_identity(tmp_path: Path) -> None:
    """Przy NFC i NFD write_file trafia w exact identity."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub:
        epub.write_file(_NFD, b"NFD-NEW")
        assert epub.read_file(_NFC) == b"NFC-BODY"
        assert epub.read_file(_NFD) == b"NFD-NEW"


def test_write_file_mixed_form_with_dual_members_is_ambiguous(tmp_path: Path) -> None:
    """write_file mieszaną formą przy dwóch równoważnych wpisach jest odrzucany."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub, pytest.raises(AmbiguousPublicationMemberError):
        epub.write_file(_MIXED, b"NOPE")


def test_delete_file_nfd_removes_unique_nfc(tmp_path: Path) -> None:
    """delete_file(NFD) przy jedynym NFC usuwa ten NFC."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        epub.delete_file(_NFD)
        assert _NFC not in epub.list_files()
        with pytest.raises(KeyError):
            epub.read_file(_NFC)
        assert _NFC in epub.pending_changes().deleted
        assert _NFD not in epub.pending_changes().deleted


def test_delete_file_dual_members_deletes_only_exact(tmp_path: Path) -> None:
    """delete_file(NFD) przy parze NFC/NFD nie rusza NFC."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub:
        epub.delete_file(_NFD)
        assert _NFC in epub.list_files()
        assert _NFD not in epub.list_files()
        assert epub.read_file(_NFC) == b"NFC-BODY"


def test_pending_nfd_write_binds_to_source_nfc(tmp_path: Path) -> None:
    """Overlay pending używa tożsamości istniejącego NFC, nie drugiego klucza NFD."""
    path = _build_epub(tmp_path, {_NFC: b"NFC-BODY"}, [f"text/{_NFC_STEM}.xhtml"])
    with Epub(path) as epub:
        epub.write_file(_NFD, b"PENDING")
        assert epub.read_file(_NFC) == b"PENDING"
        assert epub.read_file(_NFD) == b"PENDING"


def test_save_reopen_preserves_dual_member_names(tmp_path: Path) -> None:
    """Save nie scala ani nie przemianowuje pary NFC/NFD."""
    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
        name="dual.epub",
    )
    saved = tmp_path / "saved.epub"
    with Epub(path) as epub:
        epub.save(saved)
    with zipfile.ZipFile(saved) as archive:
        text_names = [name for name in archive.namelist() if name.startswith("OEBPS/text/")]
        assert text_names == [_NFC, _NFD]
        assert archive.read(_NFC) == b"NFC-BODY"
        assert archive.read(_NFD) == b"NFD-BODY"
    with Epub(saved) as epub:
        assert epub.read_file(_NFC) == b"NFC-BODY"
        assert epub.read_file(_NFD) == b"NFD-BODY"


def test_save_reopen_does_not_rename_nfd_member_to_nfc(tmp_path: Path) -> None:
    """Istniejący member NFD zostaje NFD po round-trip — bez migracji książki."""
    path = _build_epub(tmp_path, {_NFD: b"NFD-BODY"}, [f"text/{_NFD_STEM}.xhtml"])
    saved = tmp_path / "saved.epub"
    with Epub(path) as epub:
        epub.save(saved)
    with zipfile.ZipFile(saved) as archive:
        text_names = [name for name in archive.namelist() if name.startswith("OEBPS/text/")]
        assert text_names == [_NFD]


def test_preview_reads_unique_unicode_equivalent(tmp_path: Path) -> None:
    """Podgląd używa tego samego locate co core — NFC request czyta NFD member."""
    from epubforge.gui.preview.cache import ResourceByteCache
    from epubforge.gui.preview.resources import SnapshotResourceProvider, build_resource_catalog

    path = _build_epub(tmp_path, {_NFD: b"NFD-BODY"}, [f"text/{_NFD_STEM}.xhtml"])
    with Epub(path) as epub:
        catalog = build_resource_catalog(epub)
        provider = SnapshotResourceProvider(
            path,
            1,
            dirty_overlay={},
            buffered={},
            deleted=frozenset(),
            files=catalog.files,
            manifest_types=catalog.manifest_types,
            revisions=dict(catalog.revisions),
            sizes=dict(catalog.sizes),
            cache=ResourceByteCache(),
            source_signature=catalog.source_signature,
        )
        assert _NFD in catalog.files
        assert provider.exists(_NFC)
        assert provider.read(_NFC, 1) == b"NFD-BODY"


def test_preview_dual_members_do_not_alias(tmp_path: Path) -> None:
    """Podgląd przy parze NFC/NFD serwuje exact, a mieszana forma milczy."""
    from epubforge.gui.preview.cache import ResourceByteCache
    from epubforge.gui.preview.resources import SnapshotResourceProvider, build_resource_catalog

    path = _build_epub(
        tmp_path,
        {_NFC: b"NFC-BODY", _NFD: b"NFD-BODY"},
        [f"text/{_NFC_STEM}.xhtml"],
    )
    with Epub(path) as epub:
        catalog = build_resource_catalog(epub)
        provider = SnapshotResourceProvider(
            path,
            1,
            dirty_overlay={},
            buffered={},
            deleted=frozenset(),
            files=catalog.files,
            manifest_types=catalog.manifest_types,
            revisions=dict(catalog.revisions),
            sizes=dict(catalog.sizes),
            cache=ResourceByteCache(),
            source_signature=catalog.source_signature,
        )
        assert provider.read(_NFC, 1) == b"NFC-BODY"
        assert provider.read(_NFD, 1) == b"NFD-BODY"
        assert provider.read(_MIXED, 1) is None
