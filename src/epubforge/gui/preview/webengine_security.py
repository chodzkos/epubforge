"""Dedykowany profil, handler i izolacja nawigacji Qt WebEngine."""

from __future__ import annotations

import logging

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
from epubforge.gui.preview.preinit import EPUB_PREVIEW_SCHEME
from epubforge.gui.preview.registry import PreviewGenerationRegistry
from epubforge.gui.preview.sanitize import sanitize_xhtml

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

    def __init__(self, registry: PreviewGenerationRegistry, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry = registry

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802
        """Waliduje URL, sanityzuje XHTML i utrzymuje bufor przez parentowanie."""
        resolved = self._registry.resolve_url(encoded_url(job.requestUrl()))
        if resolved is None:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        data, media_type = resolved
        if media_type in _XHTML_TYPES:
            try:
                data = sanitize_xhtml(data)
            except (etree.XMLSyntaxError, XmlSecurityError, ValueError) as exc:
                logger.info("Odrzucono niepoprawny XHTML podglądu: %s", exc)
                job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
                return
        buffer = make_reply_buffer(data, job)
        job.reply(media_type.encode("ascii", errors="strict"), buffer)


def make_reply_buffer(data: bytes, parent: QObject) -> QBuffer:
    """Tworzy otwarty QBuffer żyjący co najmniej tak długo jak job/parent."""
    buffer = QBuffer(parent)
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    return buffer


class SecurePreviewPage(QWebEnginePage):
    """Strona bez popupów i nawigacji poza aktywny origin."""

    external_navigation = Signal(str)

    def __init__(
        self,
        profile: QWebEngineProfile,
        registry: PreviewGenerationRegistry,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(profile, parent)
        self._registry = registry
        self.featurePermissionRequested.connect(self._deny_legacy_permission)
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(lambda permission: permission.deny())

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
