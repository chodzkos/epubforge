"""Izolowana sesja publikacji i generacje zasobów podglądu."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import XmlSecurityError
from epubforge.gui.preview.dom_mapping import SourceNode, build_source_map
from epubforge.gui.preview.paths import PreviewRequest, build_preview_url
from epubforge.gui.preview.resources import ResourceProvider, create_resource_provider


@dataclass(frozen=True)
class SelectionState:
    """Stan zaznaczenia DOM zachowywany między generacjami."""

    internal_path: str | None = None
    element_key: str | None = None


@dataclass(frozen=True)
class PreviewGeneration:
    """Nieruchoma migawka jednej rewizji sesji, bez referencji do widgetów."""

    session_id: str
    generation_id: int
    current_document: str
    resource_provider: ResourceProvider
    dirty_overlay: Mapping[str, bytes]
    selection_state: SelectionState
    source_map: Mapping[str, SourceNode] = field(default_factory=lambda: MappingProxyType({}))

    def resource_url(self, path: str, fragment: str | None = None) -> str:
        """Buduje URL zasobu z jego własną rewizją."""
        return build_preview_url(
            self.session_id,
            path,
            self.generation_id,
            self.resource_provider.revision(path),
            fragment=fragment,
        )

    @property
    def document_url(self) -> str:
        """Kanoniczny URL bieżącego dokumentu tej generacji."""
        return self.resource_url(self.current_document)


@dataclass
class PreviewSession:
    """Jedna otwarta publikacja z osobnym, losowym originem.

    Nie przechowuje silnej referencji do :class:`Epub`, dlatego jej zamknięcie
    nie może utrzymać otwartego uchwytu ZIP.
    """

    session_id: str
    source_path: Path
    generation_id: int = 0
    current_document: str | None = None
    resource_provider: ResourceProvider | None = None
    dirty_overlay: Mapping[str, bytes] = field(default_factory=lambda: MappingProxyType({}))
    selection_state: SelectionState = field(default_factory=SelectionState)
    closed: bool = False

    @classmethod
    def create(cls, epub: Epub | None = None, source_path: Path | None = None) -> PreviewSession:
        """Tworzy sesję z 128-bitowym, nieprzewidywalnym identyfikatorem."""
        path = (
            source_path if source_path is not None else (epub.path if epub is not None else Path())
        )
        return cls(session_id=secrets.token_hex(16), source_path=Path(path))

    @property
    def origin(self) -> str:
        """Origin przypisany wyłącznie tej publikacji."""
        return f"epub-preview://{self.session_id}"

    def advance(
        self,
        epub: Epub,
        current_document: str,
        dirty_overlay: Mapping[str, str | bytes],
        media_types: Mapping[str, str] | None = None,
    ) -> PreviewGeneration:
        """Tworzy i aktywuje kolejną nieruchomą generację zasobów."""
        if self.closed:
            raise RuntimeError("Sesja podglądu jest zamknięta")
        generation_id = self.generation_id + 1
        provider = create_resource_provider(epub, generation_id, dirty_overlay, media_types)
        frozen_overlay = MappingProxyType(
            {
                path: value.encode("utf-8") if isinstance(value, str) else bytes(value)
                for path, value in dirty_overlay.items()
            }
        )
        self.generation_id = generation_id
        self.current_document = current_document
        self.resource_provider = provider
        self.dirty_overlay = frozen_overlay
        source_map = _source_map(provider, current_document, generation_id)
        return PreviewGeneration(
            session_id=self.session_id,
            generation_id=generation_id,
            current_document=current_document,
            resource_provider=provider,
            dirty_overlay=frozen_overlay,
            selection_state=self.selection_state,
            source_map=source_map,
        )

    def select(self, internal_path: str, element_key: str | None) -> None:
        """Zapamiętuje techniczny wybór elementu bez treści publikacji."""
        if self.closed:
            return
        self.selection_state = SelectionState(internal_path, element_key)

    def resolve(self, request: PreviewRequest) -> tuple[bytes, str] | None:
        """Rozwiązuje request wyłącznie dla aktywnego originu i generacji."""
        provider = self.resource_provider
        if (
            self.closed
            or provider is None
            or request.session_id != self.session_id
            or request.generation_id != self.generation_id
        ):
            return None
        data = provider.read(request.internal_path, request.generation_id)
        if data is None:
            return None
        return data, provider.media_type(request.internal_path)

    def close(self) -> None:
        """Nieodwracalnie unieważnia origin, generacje i wszystkie zasoby."""
        self.closed = True
        self.generation_id += 1
        self.current_document = None
        self.resource_provider = None
        self.dirty_overlay = MappingProxyType({})


def _source_map(
    provider: ResourceProvider, current_document: str, generation_id: int
) -> Mapping[str, SourceNode]:
    """Buduje mapę bieżącego dokumentu; błędny zasób daje pustą mapę."""
    data = provider.read(current_document, generation_id)
    if data is None:
        return MappingProxyType({})
    try:
        return MappingProxyType(build_source_map(data, current_document))
    except (ValueError, etree.XMLSyntaxError, XmlSecurityError):
        return MappingProxyType({})
