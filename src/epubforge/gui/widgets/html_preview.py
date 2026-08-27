"""Przybliżony, fail-closed podgląd XHTML oparty na QTextDocument.

Treść EPUB-a jest niezaufana. Fallback osadza wyłącznie małe, zweryfikowane
obrazy rastrowe z bieżącej publikacji i nie deleguje Qt żadnych odczytów plików,
sieci ani innych klas zasobów.
"""

from __future__ import annotations

import base64
import binascii
import posixpath
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, cast

import tinycss2
from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from lxml import etree
from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, QUrl, Signal
from PySide6.QtGui import QImageReader, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from epubforge.core import Epub, ResourceLimitError, Tool
from epubforge.core._xml_safe import parse_untrusted
from epubforge.gui.preview.paths import resolve_publication_path
from epubforge.gui.resource_limits import (
    MAX_FALLBACK_DECODED_IMAGE_BYTES,
    RasterStatus,
    probe_raster,
)
from epubforge.i18n import _

if TYPE_CHECKING:
    from epubforge.gui.preview.session import PreviewGeneration

_MAX_IMG_BYTES = 3 * 1024 * 1024
_PAPER_BG = "#ffffff"
_PAPER_FG = "#1a1a1a"
_ISOLATED_BASE = QUrl("epubforge-fallback:/publication/")
_FALLBACK_DOCUMENT = "_fallback_/document.xhtml"
_URL_ATTRIBUTES = frozenset({"href", "src", "poster", "data", "background", "cite"})


_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

ImageResolver = Callable[[str], bytes | None]
ImageIdentityResolver = Callable[[str], str | None]


def inline_images(
    xhtml: str,
    resolver: ImageResolver,
    max_bytes: int = _MAX_IMG_BYTES,
    *,
    base_path: str = _FALLBACK_DOCUMENT,
    max_decoded_bytes: int = MAX_FALLBACK_DECODED_IMAGE_BYTES,
    identity_resolver: ImageIdentityResolver | None = None,
) -> str:
    """Sanityzuje URL-e i osadza wyłącznie zweryfikowane rastry z publikacji.

    Surowe ``data:`` z XHTML nigdy nie jest zaufane. Każdy data URI w wyniku tej
    funkcji został wygenerowany tutaj z zasobu zwróconego przez ``resolver``.
    Błąd bezpiecznego parsowania zwraca pusty dokument, nigdy oryginalny HTML.
    """
    try:
        root = parse_untrusted(xhtml.encode("utf-8"), recover=True)
    except (etree.XMLSyntaxError, ValueError):
        return ""

    for element in root.iter():
        if _localname(element) == "style" and element.text:
            element.text = _sanitize_css(element.text, base_path, stylesheet=True)
        for attribute in list(element.attrib):
            local = etree.QName(attribute).localname.lower()
            value = element.get(attribute) or ""
            if local == "style":
                element.set(attribute, _sanitize_css(value, base_path))
            elif local == "srcset":
                # Pełna gramatyka srcset jest niezależną powierzchnią URL; fallback
                # jej nie potrzebuje, więc usuwa ją zamiast parsować częściowo.
                del element.attrib[attribute]
            elif (
                local in _URL_ATTRIBUTES
                and not (local == "src" and _localname(element) == "img")
                and resolve_publication_path(value, base_path) is None
            ):
                del element.attrib[attribute]

    embedded: dict[str, str] = {}
    blocked: set[str] = set()
    decoded_bytes = 0
    for img in [element for element in root.iter() if _localname(element) == "img"]:
        src_attribute = next(
            (
                attribute
                for attribute in img.attrib
                if isinstance(attribute, str)
                and etree.QName(attribute).localname.lower() == "src"
                and not attribute.startswith("{")
            ),
            None,
        )
        src = img.get(src_attribute) if src_attribute is not None else None
        for attribute in list(img.attrib):
            if etree.QName(attribute).localname.lower() == "src":
                del img.attrib[attribute]
        target = resolve_publication_path(src, base_path) if src is not None else None
        if src is None or target is None:
            continue
        identity = identity_resolver(target) if identity_resolver is not None else target
        if identity is None:
            continue
        if identity in embedded:
            img.set("src", embedded[identity])
            continue
        if identity in blocked:
            _replace_with_placeholder(img, posixpath.basename(target))
            continue
        data = resolver(src)
        if data is None:
            continue
        name = posixpath.basename(target)
        mime = _safe_raster_mime(data, name)
        probe = probe_raster(data)
        if (
            mime is None
            or len(data) > max_bytes
            or probe.status is not RasterStatus.OK
            or decoded_bytes + probe.decoded_bytes > max_decoded_bytes
        ):
            blocked.add(identity)
            _replace_with_placeholder(img, name)
        else:
            data_uri = _data_uri(data, mime)
            embedded[identity] = data_uri
            decoded_bytes += probe.decoded_bytes
            img.set("src", data_uri)
    return etree.tostring(root, encoding="unicode")


