"""Core library modules — biblioteka bez zależności od GUI."""

from epubforge.core.config import (
    Config,
    ConfigStore,
    config_dir,
    default_config_path,
    load_config,
    save_config,
)
from epubforge.core.detection import Tool, Tools, detect_with_cache
from epubforge.core.epub import Epub, ManifestItem
from epubforge.core.exceptions import (
    ConversionError,
    ConverterNotFoundError,
    EpubError,
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
)
from epubforge.core.metadata import Metadata

__all__ = [
    "Config",
    "ConfigStore",
    "ConversionError",
    "ConverterNotFoundError",
    "Epub",
    "EpubError",
    "EpubNotOpenError",
    "InvalidEpubError",
    "ManifestItem",
    "Metadata",
    "OpfNotFoundError",
    "Tool",
    "Tools",
    "config_dir",
    "default_config_path",
    "detect_with_cache",
    "load_config",
    "save_config",
]
