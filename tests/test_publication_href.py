"""Testy wspólnego resolvera publication href → ścieżka wpisu ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from epubforge.cli.main import main
from epubforge.core.exceptions import InvalidPublicationHrefError, MissingPublicationMemberError
from epubforge.core.publication_href import resolve_publication_member

_BASE = "OEBPS/content.opf"


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("chapter.xhtml", "OEBPS/chapter.xhtml"),
        ("text/chapter.xhtml", "OEBPS/text/chapter.xhtml"),
        ("../images/cover.jpg", "images/cover.jpg"),
        ("./chapter.xhtml", "OEBPS/chapter.xhtml"),
        ("a/../chapter.xhtml", "OEBPS/chapter.xhtml"),
        ("%2e%2e/other.xhtml", "other.xhtml"),
        ("#fragment", "OEBPS/content.opf"),
        ("?query=1", "OEBPS/content.opf"),
        ("chapter.xhtml#sect1", "OEBPS/chapter.xhtml"),
        ("chapter.xhtml?query=1", "OEBPS/chapter.xhtml"),
    ],
)
def test_resolve_publication_member_accepts_legal_href(href: str, expected: str) -> None:
    """Legalny publication href kanonizuje się do ścieżki wpisu bez wiodącego slash."""
    assert resolve_publication_member(_BASE, href) == expected


@pytest.mark.parametrize(
    "href",
    [
        "../../outside.xhtml",
        "../../../outside.xhtml",
        "/absolute.xhtml",
        "C:/evil.xhtml",
        "C:\\evil.xhtml",
        "\\\\server\\share\\x.xhtml",
        "foo\\bar.xhtml",
        "%252e%252e/other.xhtml",
        "http://evil.example/a.xhtml",
        "file:///etc/passwd",
        "data:text/html,x",
        "foo\x00bar.xhtml",
        "../C:/evil.xhtml",
    ],
)
def test_resolve_publication_member_rejects_unsafe_href(href: str) -> None:
    """Traversal ponad root, schemat, dysk, UNC, backslash, NUL i podwójny encode odpadają."""
    with pytest.raises(InvalidPublicationHrefError):
        resolve_publication_member(_BASE, href)


def test_encoded_parent_stays_inside_root() -> None:
    """Jeden decode ``%2e%2e`` jest legalnym ``..``; wynik zostaje w namespace ZIP."""
    assert resolve_publication_member(_BASE, "%2e%2e/other.xhtml") == "other.xhtml"


def test_root_directory_fragment_is_same_document() -> None:
    """Pusty katalog OPF (plik w korzeniu ZIP) + sam fragment nie wychodzi poza root."""
    assert resolve_publication_member("", "#fragment") == ""
    assert resolve_publication_member("/", "#fragment") == ""
    assert resolve_publication_member("", "chapter.xhtml") == "chapter.xhtml"


def test_double_encoded_parent_is_rejected() -> None:
    """``%252e%252e`` po jednym decode zostawia niebezpieczny escape — fail-closed."""
    with pytest.raises(InvalidPublicationHrefError):
        resolve_publication_member(_BASE, "%252e%252e/other.xhtml")


def test_does_not_return_escaped_parent_path() -> None:
    """Resolver nie może zwrócić ``../outside.xhtml`` jako rzekomo kanonicznej ścieżki."""
    with pytest.raises(InvalidPublicationHrefError):
        resolve_publication_member(_BASE, "../../outside.xhtml")


def _minimal_epub(
    tmp_path: Path,
    *,
    members: dict[str, bytes],
    manifest: list[tuple[str, str, str]],
    name: str = "book.epub",
) -> Path:
    """Buduje EPUB z jawną listą wpisów ZIP i pozycji manifestu."""
    items = "".join(
        f'<item id="{item_id}" href="{href}" media-type="{media}"/>'
        for item_id, href, media in manifest
    )
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f"<manifest>{items}</manifest>"
        '<spine><itemref idref="chapter1"/></spine></package>'
    )
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def test_cli_hyphenate_missing_member_has_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``epubforge hyphenate`` przy wiszącym href nie sypie tracebackiem."""
    chapter = (
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b"<head><title>t</title></head><body><p>slowo</p></body></html>"
    )
    path = _minimal_epub(
        tmp_path,
        members={"OEBPS/text/ok.xhtml": chapter},
        manifest=[
            ("chapter1", "text/ok.xhtml", "application/xhtml+xml"),
            ("ghost", "text/missing.xhtml", "application/xhtml+xml"),
        ],
    )

    exit_code = main(["hyphenate", str(path)])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert "There is no item named" not in captured.out
    assert captured.out or captured.err


def test_cli_typo_missing_member_has_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``epubforge typo`` przy wiszącym href nie sypie tracebackiem."""
    chapter = (
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b'<head><title>t</title></head><body><p>"slowo"</p></body></html>'
    )
    path = _minimal_epub(
        tmp_path,
        members={"OEBPS/text/ok.xhtml": chapter},
        manifest=[
            ("chapter1", "text/ok.xhtml", "application/xhtml+xml"),
            ("ghost", "text/missing.xhtml", "application/xhtml+xml"),
        ],
        name="typo.epub",
    )

    exit_code = main(["typo", str(path)])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert "There is no item named" not in captured.out


def test_cli_fix_images_missing_member_has_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``epubforge fix --optimize-images`` przy wiszącym obrazie nie sypie tracebackiem."""
    pytest.importorskip("PIL")
    chapter = (
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b"<head><title>t</title></head><body><p>ok</p></body></html>"
    )
    path = _minimal_epub(
        tmp_path,
        members={"OEBPS/text/ok.xhtml": chapter},
        manifest=[
            ("chapter1", "text/ok.xhtml", "application/xhtml+xml"),
            ("cover", "images/missing.jpg", "image/jpeg"),
        ],
        name="images.epub",
    )

    exit_code = main(["fix", str(path), "--optimize-images"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert "There is no item named" not in captured.out


def test_missing_member_error_is_domain_type() -> None:
    """Kontrolowany błąd brakującego wpisu dziedziczy po hierarchii EpubForge."""
    from epubforge.core.exceptions import EpubError

    assert issubclass(MissingPublicationMemberError, EpubError)
    assert issubclass(InvalidPublicationHrefError, EpubError)
