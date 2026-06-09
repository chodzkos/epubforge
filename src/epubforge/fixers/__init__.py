"""Narzędzia do naprawy plików EPUB — dzielenie wyrazów, CSS."""

from epubforge.fixers.css_fixer import CssFixOptions, fix_css
from epubforge.fixers.hyphenator import HyphenationOptions, hyphenate

__all__ = [
    "CssFixOptions",
    "HyphenationOptions",
    "fix_css",
    "hyphenate",
]
