"""Kontrakt bazowej instalacji: pełne CLI bez extra ``gui`` (bez PySide6).

Testy sprawdzają, że warstwy ``epubforge`` / ``epubforge.cli`` / ``epubforge.core``
nie ciągną za sobą ``epubforge.gui`` ani ``PySide6``. Uruchamiamy każdy przypadek
w **osobnym interpreterze** (subprocess), więc kontrakt jest sprawdzalny niezależnie
od tego, czy w danym środowisku PySide6 jest zainstalowane — liczy się to, czego
import *nie* wciąga do ``sys.modules``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from epubforge import __version__


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    """Uruchamia fragment Pythona w czystym interpreterze i zwraca wynik."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Uruchamia ``python -m epubforge`` z podanymi argumentami.

    Dekodujemy wyjście jawnie jako UTF-8 — pomoc CLI zawiera znaki spoza ASCII
    („→", polskie znaki), a domyślne kodowanie rodzica na Windows (cp1252) mogłoby
    zepsuć asercje. Sam proces potomny wymusza UTF-8 na swoich strumieniach.
    """
    return subprocess.run(
        [sys.executable, "-m", "epubforge", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def test_import_epubforge_does_not_pull_gui() -> None:
    """``import epubforge`` nie ładuje warstwy GUI ani PySide6."""
    result = _run_python(
        """
        import sys
        import epubforge
        assert "epubforge.gui" not in sys.modules, "epubforge wciągnął epubforge.gui"
        assert "PySide6" not in sys.modules, "epubforge wciągnął PySide6"
        print("OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_import_cli_main_does_not_pull_gui() -> None:
    """``import epubforge.cli.main`` nie ładuje warstwy GUI ani PySide6."""
    result = _run_python(
        """
        import sys
        import epubforge.cli.main  # noqa: F401
        offenders = [name for name in sys.modules if name.startswith("epubforge.gui")]
        assert offenders == [], f"CLI wciągnęło GUI: {offenders}"
        assert "PySide6" not in sys.modules, "CLI wciągnęło PySide6"
        print("OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_import_core_does_not_pull_gui() -> None:
    """``import epubforge.core`` (i podmoduły) nie ładuje GUI ani PySide6."""
    result = _run_python(
        """
        import sys
        import epubforge.core
        import epubforge.core.filetypes  # noqa: F401
        import epubforge.core.textutil  # noqa: F401
        offenders = [name for name in sys.modules if name.startswith("epubforge.gui")]
        assert offenders == [], f"core wciągnął GUI: {offenders}"
        assert "PySide6" not in sys.modules, "core wciągnął PySide6"
        print("OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_import_gui_package_is_lazy() -> None:
    """Sam ``import epubforge.gui`` nie ładuje PySide6 (leniwe ``__getattr__``)."""
    result = _run_python(
        """
        import sys
        import epubforge.gui  # noqa: F401
        assert "PySide6" not in sys.modules, "import pakietu gui wciągnął PySide6"
        print("OK")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_cli_help_runs() -> None:
    """``epubforge --help`` kończy się kodem 0 i wypisuje nazwę programu."""
    result = _run_cli("--help")
    assert result.returncode == 0, result.stderr
    assert "epubforge" in result.stdout


def test_cli_version_runs() -> None:
    """``epubforge --version`` wypisuje aktualną wersję i kończy się kodem 0."""
    result = _run_cli("--version")
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout


def test_cli_info_core_command_runs() -> None:
    """``epubforge info`` (komenda core) kończy się kodem 0 bez PySide6."""
    result = _run_cli("info")
    assert result.returncode == 0, result.stderr
