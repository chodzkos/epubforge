"""Dedykowany profil, handler i izolacja nawigacji Qt WebEngine."""

from __future__ import annotations

import logging
import re

from lxml import etree
from PySide6.QtCore import QBuffer, QIODevice, QObject, QUrl, Signal
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlSchemeHandler,
)

from epubforge.core._xml_safe import XmlSecurityError
from epubforge.gui.preview.backend import DiagnosticCategory, DiagnosticEvent
from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME
from epubforge.gui.preview.registry import PreviewGenerationRegistry
from epubforge.gui.preview.rewrite import rewrite_css, rewrite_svg, rewrite_xhtml
from epubforge.gui.resource_limits import RasterStatus, probe_raster
from epubforge.i18n import _

logger = logging.getLogger(__name__)

_XHTML_TYPES = frozenset({"application/xhtml+xml", "text/html"})


def encoded_url(url: QUrl) -> str:
    """Zwraca URL bez przedwczesnego dekodowania percent-encoding."""
    raw = url.toEncoded().data()
    encoded = raw.tobytes() if isinstance(raw, memoryview) else bytes(raw)
    return encoded.decode("ascii", errors="strict")


class PreviewRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Blokuje wszystko poza aktywnym originem i kontrolowanymi obrazami data:."""

    def __init__(self, registry: PreviewGenerationRegistry, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry = registry

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:  # noqa: N802
        """Stosuje allowlistę schematu, originu, generacji i typu data:."""
        url = info.requestUrl()
        if url.scheme() == EPUB_PREVIEW_SCHEME:
            blocked = not self._registry.accepts_url(encoded_url(url))
        elif url.scheme() == "data":
            blocked = info.resourceType() != QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage
        else:
            blocked = True
        info.block(blocked)


class PreviewSchemeHandler(QWebEngineUrlSchemeHandler):
    """Odpowiada wyłącznie z nieruchomej generacji rejestru."""

    diagnostics = Signal(object)

    def __init__(self, registry: PreviewGenerationRegistry, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry = registry

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802
        """Waliduje URL i przepisuje kopie XHTML/CSS do izolowanego originu."""
        resolved = self._registry.resolve_resource(encoded_url(job.requestUrl()))
        if resolved is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        data, media_type = resolved.data, resolved.media_type
        raster_problem = raster_diagnostic(data, media_type, resolved.request.internal_path)
        if raster_problem is not None:
            self.diagnostics.emit(raster_problem)
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        try:
            if media_type in _XHTML_TYPES:
                data = rewrite_xhtml(
                    data,
                    resolved.generation,
                    resolved.request.internal_path,
                    self.diagnostics.emit,
                )
            elif media_type == "image/svg+xml":
                data = rewrite_svg(
                    data,
                    resolved.generation,
                    resolved.request.internal_path,
                    self.diagnostics.emit,
                )
            elif media_type == "text/css":
                data = rewrite_css(
                    data,
                    resolved.generation,
                    resolved.request.internal_path,
                    self.diagnostics.emit,
                )
        except (etree.XMLSyntaxError, XmlSecurityError, ValueError) as exc:
            logger.info("Odrzucono niepoprawny zasób podglądu: %s", exc)
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        buffer = make_reply_buffer(data, job)
        job.reply(media_type.encode("ascii", errors="strict"), buffer)


def raster_diagnostic(data: bytes, media_type: str, internal_path: str) -> DiagnosticEvent | None:
    """Zwraca bezpieczną diagnostykę rastra odrzuconego przed dekodem Chromium."""
    if not media_type.startswith("image/") or media_type == "image/svg+xml":
        return None
    probe = probe_raster(data)
    if probe.status is RasterStatus.OK:
        return None
    if probe.status is RasterStatus.TOO_LARGE:
        return DiagnosticEvent(
            category=DiagnosticCategory.PREVIEW_LIMIT,
            message=_("Obraz jest zbyt duży do bezpiecznego podglądu."),
            problem_kind="zbyt_duzy_obraz",
            internal_path=internal_path,
            requester=internal_path,
        )
    return DiagnosticEvent(
        category=DiagnosticCategory.BOOK_ERROR,
        message=_("Nie udało się wczytać obrazu."),
        problem_kind="niepoprawny_obraz",
        internal_path=internal_path,
        requester=internal_path,
    )


def make_reply_buffer(data: bytes, parent: QObject) -> QBuffer:
    """Tworzy otwarty QBuffer żyjący co najmniej tak długo jak job/parent."""
    buffer = QBuffer(parent)
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    return buffer


class SecurePreviewPage(QWebEnginePage):
    """Strona bez popupów i nawigacji poza aktywny origin."""

    external_navigation = Signal(str)
    dom_node_activated = Signal(str)

    def __init__(
        self,
        profile: QWebEngineProfile,
        registry: PreviewGenerationRegistry,
        parent: QObject | None = None,
        *,
        bridge_token: str = "",
    ) -> None:
        super().__init__(profile, parent)
        self._registry = registry
        self.featurePermissionRequested.connect(self._deny_legacy_permission)
        self._bridge_token = bridge_token
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(lambda permission: permission.deny())

    def javaScriptConsoleMessage(  # noqa: N802
        self, level: object, message: str, line_number: int, source_id: str
    ) -> None:
        """Przepuszcza tylko uwierzytelniony identyfikator, nigdy treść publikacji."""
        del level, line_number, source_id
        prefix = f"epubforge-node:{self._bridge_token}:"
        if not self._bridge_token or not message.startswith(prefix):
            return
        node_id = message[len(prefix) :]
        if re.fullmatch(r"[0-9a-f]{16}", node_id):
            self.dom_node_activated.emit(node_id)

    def acceptNavigationRequest(  # noqa: N802
        self,
        url: QUrl | str,
        navigation_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        """Pozwala tylko nawigować w aktywnym originie; link zewnętrzny sygnalizuje."""
        target = QUrl(url) if isinstance(url, str) else url
        allowed = self._registry.accepts_url(encoded_url(target))
        if (
            not allowed
            and navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        ):
            self.external_navigation.emit(target.toString())
        return allowed

    def createWindow(  # type: ignore[override]  # noqa: N802
        self, window_type: QWebEnginePage.WebWindowType
    ) -> QWebEnginePage | None:
        """Blokuje wszystkie nowe okna i popupy."""
        return None

    def _deny_legacy_permission(self, origin: QUrl, feature: QWebEnginePage.Feature) -> None:
        """Odrzuca starszy interfejs żądań uprawnień Qt."""
        self.setFeaturePermission(
            origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )


def create_secure_profile(
    parent: QObject,
) -> tuple[
    QWebEngineProfile,
    PreviewGenerationRegistry,
    PreviewSchemeHandler,
    PreviewRequestInterceptor,
]:
    """Tworzy prywatny profil off-the-record bez cache, storage i uprawnień."""
    registry = PreviewGenerationRegistry()
    profile = QWebEngineProfile(parent)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    profile.setHttpCacheMaximumSize(0)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    profile.setPersistentPermissionsPolicy(
        QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime
    )
    profile.setPushServiceEnabled(False)
    profile.setSpellCheckEnabled(False)
    profile.setSpellCheckLanguages([])
    profile.downloadRequested.connect(_cancel_download)

    handler = PreviewSchemeHandler(registry, profile)
    interceptor = PreviewRequestInterceptor(registry, profile)
    profile.installUrlSchemeHandler(EPUB_PREVIEW_SCHEME.encode("ascii"), handler)
    profile.setUrlRequestInterceptor(interceptor)
    return profile, registry, handler, interceptor


def harden_page_settings(settings: QWebEngineSettings) -> None:
    """Wyłącza skrypty publikacji, storage, sieciowe dodatki i niepotrzebne API."""
    attribute = QWebEngineSettings.WebAttribute
    disabled = (
        attribute.JavascriptEnabled,
        attribute.JavascriptCanOpenWindows,
        attribute.JavascriptCanAccessClipboard,
        attribute.LocalStorageEnabled,
        attribute.LocalContentCanAccessRemoteUrls,
        attribute.LocalContentCanAccessFileUrls,
        attribute.HyperlinkAuditingEnabled,
        attribute.PluginsEnabled,
        attribute.FullScreenSupportEnabled,
        attribute.ScreenCaptureEnabled,
        attribute.WebGLEnabled,
        attribute.Accelerated2dCanvasEnabled,
        attribute.AllowRunningInsecureContent,
        attribute.AllowGeolocationOnInsecureOrigins,
        attribute.DnsPrefetchEnabled,
        attribute.PdfViewerEnabled,
        attribute.NavigateOnDropEnabled,
        attribute.BackForwardCacheEnabled,
    )
    for item in disabled:
        settings.setAttribute(item, False)


def _cancel_download(download: QWebEngineDownloadRequest) -> None:
    """Anuluje każde pobieranie bez pytania użytkownika."""
    download.cancel()
