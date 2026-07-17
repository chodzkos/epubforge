"""Sesja podglądu publikacji — fundament (Prompt 1).

Reprezentuje jedną otwartą publikację w podglądzie. Na tym etapie przechowuje
tylko tożsamość sesji i odwołanie do :class:`~epubforge.core.epub.Epub`; Prompt 2
rozszerzy ją o nieprzewidywalny origin (``epub-preview://<session-id>/...``),
``resource_provider``, snapshot niezapisanych zmian oraz stan zaznaczenia.

Moduł jest czystym Pythonem (bez WebEngine) — może być importowany także przez
lekki fallback, który nigdy nie dotyka Qt WebEngine.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from epubforge.core import Epub


@dataclass
class PreviewSession:
    """Jedna otwarta publikacja w podglądzie (fundament; rozszerzana w Prompt 2).

    Atrybuty:
        session_id: nieprzewidywalny identyfikator sesji (osobny origin w Prompt 2).
        epub: otwarta publikacja (lub ``None``, gdy jeszcze nic nie wczytano).
        source_path: ścieżka źródłowego pliku EPUB (informacyjnie, np. handoff).
        generation_id: rosnący numer rewizji renderu (Prompt 3 użyje go do
            odrzucania spóźnionych wyników asynchronicznych).
    """

    session_id: str
    epub: Epub | None = None
    source_path: Path | None = None
    generation_id: int = 0

    @classmethod
    def create(cls, epub: Epub | None = None, source_path: Path | None = None) -> PreviewSession:
        """Tworzy sesję z losowym, nieprzewidywalnym ``session_id``."""
        return cls(session_id=secrets.token_hex(8), epub=epub, source_path=source_path)
