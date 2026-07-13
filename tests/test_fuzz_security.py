"""Fuzz / property testy odporności: ZIP, XML i ścieżki (F-18).

Sprawdzamy niezmienniki bezpieczeństwa na losowych/patologicznych danych:

* niezaufany XML nigdy nie wywala runnera nieoczekiwanym wyjątkiem ani nie sięga
  do sieci (parser utwardzony);
* kanonizacja nazw wpisów ZIP akceptuje **wyłącznie** nazwy, które nie mogą uciec
  poza archiwum (brak ``..``/ścieżki absolutnej/backslasha/NUL);
* walidacja całego archiwum na losowych wpisach kończy się kontrolowanym wyjątkiem
  (``ResourceLimitError``) albo akceptacją — nigdy krachem.

Cały plik należy do stabilnego jobu bezpieczeństwa CI (marker ``security``).
"""

from __future__ import annotations

import contextlib
import io
import posixpath
import zipfile

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from lxml import etree

from epubforge.core._archive import DEFAULT_LIMITS, _validate_name, validate_archive
from epubforge.core._xml_safe import XmlSecurityError, parse_untrusted
from epubforge.core.exceptions import ResourceLimitError

pytestmark = pytest.mark.security

# Kontrolowane, dozwolone wyjątki parsera niezaufanego XML.
_ALLOWED_XML_ERRORS = (etree.XMLSyntaxError, XmlSecurityError, ValueError)

# Tokeny budujące „ciekawe" nazwy wpisów — traversal, absolutne, NUL, backslash, unicode.
_NAME_TOKENS = st.sampled_from(
    ["a", "b", "/", ".", "..", "\\", "\x00", ":", " ", "OEBPS", "ą", "%2e", "dir", "x"]
)
_NAMES = st.lists(_NAME_TOKENS, max_size=6).map("".join)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.binary(max_size=4096))
def test_parse_untrusted_strict_never_crashes(data: bytes) -> None:
    """Dowolne bajty → parser zwraca element albo rzuca kontrolowany wyjątek."""
    with contextlib.suppress(*_ALLOWED_XML_ERRORS):
        parse_untrusted(data)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.binary(max_size=4096))
def test_parse_untrusted_recover_never_crashes(data: bytes) -> None:
    """Wariant recover również nigdy nie wychodzi poza kontrolowane wyjątki."""
    with contextlib.suppress(*_ALLOWED_XML_ERRORS):
        parse_untrusted(data, recover=True)


@settings(max_examples=500, deadline=None)
@given(_NAMES)
def test_validate_name_accepts_only_escape_proof(name: str) -> None:
    """Nazwa zaakceptowana przez kanonizację NIE MOŻE uciec poza archiwum."""
    try:
        _validate_name(name, set())
    except ResourceLimitError:
        return  # odrzucona — kontrolowany wynik, OK
    # Zaakceptowana → musi być bezpieczna na każdym froncie.
    assert name, "pusta nazwa nie powinna przejść"
    assert "\x00" not in name
    assert "\\" not in name
    assert not name.startswith("/")
    # Kluczowy niezmiennik: żaden SEGMENT po normalizacji nie jest ``..`` i sama
    # ścieżka nie jest ``..`` — więc join z katalogiem bazowym nie ucieknie w górę.
    # (Nazwa-plik jak ``..x`` jest bezpieczna — to nie segment traversal.)
    normalized = posixpath.normpath(name)
    assert normalized != "..", f"ucieczka po normpath: {name!r} → {normalized!r}"
    assert ".." not in normalized.split("/"), f"segment traversal: {name!r} → {normalized!r}"


@given(st.text(max_size=40))
def test_validate_name_only_raises_resource_limit(name: str) -> None:
    """Dowolny tekst → kanonizacja albo przechodzi, albo rzuca WYŁĄCZNIE ResourceLimitError."""
    with contextlib.suppress(ResourceLimitError):
        _validate_name(name, set())


@pytest.mark.filterwarnings("ignore::UserWarning")  # zipfile ostrzega o duplikatach — tu celowe
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.tuples(_NAMES, st.binary(max_size=48)), max_size=6))
def test_validate_archive_never_crashes(entries: list[tuple[str, bytes]]) -> None:
    """Losowe archiwum → walidacja daje ResourceLimitError albo przechodzi, bez krachu."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zout:
        for index, (name, data) in enumerate(entries):
            info = zipfile.ZipInfo(name or f"entry{index}")
            with contextlib.suppress(ValueError, OSError):
                zout.writestr(info, data)
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as zin, contextlib.suppress(ResourceLimitError):
        validate_archive(zin, DEFAULT_LIMITS)
