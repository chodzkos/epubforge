"""Narzędzia do naprawy plików EPUB — dzielenie wyrazów, CSS."""

from epubforge.fixers.hyphenator import HyphenationOptions, hyphenate

__all__ = [
    "HyphenationOptions",
    "hyphenate",
]
