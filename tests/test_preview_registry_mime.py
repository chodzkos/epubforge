"""Regresja: główny dokument zawsze przechodzi przez sanityzację XHTML."""

from __future__ import annotations

from epubforge.gui.preview.registry import PreviewGenerationRegistry
from epubforge.gui.preview.resources import ResourceProvider
from epubforge.gui.preview.session import PreviewGeneration, SelectionState


class _MislabelledProvider(ResourceProvider):
    """Dostawca udający, że dokument XHTML jest aktywnym SVG."""

    def read(self, path: str, generation_id: int) -> bytes | None:
        """Zwraca testowy dokument dla aktywnej generacji."""
        return b"<html><body>x</body></html>" if generation_id == 1 else None

    def media_type(self, path: str) -> str:
        """Zwraca celowo mylący typ manifestu."""
        return "image/svg+xml"

    def exists(self, path: str) -> bool:
        """Testowy dokument zawsze istnieje."""
        return True

    def revision(self, path: str) -> int:
        """Stała rewizja fixture."""
        return 1


def test_registry_forces_xhtml_for_current_document() -> None:
    """MIME manifestu nie może ominąć sanityzatora strony głównej."""
    session_id = "0123456789abcdef0123456789abcdef"
    generation = PreviewGeneration(
        session_id=session_id,
        generation_id=1,
        current_document="OEBPS/ch.xhtml",
        resource_provider=_MislabelledProvider(),
        dirty_overlay={},
        selection_state=SelectionState(),
    )
    registry = PreviewGenerationRegistry()
    registry.activate(generation)
    resolved = registry.resolve_url(f"epub-preview://{session_id}/OEBPS/ch.xhtml?rev=1")
    assert resolved is not None
    assert resolved[1] == "application/xhtml+xml"
