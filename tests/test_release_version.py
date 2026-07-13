"""Testy bramki zgodności tagu wydania z ``__version__`` (``build/check_tag_version.py``).

Kryterium (część): polityka/wersja zgadza się z tagiem — rozjazd przerywa release.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "build" / "check_tag_version.py"


def _load_module():
    """Ładuje skrypt buildowy jako moduł (nie jest częścią pakietu)."""
    spec = importlib.util.spec_from_file_location("check_tag_version", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ctv = _load_module()


def test_declared_version_matches_package() -> None:
    """Statyczny odczyt ``__version__`` zgadza się z zainstalowanym pakietem."""
    import epubforge

    assert ctv.read_declared_version() == epubforge.__version__


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v3.0.0", "3.0.0"),
        ("v10.20.30", "10.20.30"),
        ("v3.0.0-rc1", "3.0.0-rc1"),
    ],
)
def test_tag_version_parses_valid(tag: str, expected: str) -> None:
    """Poprawne tagi ``vX.Y.Z`` (z opcjonalnym prerelease) są parsowane."""
    assert ctv.tag_version(tag) == expected


@pytest.mark.parametrize("bad", ["3.0.0", "v3.0", "release-3", "vX.Y.Z", ""])
def test_tag_version_rejects_invalid(bad: str) -> None:
    """Tag bez postaci ``vX.Y.Z`` jest odrzucany."""
    with pytest.raises(ValueError, match="nie ma postaci"):
        ctv.tag_version(bad)


def test_check_matches_current_version() -> None:
    """Tag zgodny z ``__version__`` przechodzi bramkę."""
    ok, message = ctv.check(f"v{ctv.read_declared_version()}")
    assert ok is True
    assert "OK" in message


def test_check_detects_mismatch(tmp_path: Path) -> None:
    """Rozjazd tag↔wersja jest wykryty i opisany."""
    fake_init = tmp_path / "__init__.py"
    fake_init.write_text('__version__ = "3.0.0"\n', encoding="utf-8")
    ok, message = ctv.check("v9.9.9", init_path=fake_init)
    assert ok is False
    assert "Rozjazd wersji" in message


def test_cli_returns_nonzero_on_mismatch(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI zwraca kod ≠ 0 przy rozjeździe (przerywa release)."""
    assert ctv.main(["check_tag_version.py", "v0.0.1-nope"]) == 1


def test_cli_returns_zero_on_match() -> None:
    """CLI zwraca 0, gdy tag zgadza się z wersją."""
    assert ctv.main(["check_tag_version.py", f"v{ctv.read_declared_version()}"]) == 0
