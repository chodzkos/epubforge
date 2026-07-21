"""Wątkowo bezpieczny rejestr jednej aktywnej generacji podglądu."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from epubforge.gui.preview.paths import PreviewRequest, UnsafePreviewPathError, parse_preview_url
from epubforge.gui.preview.session import PreviewGeneration


@dataclass(frozen=True)
class ResolvedResource:
    """Zasób wraz z kontekstem potrzebnym do bezpiecznego przepisywania."""

    data: bytes
    media_type: str
    request: PreviewRequest
    generation: PreviewGeneration


class PreviewGenerationRegistry:
    """Udostępnia handlerowi wyłącznie nieruchomą, aktywną generację."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._generation: PreviewGeneration | None = None

    def activate(self, generation: PreviewGeneration) -> None:
        """Atomowo zastępuje aktywną generację."""
        with self._lock:
            self._generation = generation

    def clear(self) -> None:
        """Unieważnia wszystkie dotychczasowe URL-e."""
        with self._lock:
            self._generation = None

    def accepts_url(self, url: str) -> bool:
        """Czy URL należy do aktywnego originu i generacji."""
        try:
            request = parse_preview_url(url)
        except UnsafePreviewPathError:
            return False
        with self._lock:
            generation = self._generation
            return generation is not None and _matches(generation, request)

    def resolve_resource(self, url: str) -> ResolvedResource | None:
        """Rozwiązuje URL i zachowuje kontekst generacji bez dostępu do GUI."""
        try:
            request = parse_preview_url(url)
        except UnsafePreviewPathError:
            return None
        with self._lock:
            generation = self._generation
            if generation is None or not _matches(generation, request):
                return None
            provider = generation.resource_provider
        if provider.revision(request.internal_path) != request.revision:
            return None
        # Realny provider preładuje zasoby w workerze; handler nie może wykonywać
        # stat/ZIP I/O. Fallback zachowuje kompatybilność prostych providerów testowych.
        prepared_read = getattr(provider, "read_prepared", provider.read)
        data = prepared_read(request.internal_path, request.generation_id)
        if data is None:
            return None
        with self._lock:
            if self._generation is not generation:
                return None
        media_type = provider.media_type(request.internal_path)
        if request.internal_path == generation.current_document:
            media_type = "application/xhtml+xml"
        return ResolvedResource(data, media_type, request, generation)

    def resolve_url(self, url: str) -> tuple[bytes, str] | None:
        """Kompatybilny skrót zwracający bajty i media type."""
        resolved = self.resolve_resource(url)
        if resolved is None:
            return None
        return resolved.data, resolved.media_type


def _matches(generation: PreviewGeneration, request: PreviewRequest) -> bool:
    """Porównuje origin i generację bez efektów ubocznych."""
    return (
        generation.session_id == request.session_id
        and generation.generation_id == request.generation_id
    )
