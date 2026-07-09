"""Narzędzia do naprawy plików EPUB — dzielenie wyrazów, CSS, presety, typografia, obrazy."""

from epubforge.fixers.css_fixer import CssFixOptions, fix_css
from epubforge.fixers.css_presets import (
    CssPreset,
    PresetError,
    apply_preset,
    get_preset,
    import_user_preset,
    list_presets,
)
from epubforge.fixers.hyphenator import HyphenationOptions, hyphenate
from epubforge.fixers.images import (
    ImageFixOptions,
    ImageOptimizationError,
    ImageReport,
    optimize_images,
)
from epubforge.fixers.typography import TypographyOptions, TypographyReport, fix_typography

__all__ = [
    "CssFixOptions",
    "CssPreset",
    "HyphenationOptions",
    "ImageFixOptions",
    "ImageOptimizationError",
    "ImageReport",
    "PresetError",
    "TypographyOptions",
    "TypographyReport",
    "apply_preset",
    "fix_css",
    "fix_typography",
    "get_preset",
    "hyphenate",
    "import_user_preset",
    "list_presets",
    "optimize_images",
]
