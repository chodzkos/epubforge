"""Lekki backend podglądu — opakowanie istniejącego ``QTextBrowser``.

Zachowuje dotychczasową funkcjonalność podglądu (:class:`HtmlPreview`): przybliżony
render XHTML z osadzaniem obrazków z EPUB. Ten tor NIE importuje Qt WebEngine i jest
domyślnym fallbackiem, gdy dokładny podgląd jest niedostępny.
"""

from __future__ import annotations

from chodzkos_gui_kit.palette import Palette
from PySide6.QtWidgets import QVBoxLayout, QWidget

from epubforge.core import Tool
from epubforge.gui.preview.backend import (
    BackendKind,
    PreviewBackend,
    PreviewSnapshot,
    PreviewState,
    PreviewStatus,
)
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.widgets.html_preview import HtmlPreview


class TextDocumentPreviewBackend(PreviewBackend):
    """Backend ``QTextBrowser`` (przybliżony podgląd) — domyślny/fallback."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        theme: Palette | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = BackendKind.TEXT
        self._session: PreviewSession | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.html_preview = HtmlPreview(tools=tools, theme=theme)
        # Handoff Sigil/Calibre Editor przechodzi w górę do wspólnego sygnału.
        self.html_preview.open_external.connect(self.open_external)
        layout.addWidget(self.html_preview)

    def set_session(self, session: PreviewSession | None) -> None:
        """Ustawia sesję i zwalnia dokument poprzedniej publikacji."""
        previous = self._session
        self._session = session
        if previous is not None and previous is not session:
            self.html_preview.clear_content()

    def render_snapshot(self, snapshot: PreviewSnapshot) -> None:
        """Renderuje treść snapshotu przez ``HtmlPreview.set_content``."""
        self.status_changed.emit(PreviewStatus.RENDERING)
        self.html_preview.set_content(
            snapshot.xhtml,
            snapshot.epub,
            snapshot.internal_path,
            snapshot.generation,
        )
        self.status_changed.emit(PreviewStatus.READY)
        if snapshot.internal_path is not None:
            self.document_ready.emit(snapshot.internal_path)

    def capture_state(self) -> PreviewState:
        """Zapisuje względną pozycję scrolla podglądu."""
        bar = self.html_preview.view.verticalScrollBar()
        maximum = bar.maximum()
        ratio = bar.value() / maximum if maximum else 0.0
        return PreviewState(scroll_ratio=ratio)

    def restore_state(self, state: PreviewState) -> None:
        """Przywraca pozycję scrolla z zapamiętanego stanu."""
        bar = self.html_preview.view.verticalScrollBar()
        bar.setValue(round(state.scroll_ratio * bar.maximum()))

    def focus_node(self, node_id: str) -> None:
        """Lekki backend nie udostępnia mapowania elementów DOM."""
        return None

    def set_theme(self, palette: Palette) -> None:
        """Przemalowuje ramkę „papieru"; tło pozostaje białe (jak dotąd)."""
        self.html_preview.set_theme(palette)

    def dispose(self) -> None:
        """Zwalnia aktywny dokument i jego zdekodowane zasoby."""
        self._session = None
        self.html_preview.clear_content()
