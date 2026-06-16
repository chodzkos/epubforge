"""Pakiet spisu treści (TOC): model, odczyt, generowanie, zapis i naprawa.

Czysta logika bez zależności od GUI — używana przez CLI (`epubforge toc`) oraz
zakładkę „Spis treści".
"""

from epubforge.toc.generator import generate_toc
from epubforge.toc.model import (
    MoveMode,
    TocEntry,
    iter_entries,
    move_entry,
    parent_of,
    siblings_of,
)
from epubforge.toc.reader import TocSource, read_toc
from epubforge.toc.repair import TocProblem, repair_toc, validate_toc
from epubforge.toc.writer import write_toc

__all__ = [
    "MoveMode",
    "TocEntry",
    "TocProblem",
    "TocSource",
    "generate_toc",
    "iter_entries",
    "move_entry",
    "parent_of",
    "read_toc",
    "repair_toc",
    "siblings_of",
    "validate_toc",
    "write_toc",
]
