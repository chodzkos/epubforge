"""Providerzy metadanych — źródła danych pod :func:`epubforge.bookmeta.fetch_by_isbn`."""

from epubforge.bookmeta.providers.base import Provider
from epubforge.bookmeta.providers.bn import BNProvider
from epubforge.bookmeta.providers.googlebooks import GoogleBooksProvider
from epubforge.bookmeta.providers.openlibrary import OpenLibraryProvider

__all__ = [
    "BNProvider",
    "GoogleBooksProvider",
    "OpenLibraryProvider",
    "Provider",
]
