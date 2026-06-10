"""Wspólna logika domyślnego katalogu wyjściowego dla zakładek eksportu.

Zasady (jednolite dla Konwertera i Eksportu Kindle):

* puste pole katalogu → zapis **obok pliku źródłowego** (``source.parent``);
* przy dodaniu pierwszego pliku puste pole jest podpowiadane katalogiem tego pliku;
* ręczny wybór użytkownika nie jest nadpisywany (podpowiadamy tylko gdy puste);
* ostatnio użyty katalog jest pamiętany w ``config.json`` jako fallback.
"""

from __future__ import annotations

from pathlib import Path

from epubforge.core.config import Config

LAST_OUTPUT_DIR_KEY = "last_output_dir"


def resolve_output_dir(output_dir: Path | None, source: Path) -> Path:
    """Zwraca katalog wyjściowy dla pliku: wskazany albo katalog źródła.

    Args:
        output_dir: katalog wskazany przez użytkownika albo ``None`` (puste pole).
        source: przetwarzany plik źródłowy.
    """
    return output_dir if output_dir is not None else source.parent


def remembered_output_dir(config: Config) -> str:
    """Zwraca ostatnio zapamiętany katalog wyjściowy z configu (lub pusty)."""
    value = config.get(LAST_OUTPUT_DIR_KEY)
    return value if isinstance(value, str) else ""


def remember_output_dir(config: Config, field_value: str) -> None:
    """Zapisuje katalog w configu jako ostatnio użyty, jeśli pole nie jest puste."""
    field = field_value.strip()
    if field:
        config[LAST_OUTPUT_DIR_KEY] = field
