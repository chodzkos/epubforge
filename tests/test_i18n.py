"""Testy internacjonalizacji gettext."""

from __future__ import annotations

import builtins
import io
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from epubforge.cli.main import main
from epubforge.core import Tool
from epubforge.core.config import ConfigStore
from epubforge.gui.app import MainWindow
from epubforge.gui.theme import ThemeManager
from epubforge.i18n import _, detect_system_language, init_i18n, ngettext

LOCALE_DIR = Path(__file__).resolve().parents[1] / "src" / "epubforge" / "locale"
DOMAIN = "epubforge"


def test_init_i18n_en_translates_real_entry_and_falls_back() -> None:
    """Angielski katalog tłumaczy realny wpis i zwraca msgid dla braków."""
    assert init_i18n("en") == "en"
    assert _("Metadane") == "Metadata"
    assert _("Nieistniejący komunikat") == "Nieistniejący komunikat"


def test_unknown_language_falls_back_to_polish() -> None:
    """Nieznany kod języka nie wybucha i używa polskiego źródła."""
    assert init_i18n("xx") == "pl"
    assert _("Metadane") == "Metadane"


def test_ngettext_pl_uses_three_plural_forms() -> None:
    """Polski katalog ma trzy formy liczby mnogiej."""
    init_i18n("pl")
    assert ngettext("{n} plik", "{n} plików", 1).format(n=1) == "1 plik"
    assert ngettext("{n} plik", "{n} plików", 2).format(n=2) == "2 pliki"
    assert ngettext("{n} plik", "{n} plików", 5).format(n=5) == "5 plików"


def test_catalogs_have_complete_non_fuzzy_en_de_translations() -> None:
    """Każdy msgid z POT ma niepuste, nie-fuzzy tłumaczenie EN i DE."""
    pot_messages = _messages(LOCALE_DIR / f"{DOMAIN}.pot")
    for language in ("en", "de"):
        po_messages = _messages(LOCALE_DIR / language / "LC_MESSAGES" / f"{DOMAIN}.po")
        for message_id in pot_messages:
            message = po_messages.get(message_id)
            assert message is not None, f"{language}: missing {message_id!r}"
            assert "fuzzy" not in message.flags, f"{language}: fuzzy {message_id!r}"
            if isinstance(message.string, tuple):
                assert all(message.string), f"{language}: empty plural {message_id!r}"
            else:
                assert message.string, f"{language}: empty {message_id!r}"


def test_mo_files_are_current_against_po() -> None:
    """Skompilowane .mo w repo są aktualne względem .po."""
    for po_path in sorted(LOCALE_DIR.glob(f"*/LC_MESSAGES/{DOMAIN}.po")):
        with po_path.open(encoding="utf-8") as handle:
            catalog = read_po(handle, locale=po_path.parents[1].name)
        compiled = io.BytesIO()
        write_mo(compiled, catalog)
        mo_path = po_path.with_suffix(".mo")
        assert mo_path.read_bytes() == compiled.getvalue(), f"{mo_path} is stale"


def test_detect_system_language_works_without_pyside6(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI może wykrywać język bez importowalnego PySide6."""
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("PySide6"):
            raise ImportError("PySide6 intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr("epubforge.i18n.locale.getlocale", lambda: ("Polish_Poland", "1250"))
    assert detect_system_language() == "pl"


def test_cli_uses_language_from_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI inicjuje gettext z configu przed budową parsera i komunikatów."""
    monkeypatch.setattr("epubforge.cli.main.load_config", lambda _path: {"language": "en"})

    assert main(["info"]) == 0

    captured = capsys.readouterr()
    assert "Detected tools: (TODO - stage 3)" in captured.out


@pytest.mark.gui
def test_main_window_uses_english_language_from_config(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """MainWindow z configiem language=en buduje zakładki po angielsku."""
    config_path = tmp_path / "config.json"
    store = ConfigStore(config_path, {"language": "en"})
    tools = {
        "pandoc": Tool("pandoc", None, available=False),
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
    }
    manager = ThemeManager(qapp, store)
    window = MainWindow(config_path, store, tools, manager)
    qtbot.addWidget(window)

    titles = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert titles == ["Metadata", "Converter", "Fixer", "Kindle Export"]


def _messages(path: Path) -> dict[str | tuple[str, str], Any]:
    """Zwraca wiadomości katalogu pomijając nagłówek."""
    with path.open(encoding="utf-8") as handle:
        catalog = read_po(handle)
    return {message.id: message for message in catalog if message.id}
