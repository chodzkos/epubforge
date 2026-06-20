"""Przybliżony podgląd XHTML w edytorze (silnik QTextDocument) + handoff do narzędzi.

Renderujemy treść rozdziału przez ``QTextBrowser.setHtml`` — to świadomie
przybliżony obraz (Qt nie wykonuje JS ani pełnego CSS). Obrazki o względnych
``src`` są przepisywane na ``data:`` URI z bajtów EPUB (duże → placeholder, żeby
dokument nie puchł). Pasek nad podglądem niesie adnotację o ograniczeniach oraz
przyciski otwierające plik w Sigil / Calibre Editor (pełny podgląd).

Logika przepisywania obrazków (:func:`inline_images`) jest czysta i testowalna
bez Qt — przyjmuje resolver ``src -> bytes | None``.
"""

from __future__ import annotations

import base64
import posixpath
from collections.abc import Callable
from typing import cast
from urllib.parse import unquote

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from lxml import etree
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub, Tool
from epubforge.i18n import _

# Limit rozmiaru obrazka osadzanego jako data: URI (większe → placeholder).
_MAX_IMG_BYTES = 3 * 1024 * 1024
# Kolory „papieru" podglądu — CELOWO niezależne od motywu (jak inspektor CSS).
_PAPER_BG = "#ffffff"
_PAPER_FG = "#1a1a1a"

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}
_SKIP_SRC_PREFIXES = ("data:", "http://", "https://", "//")

ImageResolver = Callable[[str], bytes | None]


def inline_images(xhtml: str, resolver: ImageResolver, max_bytes: int = _MAX_IMG_BYTES) -> str:
    """Przepisuje względne ``<img src>`` na ``data:`` URI (duże → placeholder z nazwą).

    Args:
        xhtml: treść dokumentu XHTML.
        resolver: funkcja ``src -> bajty`` (lub ``None``, gdy pliku brak).
        max_bytes: powyżej tego rozmiaru obraz zastępujemy placeholderem.

    Returns:
        Zmodyfikowany dokument (lub oryginał, gdy nie da się sparsować).
    """
    try:
        root = cast(
            "etree._Element | None",
            etree.fromstring(xhtml.encode("utf-8"), etree.XMLParser(recover=True)),
        )
    except (etree.XMLSyntaxError, ValueError):
        return xhtml
    if root is None:
        return xhtml

    for img in [el for el in root.iter() if _localname(el) == "img"]:
        src = img.get("src")
        if not src or src.startswith(_SKIP_SRC_PREFIXES):
            continue
        data = resolver(src)
        if data is None:
            continue
        name = posixpath.basename(unquote(src.split("#", 1)[0]))
        if len(data) > max_bytes:
            _replace_with_placeholder(img, name)
        else:
            img.set("src", _data_uri(data, name))
    return etree.tostring(root, encoding="unicode")


def _localname(element: etree._Element) -> str:
    """Lokalna nazwa tagu małymi literami (bez przestrzeni nazw)."""
    tag = cast(object, element.tag)  # dla komentarzy/PI tag bywa wywoływalny, nie str
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _data_uri(data: bytes, name: str) -> str:
    """Buduje ``data:`` URI z bajtów obrazka (mime po rozszerzeniu nazwy)."""
    mime = _MIME_BY_SUFFIX.get(posixpath.splitext(name)[1].lower(), "application/octet-stream")
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _replace_with_placeholder(img: etree._Element, name: str) -> None:
    """Zastępuje za duży obrazek tekstowym placeholderem z nazwą pliku."""
    parent = img.getparent()
    if parent is None:
        return
    placeholder = etree.Element("span")
    placeholder.text = _("[obraz: {name}]").format(name=name)
    placeholder.tail = img.tail
    parent.replace(img, placeholder)


class HtmlPreview(QWidget):
    """Przybliżony podgląd XHTML + przyciski otwarcia w Sigil/Calibre Editor.

    Sygnały:
        open_external: żądanie otwarcia bieżącego pliku w narzędziu (klucz tool).
    """

    open_external = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        theme: Theme | None = None,
    ) -> None:
        super().__init__(parent)
        self._tools = tools or {}
        self._theme = theme if theme is not None else current_theme()
        self._build_ui()
        self._style_paper()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        note = QLabel(
            _(
                "Podgląd przybliżony (silnik Qt) — nie pokazuje pełnego CSS, fontów "
                "osadzonych ani układu czytnika. Pełny podgląd:"
            )
        )
        note.setWordWrap(True)
        bar.addWidget(note, stretch=1)
        self.sigil_button = self._tool_button(_("Sigil"), "sigil")
        self.calibre_button = self._tool_button(_("Calibre Editor"), "calibre_editor")
        bar.addWidget(self.sigil_button)
        bar.addWidget(self.calibre_button)
        layout.addLayout(bar)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.setReadOnly(True)
        layout.addWidget(self.view, stretch=1)

    def _tool_button(self, label: str, key: str) -> QPushButton:
        """Tworzy przycisk handoffu; włączony tylko gdy narzędzie wykryte."""
        button = QPushButton(label)
        tool = self._tools.get(key)
        available = tool is not None and tool.available and tool.path is not None
        button.setEnabled(available)
        button.setToolTip(
            _("Otwórz bieżący plik w: {tool}").format(tool=label)
            if available
            else _("Nie wykryto {tool}").format(tool=label)
        )
        button.clicked.connect(lambda: self.open_external.emit(key))
        return button

    def set_content(self, xhtml_text: str, epub: Epub | None, internal_path: str | None) -> None:
        """Renderuje XHTML w podglądzie, osadzając obrazki z otwartego EPUB."""
        if epub is not None and internal_path is not None:
            resolver = _epub_image_resolver(epub, internal_path)
            html = inline_images(xhtml_text, resolver)
        else:
            html = xhtml_text
        self.view.setHtml(html)

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw (ramka „papieru"); tło podglądu zostaje białe."""
        self._theme = theme
        self._style_paper()

    def _style_paper(self) -> None:
        """Stylizuje kartę podglądu: biały papier niezależny od motywu, ramka z Theme."""
        self.view.setStyleSheet(
            f"QTextBrowser {{ background-color: {_PAPER_BG}; color: {_PAPER_FG}; "
            f"border: 1px solid {self._theme.border}; }}"
        )


def _epub_image_resolver(epub: Epub, internal_path: str) -> ImageResolver:
    """Buduje resolver ``src -> bajty`` czytający obrazki z EPUB względem pliku."""
    base_dir = posixpath.dirname(internal_path)

    def resolve(src: str) -> bytes | None:
        path = unquote(src.split("#", 1)[0])
        target = posixpath.normpath(posixpath.join(base_dir, path)) if base_dir else path
        try:
            return epub.read_file(target)
        except (KeyError, OSError):
            return None

    return resolve
