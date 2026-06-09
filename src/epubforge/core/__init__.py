"""Core library modules — biblioteka bez zależności od GUI."""

from epubforge.core.epub import Epub, ManifestItem
from epubforge.core.exceptions import (
    EpubError,
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
)
from epubforge.core.metadata import Metadata

__all__ = [
    "Epub",
    "EpubError",
    "EpubNotOpenError",
    "InvalidEpubError",
    "ManifestItem",
    "Metadata",
    "OpfNotFoundError",
]
