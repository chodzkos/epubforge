"""Narzędzia do naprawy plików EPUB — dzielenie wyrazów, CSS, presety."""

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

__all__ = [
    "CssFixOptions",
    "CssPreset",
    "HyphenationOptions",
    "PresetError",
    "apply_preset",
    "fix_css",
    "get_preset",
    "hyphenate",
    "import_user_preset",
    "list_presets",
]
