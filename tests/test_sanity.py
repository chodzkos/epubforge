"""Test podstawowy — sprawdza że pakiet się importuje poprawnie."""

import epubforge


def test_package_imports() -> None:
    """Pakiet epubforge musi być importowalny i mieć wersję."""
    assert hasattr(epubforge, "__version__")
    assert isinstance(epubforge.__version__, str)
    assert len(epubforge.__version__) > 0


def test_version_format() -> None:
    """Wersja musi być w formacie PEP 440."""
    version = epubforge.__version__
    # Akceptujemy: 0.1.0, 0.1.0-dev, 0.1.0-alpha, 1.0.0rc1 itp.
    assert any(c.isdigit() for c in version), f"Wersja '{version}' nie zawiera cyfr"


def test_cli_main_exists() -> None:
    """CLI ma funkcję main()."""
    from epubforge.cli.main import main

    assert callable(main)
