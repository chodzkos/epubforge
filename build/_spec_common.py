"""Wspólny fragment obu speców PyInstaller (portable/onefile + onedir).

Jedna lista ``datas`` (zasoby pakietu), ``hiddenimports`` i wykluczeń Qt dla obu
wariantów — trzymanie ich w jednym miejscu zapobiega rozjazdowi list (audyt F-03:
onefile i onedir miały tę samą, niekompletną listę i łatwo było zaktualizować
tylko jedną). KAŻDY katalog, którego kod szuka w ``sys._MEIPASS``, musi tu być;
brak katalogu w drzewie przerywa build (fail-fast), więc release nie powstanie
bez zasobu.

Specy ładują ten moduł przez ``sys.path.insert(0, SPECPATH)`` + ``import
_spec_common``. Funkcje przyjmują ``spec_dir`` (katalog spec-a), bo globalny
``SPECPATH`` PyInstallera nie jest tu widoczny.
"""

from __future__ import annotations

import importlib
import os

# Moduły, których obecność potwierdzamy przed buildem (fail-fast na brak zależności).
REQUIRED_MODULES = (
    "PySide6.QtWidgets",
    "lxml.etree",
    "pyphen",
    "tinycss2",
    "platformdirs",
)

HIDDEN_IMPORTS = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "lxml",
    "lxml.etree",
    "pyphen",
    "tinycss2",
    "platformdirs",
]

# (podkatalog w src/epubforge, ścieżka docelowa w bundlu). Zasoby czytane z
# ``sys._MEIPASS`` przez loadery: gui/assets (okno About), locale (gettext .mo),
# fixers/presets (presety CSS), stats_stopwords (statystyki), recipes_builtin
# (receptury), data (taxonomy_pl.toml) oraz help_docs (pliki Markdown pomocy —
# okno pomocy czyta je w runtime, więc frozen exe też musi je wozić). recipes_builtin
# i data były wcześniej pominięte w obu specach (F-03) — bez nich tagowanie i
# receptury padały w .exe.
_RESOURCE_DIRS = (
    ("gui/assets", "epubforge/gui/assets"),
    ("locale", "epubforge/locale"),
    ("fixers/presets", "epubforge/fixers/presets"),
    ("stats_stopwords", "epubforge/stats_stopwords"),
    ("recipes_builtin", "epubforge/recipes_builtin"),
    ("data", "epubforge/data"),
    ("help_docs", "epubforge/help_docs"),
)

# Ciężkie moduły Qt, których aplikacja nie używa — wykluczamy, by artefakt nie spuchł.
_QT_EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtDesigner",
    "PySide6.QtTest",
]

EXCLUDES = [
    "matplotlib",
    "numpy",
    "scipy",
    "unittest",
    "test",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    *_QT_EXCLUDES,
]


def check_required_modules() -> None:
    """Importuje wymagane moduły — build pada wcześnie, gdy zależność zniknie."""
    for module in REQUIRED_MODULES:
        importlib.import_module(module)


def _package_dir(spec_dir: str) -> str:
    """Bezwzględna ścieżka do ``src/epubforge`` względem katalogu spec-a."""
    return os.path.abspath(os.path.join(spec_dir, "..", "src", "epubforge"))


def src_pathex(spec_dir: str) -> str:
    """Katalog ``src`` do ``pathex`` (import ``epubforge`` w analizie)."""
    return os.path.abspath(os.path.join(spec_dir, "..", "src"))


def entry_script(spec_dir: str) -> str:
    """Skrypt wejściowy zamrożonej aplikacji (``gui/app.py``)."""
    return os.path.join(_package_dir(spec_dir), "gui", "app.py")


def datas(spec_dir: str) -> list[tuple[str, str]]:
    """Lista ``(katalog_źródłowy, ścieżka_w_bundlu)`` dla wszystkich zasobów.

    Podnosi ``SystemExit``, gdy któregokolwiek katalogu brak — brak zasobu ma
    przerwać build, a nie po cichu wydać niekompletny artefakt.
    """
    package = _package_dir(spec_dir)
    result: list[tuple[str, str]] = []
    for rel_source, dest in _RESOURCE_DIRS:
        abs_source = os.path.join(package, *rel_source.split("/"))
        if not os.path.isdir(abs_source):
            raise SystemExit(f"[epubforge spec] brak katalogu zasobu: {abs_source}")
        result.append((abs_source, dest))
    return result


def icon_path(spec_dir: str) -> str:
    """Ikona: prawdziwa z ``gui/assets`` gdy jest, inaczej placeholder z ``build/``."""
    assets_icon = os.path.join(_package_dir(spec_dir), "gui", "assets", "icon.ico")
    if os.path.exists(assets_icon):
        return assets_icon
    return os.path.join(spec_dir, "icon.ico")
