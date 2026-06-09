"""Core library modules — biblioteka bez zależności od GUI."""

from epubforge.core.epub import Epub, ManifestItem
from epubforge.core.exceptions import (
    EpubError,
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
)

__all__ = [
    "Epub",
    "EpubError",
    "EpubNotOpenError",
    "InvalidEpubError",
    "ManifestItem",
    "OpfNotFoundError",
]