def _sanitize_css(css: str, base_path: str, *, stylesheet: bool = False) -> str:
    """Usuwa deklaracje/reguły z obcymi URL-ami przez parser gramatyki CSS."""
    if stylesheet:
        rules = tinycss2.parse_stylesheet(css, skip_comments=False, skip_whitespace=False)
        clean_rules = []
        for rule in rules:
            if rule.type == "at-rule" and getattr(rule, "lower_at_keyword", "") == "import":
                continue
            content = getattr(rule, "content", None)
            if content is not None and _tokens_have_unsafe_url(content, base_path):
                continue
            clean_rules.append(rule)
        return cast(str, tinycss2.serialize(clean_rules))
    declarations = tinycss2.parse_declaration_list(css, skip_comments=False, skip_whitespace=False)
    clean_declarations = [
        declaration
        for declaration in declarations
        if declaration.type != "declaration"
        or not _tokens_have_unsafe_url(declaration.value, base_path)
    ]
    return cast(str, tinycss2.serialize(clean_declarations))


def _tokens_have_unsafe_url(tokens: Sequence[Any], base_path: str) -> bool:
    """Wykrywa URLToken/``url()`` także z poprawnymi escape'ami CSS."""
    for token in tokens:
        token_type = getattr(token, "type", "")
        if token_type == "url":
            if resolve_publication_path(str(token.value), base_path) is None:
                return True
        elif token_type == "function":
            if token.lower_name == "url":
                value = tinycss2.serialize(token.arguments).strip().strip("'\"")
                if resolve_publication_path(value, base_path) is None:
                    return True
            elif _tokens_have_unsafe_url(token.arguments, base_path):
                return True
        content = getattr(token, "content", None)
        if content is not None and _tokens_have_unsafe_url(content, base_path):
            return True
    return False


def _embedded_data_urls(xhtml: str) -> set[str]:
    """Zbiera dokładne URI wygenerowanych obrazów do per-document allowlisty."""
    try:
        root = parse_untrusted(xhtml.encode("utf-8"), recover=True)
    except (etree.XMLSyntaxError, ValueError):
        return set()
    return {
        src
        for element in root.iter()
        if _localname(element) == "img"
        and (src := element.get("src")) is not None
        and src.startswith("data:")
    }


def _localname(element: etree._Element) -> str:
    """Lokalna nazwa tagu małymi literami (bez przestrzeni nazw)."""
    tag = cast(object, element.tag)
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _safe_raster_mime(data: bytes, name: str) -> str | None:
    """Rozpoznaje jawnie dozwolony raster po rozszerzeniu i wykrytym formacie bajtów."""
    suffix = posixpath.splitext(name)[1].lower()
    expected_format = {
        ".png": "png",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".gif": "gif",
        ".webp": "webp",
        ".bmp": "bmp",
    }.get(suffix)
    if expected_format is None:
        return None
    device = QBuffer()
    device.setData(QByteArray(data))
    if not device.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    detected = (
        bytes(QImageReader.imageFormat(device).data()).decode("ascii", errors="ignore").lower()
    )
    if detected != expected_format:
        return None
    return _MIME_BY_SUFFIX[suffix]


