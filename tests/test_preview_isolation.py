"""Testy izolacji importów: core/CLI nie ładują Qt, podgląd nie ładuje WebEngine.

Uruchamiane w podprocesie, bo liczy się STAN ``sys.modules`` po świeżym imporcie —
w bieżącym procesie testowym Qt może już być załadowane przez inne testy.
"""

from __future__ import annotations

import subprocess
import sys


def test_core_and_cli_do_not_import_qt() -> None:
    """Import ``epubforge`` i CLI nie może wciągać żadnego modułu PySide6 (Qt)."""
    code = (
        "import sys, epubforge, epubforge.cli.main\n"
        "qt = [m for m in sys.modules if m.startswith('PySide6')]\n"
        "assert not qt, qt\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_preview_package_does_not_import_webengine() -> None:
    """Import pakietu podglądu nie może wciągać ``PySide6.QtWebEngine*`` (leniwość)."""
    code = (
        "import importlib.util, sys\n"
        "if importlib.util.find_spec('PySide6') is None:\n"
        "    sys.exit(0)\n"
        "import epubforge.gui.preview\n"
        "we = [m for m in sys.modules if m.startswith('PySide6.QtWebEngine')]\n"
        "assert not we, we\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
