"""Internacjonalizacja aplikacji przez gettext.

Msgid pozostaje po polsku, bo to obecny język źródłowy GUI i CLI. Katalog PL
jest mimo to kompilowany, żeby `ngettext` obsługiwał trzy polskie formy mnogie.
"""

from __future__ import annotations

import gettext
import locale
import sys
from pathlib import Path

_DOMAIN = "epubforge"
_SUPPORTED = {"pl", "en", "de"}
_DEFAULT_LANGUAGE = "pl"

_translator: gettext.NullTranslations = gettext.NullTranslations()
_current_language = _DEFAULT_LANGUAGE


def localedir() -> Path:
    """Zwraca katalog z plikami gettext, także w bundlu PyInstaller."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "locale"
    return Path(__file__).resolve().parent / "locale"


def init_i18n(language: str = "auto") -> str:
    """Inicjuje globalny translator i zwraca efektywny kod języka."""
    global _current_language, _translator

    effective = detect_system_language() if language == "auto" else _normalize_language(language)
    _current_language = effective
    _translator = gettext.translation(
        _DOMAIN,
        localedir=str(localedir()),
        languages=[effective],
        fallback=True,
    )
    return effective


def _(msgid: str) -> str:
    """Tłumaczy tekst w momencie wywołania."""
    return _translator.gettext(msgid)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Tłumaczy formę mnogą w momencie wywołania."""
    return _translator.ngettext(singular, plural, n)


def detect_system_language() -> str:
    """Wykrywa język systemu, bez twardej zależności od PySide6."""
    candidate = ""
    try:
        from PySide6.QtCore import QLocale

        candidate = QLocale.system().name()
    except ImportError:
        locale_name, _encoding = locale.getlocale()
        candidate = locale_name or ""
    except Exception:
        candidate = ""
    return _normalize_language(candidate)


def available_languages() -> list[str]:
    """Zwraca dostępne języki na podstawie katalogów z `.mo`."""
    base = localedir()
    languages: list[str] = []
    if not base.is_dir():
        return languages
    for path in base.iterdir():
        if (path / "LC_MESSAGES" / f"{_DOMAIN}.mo").is_file():
            languages.append(path.name)
    return sorted(languages)


def current_language() -> str:
    """Zwraca kod aktualnie ustawionego języka."""
    return _current_language


def _normalize_language(language: str | None) -> str:
    """Normalizuje nazwy typu `pl_PL`, `Polish_Poland`, `de-DE` do `pl/en/de`."""
    raw = (language or "").strip().lower().replace("-", "_")
    if not raw:
        return _DEFAULT_LANGUAGE
    prefix = raw.split("_", 1)[0]
    aliases = {
        "polish": "pl",
        "polski": "pl",
        "german": "de",
        "deutsch": "de",
        "english": "en",
        "angielski": "en",
    }
    normalized = aliases.get(prefix, prefix)
    return normalized if normalized in _SUPPORTED else _DEFAULT_LANGUAGE
