"""Pliki prawdy pomocy EpubForge (Markdown) + ich rejestr — warstwa bez Qt.

„Jeden plik prawdy" (gui-kit 0.5.3): treść zakładek pomocy renderowanych z Markdown
mieszka w plikach ``*.md`` tego pakietu, a nie jest duplikowana w kodzie GUI. Pliki są
danymi pakietu (pakowane jak ``locale`` / ``fixers/presets``), więc działają z koła,
z drzewa źródeł i po zebraniu przez PyInstaller — czytane w runtime przez
``importlib.resources.files("epubforge.help_docs")``.

Rejestr :data:`MARKDOWN_SECTIONS` (``(tytuł_zakładki, nazwa_pliku)`` w kolejności
zakładek GUI) jest **czysto-core** — nie importuje Qt — dzięki czemu korzysta z niego
zarówno okno pomocy (``gui/help_window.py``), jak i samokontrola zasobów zamrożonego
artefaktu (``_frozen_check``) oraz kontrakt koła (``build/verify_wheel_resources.py``).
"""

from __future__ import annotations

# (tytuł zakładki pomocy, nazwa pliku w tym pakiecie) — kolejność = kolejność
# zakładek w oknie pomocy (odwzorowuje zakładki GUI + zakładka „Wiersz poleceń").
MARKDOWN_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Metadane", "metadata.md"),
    ("Konwerter", "converter.md"),
    ("Fixer", "fixer.md"),
    ("Eksport Kindle", "kindle.md"),
    ("Edytor", "editor.md"),
    ("Walidacja", "validation.md"),
    ("Spis treści", "toc.md"),
    ("Statystyki", "stats.md"),
    ("Wiersz poleceń", "cli.md"),
)
