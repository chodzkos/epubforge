"""Narzędzia do naprawy plików EPUB — dzielenie wyrazów, CSS, presety, typografia."""

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
from epubforge.fixers.typography import TypographyOptions, TypographyReport, fix_typography

__all__ = [
    "CssFixOptions",
    "CssPreset",
    "HyphenationOptions",
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
]
