"""Weryfikacja zasobów zainstalowanego koła przez publiczne API EpubForge.

Skrypt uruchamiamy w **pustym venv** z zainstalowanym kołem i **poza** drzewem
źródłowym repo — dzięki temu potwierdza, że dane (locale, presety CSS, receptury
wbudowane, stopwords statystyk, taksonomia PL) oraz marker ``py.typed`` są spakowane
w kole i czytane z zainstalowanej lokalizacji, a nie z checkoutu.

Nie zależy od pytest — czysty ``python build/verify_wheel_resources.py``. Kod
wyjścia 0 = wszystkie zasoby odczytane; 1 = brak zasobu.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Katalog nieistniejący — izoluje testy „wbudowane" od ewentualnych zasobów
# użytkownika w config_dir() na runnerze.
_NO_USER_DIR = Path("/nonexistent-epubforge-user-dir")


def _check_not_from_checkout() -> None:
    """Pakiet musi pochodzić z instalacji (site-packages), nie z drzewa źródeł."""
    import epubforge

    pkg_dir = Path(epubforge.__file__).resolve().parent
    if "site-packages" not in pkg_dir.parts and "dist-packages" not in pkg_dir.parts:
        raise SystemExit(f"pakiet nie jest zainstalowany z koła (ścieżka: {pkg_dir})")


def _check_py_typed() -> None:
    """Marker PEP 561 musi leżeć obok zainstalowanego pakietu."""
    import epubforge

    marker = Path(epubforge.__file__).resolve().parent / "py.typed"
    if not marker.is_file():
        raise SystemExit(f"brak markera py.typed: {marker}")


def _check_taxonomy() -> None:
    """data/taxonomy_pl.toml — wczytanie taksonomii PL."""
    from epubforge.bookmeta.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()
    if not taxonomy.entries:
        raise SystemExit("taksonomia PL jest pusta (data/taxonomy_pl.toml niedoczytane)")


def _check_recipes() -> None:
    """recipes_builtin/*.toml — wbudowane receptury."""
    from epubforge.recipes import discover_recipes

    names = {recipe.name for recipe in discover_recipes(user_dir=_NO_USER_DIR)}
    missing = {"kindle-pl", "czytnik-epub"} - names
    if missing:
        raise SystemExit(f"brak wbudowanych receptur: {sorted(missing)} (mam: {sorted(names)})")


def _check_presets() -> None:
    """fixers/presets/*.css + presets.json — presety CSS."""
    from epubforge.fixers.css_presets import list_presets

    presets = list_presets(user_dir=_NO_USER_DIR)
    if not presets:
        raise SystemExit("brak wbudowanych presetów CSS (fixers/presets niedoczytane)")


def _check_stopwords() -> None:
    """stats_stopwords/*.txt — listy stop-słów statystyk."""
    from epubforge.stats import _load_stopwords

    for language in ("pl", "en", "de"):
        if not _load_stopwords(language):
            raise SystemExit(f"puste stopwords dla języka {language!r} (stats_stopwords)")


def _check_locale() -> None:
    """locale/*/LC_MESSAGES/epubforge.mo — katalogi tłumaczeń gettext."""
    from epubforge.i18n import _, init_i18n

    if init_i18n("en") != "en":
        raise SystemExit("init_i18n('en') nie wybrał katalogu angielskiego")
    if _("Metadane") != "Metadata":
        raise SystemExit("katalog .mo (en) nie został wczytany — tłumaczenie nie zadziałało")


def main() -> int:
    """Uruchamia wszystkie kontrole zasobów i raportuje wynik."""
    checks = (
        _check_not_from_checkout,
        _check_py_typed,
        _check_taxonomy,
        _check_recipes,
        _check_presets,
        _check_stopwords,
        _check_locale,
    )
    for check in checks:
        check()
        print(f"OK: {check.__doc__.splitlines()[0] if check.__doc__ else check.__name__}")
    print("OK: wszystkie zasoby odczytane przez publiczne API zainstalowanego koła")
    return 0


if __name__ == "__main__":
    sys.exit(main())