def _data_uri(data: bytes, mime: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _replace_with_placeholder(img: etree._Element, name: str) -> None:
    parent = img.getparent()
    if parent is None:
        if "src" in img.attrib:
            del img.attrib["src"]
        return
    placeholder = etree.Element("span")
    placeholder.text = _("[obraz: {name}]").format(name=name)
    placeholder.tail = img.tail
    parent.replace(img, placeholder)


class _PublicationTextBrowser(QTextBrowser):
    """Twarda granica: tylko allowlistowany data raster jako ImageResource."""

    def __init__(self) -> None:
        super().__init__()
        self._allowed_data_urls: set[str] = set()
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.document().setBaseUrl(_ISOLATED_BASE)

    def set_allowed_data_urls(self, urls: set[str]) -> None:
        self._allowed_data_urls = set(urls)

    def loadResource(self, resource_type: int, name: QUrl | str) -> object:  # noqa: N802
        qurl = name if isinstance(name, QUrl) else QUrl(name)
        url = qurl.toString()
        if (
            resource_type == QTextDocument.ResourceType.ImageResource
            and qurl.scheme().lower() == "data"
            and url in self._allowed_data_urls
        ):
            try:
                header, encoded = url.split(",", 1)
                if header not in {f"data:{mime};base64" for mime in _MIME_BY_SUFFIX.values()}:
                    return QByteArray()
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                return QByteArray()
            if len(data) > _MAX_IMG_BYTES:
                return QByteArray()
            if probe_raster(data).status is not RasterStatus.OK:
                return QByteArray()
            return QByteArray(data)
        return QByteArray()


class HtmlPreview(QWidget):
    """Przybliżony podgląd XHTML + handoff do Sigil/Calibre Editor."""

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
        self.view = _PublicationTextBrowser()
        self.view.setReadOnly(True)
        layout.addWidget(self.view, stretch=1)

    def _tool_button(self, label: str, key: str) -> QPushButton:
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

    def set_content(
        self,
        xhtml_text: str,
        epub: Epub | None,
        internal_path: str | None,
        generation: PreviewGeneration | None = None,
    ) -> None:
        """Sanityzuje i renderuje dokument z nową, per-document allowlistą."""
        base_path = internal_path if internal_path is not None else _FALLBACK_DOCUMENT
        resolver = (
            _epub_image_resolver(epub, internal_path, generation)
            if epub is not None and internal_path is not None
            else lambda _src: None
        )
        identity_resolver = (
            generation.resource_provider.canonical_path if generation is not None else None
        )
        html = inline_images(
            xhtml_text,
            resolver,
            base_path=base_path,
            identity_resolver=identity_resolver,
        )
        self.view.set_allowed_data_urls(set())
        previous_document = self.view.document()
        document = QTextDocument(self.view)
        document.setBaseUrl(_ISOLATED_BASE)
        self.view.setDocument(document)
        if isValid(previous_document):
            previous_document.deleteLater()
            QCoreApplication.sendPostedEvents(
                previous_document,
                QEvent.Type.DeferredDelete,
            )
        self.view.set_allowed_data_urls(_embedded_data_urls(html))
        self.view.setHtml(html)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._style_paper()

    def _style_paper(self) -> None:
        self.view.setStyleSheet(
            f"QTextBrowser {{ background-color: {_PAPER_BG}; color: {_PAPER_FG}; "
            f"border: 1px solid {self._theme.border}; }}"
        )


def _epub_image_resolver(
    epub: Epub,
    internal_path: str,
    generation: PreviewGeneration | None = None,
) -> ImageResolver:
    """Czyta logiczny winner obrazu przez provider generacji albo otwarty EPUB."""

    def resolve(src: str) -> bytes | None:
        target = resolve_publication_path(src, internal_path)
        if target is None:
            return None
        if generation is not None:
            return generation.resource_provider.read_limited(
                target,
                generation.generation_id,
                _MAX_IMG_BYTES,
            )
        try:
            return epub.read_file_limited(target, _MAX_IMG_BYTES)
        except (KeyError, OSError, ResourceLimitError):
            return None

    return resolve
