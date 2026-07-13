"""Samokontrola zasobów zamrożonego artefaktu (PyInstaller) — bez Qt.

Zamrożony ``epubforge.exe`` uruchomiony z ``--self-check [PLIK_LOGU]`` ładuje
każdy pakowany zasób przez publiczne API i kończy się kodem 0 (wszystko OK) lub
1 (brak zasobu). W zamrożonym procesie loadery czytają z ``sys._MEIPASS``
(bundle), więc pozytywny wynik dowodzi, że dane trafiły do artefaktu — nie do
źródłowego checkoutu.

Windowed build (``console=False``) nie ma podpiętego stdout (``sys.stdout`` bywa
``None``), dlatego wynik zapisujemy do pliku logu; gdy stdout istnieje (źródła/
konsola), dublujemy go na stdout. Moduł jest czysto-core (żaden import Qt), więc
używa go zarówno zamrożony entry point GUI, jak i testy jednostkowe oraz
``build/verify_wheel_resources.py`` (kontrakt koła).
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from pathlib import Path

# Katalog użytkownika, który na pewno nie istnieje — izoluje kontrole „wbudowane"
# od ewentualnych zasobów użytkownika w ``config_dir()`` na maszynie testowej.
_NO_USER_DIR = Path("/nonexistent-epubforge-user-dir")

# Domyślna nazwa pliku logu, gdy nie podano ścieżki argumentem.
_DEFAULT_LOG = "epubforge-selfcheck.log"


def _check_taxonomy() -> str:
    """data/taxonomy_pl.toml — wczytanie taksonomii PL."""
    from epubforge.bookmeta.taxonomy import load_taxonomy

    entries = load_taxonomy().entries
    if not entries:
        raise RuntimeError("taksonomia PL jest pusta (data/taxonomy_pl.toml)")
    return f"taksonomia PL: {len(entries)} wpisów"


def _check_recipes() -> str:
    """recipes_builtin/*.toml — wbudowane receptury."""
    from epubforge.recipes import discover_recipes

    names = {recipe.name for recipe in discover_recipes(user_dir=_NO_USER_DIR)}
    missing = {"kindle-pl", "czytnik-epub"} - names
    if missing:
        raise RuntimeError(f"brak wbudowanych receptur: {sorted(missing)}")
    return f"receptury wbudowane: {sorted(names)}"


def _check_presets() -> str:
    """fixers/presets/*.css + presets.json — presety CSS."""
    from epubforge.fixers.css_presets import list_presets

    presets = list_presets(user_dir=_NO_USER_DIR)
    if not presets:
        raise RuntimeError("brak wbudowanych presetów CSS (fixers/presets)")
    return f"presety CSS: {len(presets)}"


def _check_stopwords() -> str:
    """stats_stopwords/*.txt — listy stop-słów statystyk."""
    from epubforge.stats import _load_stopwords

    for language in ("pl", "en", "de"):
        if not _load_stopwords(language):
            raise RuntimeError(f"puste stopwords dla języka {language!r} (stats_stopwords)")
    return "stopwords: pl/en/de"


def _check_locale() -> str:
    """locale/*/LC_MESSAGES/epubforge.mo — katalogi tłumaczeń gettext."""
    from epubforge.i18n import _, init_i18n

    if init_i18n("en") != "en":
        raise RuntimeError("init_i18n('en') nie wybrał katalogu angielskiego")
    if _("Metadane") != "Metadata":
        raise RuntimeError("katalog .mo (en) nie został wczytany")
    return "tłumaczenia gettext: en OK"


# Kolejność krotki = kolejność raportu. Każda kontrola zwraca opis albo rzuca wyjątek.
CHECKS: tuple[tuple[str, Callable[[], str]], ...] = (
    ("taksonomia", _check_taxonomy),
    ("receptury", _check_recipes),
    ("presety", _check_presets),
    ("stopwords", _check_stopwords),
    ("tłumaczenia", _check_locale),
)


def _config_mode_line() -> str:
    """Raportuje kontrakt portable: gdzie trafia config i w jakim trybie.

    Onefile (runtime hook) → ``mode=portable`` i katalog obok exe; onedir/instalator
    → ``mode=installed`` i lokalizacja systemowa. Format ``mode=<tryb>`` jest
    parsowany przez smoke test w ``build.yml`` do asercji per-wariant.
    """
    from epubforge.core import config

    mode = "portable" if config._is_portable() else "installed"
    return f"config: mode={mode} dir={config.config_dir()}"


def check_bundled_resources() -> list[str]:
    """Uruchamia wszystkie kontrole zasobów; rzuca przy pierwszym braku.

    Returns:
        Lista opisów kolejnych, poprawnie wczytanych zasobów.
    """
    return [check() for _name, check in CHECKS]


def run_self_check(argv: list[str] | None = None) -> int:
    """Punkt wejścia ``--self-check``: waliduje zasoby i zwraca kod wyjścia.

    Args:
        argv: Argumenty PO ``--self-check`` (pierwszy = opcjonalna ścieżka logu);
            ``None`` bierze ``sys.argv[1:]``.

    Returns:
        0 — wszystkie zasoby wczytane; 1 — brak któregokolwiek zasobu.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    log_path = Path(args[0]) if args else Path(_DEFAULT_LOG)

    frozen = bool(getattr(sys, "_MEIPASS", None))
    lines = [f"epubforge self-check (frozen={frozen})"]
    exit_code = 0
    try:
        for detail in check_bundled_resources():
            lines.append(f"OK: {detail}")
        lines.append(f"OK: {_config_mode_line()}")
        lines.append("OK: wszystkie zasoby wczytane z bundla")
    except Exception as exc:  # celowo szeroko — raport dowolnego braku zasobu jako FAIL
        lines.append(f"FAIL: {exc}")
        exit_code = 1

    text = "\n".join(lines) + "\n"
    # Windowed build (console=False) bywa bez stdout — log do pliku jest źródłem prawdy.
    with contextlib.suppress(OSError):
        log_path.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        sys.stdout.write(text)
    return exit_code
