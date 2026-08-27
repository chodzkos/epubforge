"""Core library modules — biblioteka bez zależności od GUI."""

from epubforge.core._archive import DEFAULT_LIMITS, ArchiveLimits
from epubforge.core.config import (
    Config,
    ConfigStore,
    config_dir,
    default_config_path,
    load_config,
    save_config,
)
from epubforge.core.detection import Tool, Tools, detect_with_cache
from epubforge.core.epub import (
    Epub,
    ManifestItem,
    PendingChanges,
    SourceIdentity,
    source_identity_from_stat,
)
from epubforge.core.exceptions import (
    ConversionError,
    ConverterNotFoundError,
    EpubError,
    EpubNotOpenError,
    InvalidEpubError,
    InvalidPublicationHrefError,
    MissingPublicationMemberError,
    OpfNotFoundError,
    ResourceLimitError,
    ValidationError,
)
from epubforge.core.metadata import (
    Metadata,
    get_number_of_pages,
    remove_number_of_pages,
    set_number_of_pages,
    supports_number_of_pages,
)

__all__ = [
    "DEFAULT_LIMITS",
    "ArchiveLimits",
    "Config",
    "ConfigStore",
    "ConversionError",
    "ConverterNotFoundError",
    "Epub",
    "EpubError",
    "EpubNotOpenError",
    "InvalidEpubError",
    "InvalidPublicationHrefError",
    "ManifestItem",
    "Metadata",
    "MissingPublicationMemberError",
    "OpfNotFoundError",
    "PendingChanges",
    "ResourceLimitError",
    "SourceIdentity",
    "Tool",
    "Tools",
    "ValidationError",
    "config_dir",
    "default_config_path",
    "detect_with_cache",
    "get_number_of_pages",
    "load_config",
    "remove_number_of_pages",
    "save_config",
    "set_number_of_pages",
    "source_identity_from_stat",
    "supports_number_of_pages",
]
