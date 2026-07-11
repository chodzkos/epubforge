"""Generator zrzutów ekranu GUI do README/wydania (renderowanie offscreen).

Uruchamia PySide6 na platformie ``offscreen`` (bez fizycznego wyświetlacza),
buduje główne okno oraz kluczowe dialogi funkcji z bramy v3.0 (pobieranie
metadanych po ISBN, ustawienia AI) i zapisuje je jako PNG do ``docs/img/``.

Uwaga: to narzędzie deweloperskie, nie część biblioteki. Zrzuty odświeżamy
ręcznie po istotnych zmianach UI:

    QT_QPA_PLATFORM=offscreen python scripts/make_screenshots.py
"""

from __future__ import annotations

import os
from pathlib import Path

# Platforma offscreen MUSI być ustawiona przed importem QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chodzkos_gui_kit.qt.theme import ThemeManager
from PySide6.QtWidgets import QApplication, QWidget

from epubforge.bookmeta import BookRecord
from epubforge.bookmeta.ai import AIConfig
from epubforge.core import ConfigStore, Metadata
from epubforge.gui.app import MainWindow
from epubforge.gui.metadata_fetch import FetchMetadataDialog
from epubforge.gui.tags_panel import AISettingsDialog

_OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "img"

# Przykładowy rekord (offline) do podglądu dialogu pobierania metadanych.
_SAMPLE_RECORD = BookRecord(
    title="Ostatnie życzenie",
    creators=["Sapkowski, Andrzej"],
    publisher="SuperNOWA",
    date="2014",
    description=(
        "Zbiór opowiadań o wiedźminie Geralcie z Rivii — pierwszy tom sagi, "
        "wprowadzający świat, bohaterów i moralne dylematy łowcy potworów."
    ),
    language="pl",
    page_count=330,
    subjects=["Fantasy", "Opowiadania polskie", "Wiedźmin"],
    series="Wiedźmin",
    source="lubimyczytac",
)


def _grab(widget: QWidget, name: str) -> None:
    """Zapisuje zrzut widgetu do ``docs/img/<name>.png`` (po przetworzeniu zdarzeń)."""
    app = QApplication.instance()
    assert app is not None
    widget.show()
    for _ in range(6):  # kilka pętli, by paleta/QSS i layout się ustabilizowały
        app.processEvents()
    target = _OUT_DIR / f"{name}.png"
    widget.grab().save(str(target))
    print(f"zapisano: {target.relative_to(_OUT_DIR.parent.parent)}")


def main() -> None:
    """Buduje okna i zapisuje komplet zrzutów (motyw ciemny)."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setApplicationName("EpubForge")

    config_path = _OUT_DIR / "_screenshot_config.json"
    config = ConfigStore("epubforge", path=config_path)
    theme_manager = ThemeManager(app, config)
    theme_manager.apply("dark")

    window = MainWindow(config_path, config, {}, theme_manager)
    window.resize(1180, 720)

    # Główne okno: zakładka Metadane (przycisk „Pobierz metadane…", brama v3.0).
    window.tabs.setCurrentWidget(window.metadata_tab)
    _grab(window, "gui-metadata")

    # Główne okno: zakładka Fixer (typografia, obrazy, tagi).
    window.tabs.setCurrentWidget(window.fixer_tab)
    _grab(window, "gui-fixer")

    # Dialog pobierania metadanych po ISBN — wypełniony przykładowym rekordem (offline).
    dialog = FetchMetadataDialog(Metadata(title="", creators=[]), prefill_isbn="9788375780635")
    dialog.resize(560, 640)
    dialog._on_fetched(_SAMPLE_RECORD)
    _grab(dialog, "gui-fetch-metadata")

    # Dialog ustawień AI (presety zgodne z OpenAI, klucz ze zmiennej środowiskowej).
    ai_dialog = AISettingsDialog(AIConfig())
    ai_dialog.resize(520, 320)
    _grab(ai_dialog, "gui-ai-settings")

    # Sprzątamy tymczasowy config zrzutów.
    config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
