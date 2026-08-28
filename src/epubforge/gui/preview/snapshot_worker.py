"""Asynchroniczne przygotowanie snapshotu poza głównym wątkiem Qt."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Slot
from shiboken6 import isValid

from epubforge.core import Epub, PendingChanges
from epubforge.gui.css_inspector_limits import utf8_fits
from epubforge.gui.preview.backend import (
    DiagnosticCategory,
    DiagnosticEvent,
    PreviewBackend,
    PreviewSnapshot,
    PreviewStatus,
)
from epubforge.gui.preview.controller import PreviewController, SnapshotResult
from epubforge.gui.preview.memory_budget import (
    MAX_DIRTY_PENDING_BYTES,
    MAX_PREVIEW_RESIDENT_BYTES,
    PreviewBudgetExceededError,
    PreviewBudgetKind,
    estimate_preview_memory,
    format_preview_bytes,
)
from epubforge.gui.preview.resources import SnapshotResourceProvider
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.text_backend import TextDocumentPreviewBackend
from epubforge.gui.resource_limits import (
    MAX_MAIN_PREVIEW_BYTES,
    MAX_PREVIEW_CSS_BYTES,
    PreviewTextKind,
    find_preview_text_violation,
)
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel, Worker
from epubforge.i18n import _


@dataclass(frozen=True)
class SnapshotRequest:
    """Gotowe dane pamięciowe przekazywane workerowi, bez referencji do widgetów."""

    serial: int
    epub: Epub
    session: PreviewSession
    current_path: str
    current_text: str
    dirty: Mapping[str, str | bytes]
    media_types: Mapping[str, str]
    pending: PendingChanges
    retained_providers: tuple[SnapshotResourceProvider, ...] = ()


def _budget_diagnostic(exc: PreviewBudgetExceededError, internal_path: str) -> DiagnosticEvent:
    """Buduje bezpieczną diagnostykę wspólną dla GUI i workera."""
    message = _(
        "Podgląd jest zbyt duży do bezpiecznego wygenerowania. Rozmiar: {current}; limit: {limit}."
    ).format(
        current=format_preview_bytes(exc.current_bytes),
        limit=format_preview_bytes(exc.limit_bytes),
    )
    return DiagnosticEvent(
        category=DiagnosticCategory.PREVIEW_LIMIT,
        message=message,
        problem_kind="zbyt_duza_sesja_podgladu",
        internal_path=internal_path,
        requester=internal_path,
    )


def build_snapshot_job(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    controller: PreviewController,
    request: SnapshotRequest,
) -> SnapshotResult | None:
    """Buduje snapshot w workerze; funkcja nie importuje ani nie dotyka widgetów."""
    if should_cancel():
        return None
    retained_bytes = sum(provider.resident_bytes for provider in request.retained_providers)
    provider = request.session.resource_provider
    if provider is not None and all(provider is not item for item in request.retained_providers):
        if not isinstance(provider, SnapshotResourceProvider):
            violation = PreviewBudgetExceededError(
                PreviewBudgetKind.RESIDENT,
                MAX_PREVIEW_RESIDENT_BYTES + 1,
                MAX_PREVIEW_RESIDENT_BYTES,
            )
            return SnapshotResult(None, _budget_diagnostic(violation, request.current_path))
        retained_bytes += provider.resident_bytes
    try:
        estimate_preview_memory(
            current_path=request.current_path,
            current_text=request.current_text,
            dirty=request.dirty,
            pending=request.pending,
            dirty_pending_limit=MAX_DIRTY_PENDING_BYTES,
            resident_limit=MAX_PREVIEW_RESIDENT_BYTES,
            cache_bytes=request.session.cache_stats().limits.total,
            retained_generation_bytes=retained_bytes,
            main_document_reserve=MAX_MAIN_PREVIEW_BYTES,
        )
    except PreviewBudgetExceededError as exc:
        return SnapshotResult(None, _budget_diagnostic(exc, request.current_path))
    result = controller.build(
        epub=request.epub,
        session=request.session,
        current_path=request.current_path,
        current_text=request.current_text,
        dirty=request.dirty,
        media_types=request.media_types,
        pending=request.pending,
    )
    return None if should_cancel() else result


class SnapshotWorkerMixin:
    """Mixin kolejkujący najwyżej jeden build i jedno najnowsze żądanie."""

    _controller: PreviewController
    _session: PreviewSession | None
    _status: PreviewStatus
    _generation: int
    _last_snapshot: PreviewSnapshot | None
    _active: PreviewBackend
    _text_backend: TextDocumentPreviewBackend
    _comparison_backend: PreviewBackend | None
    diagnostics: Any
    fallback_label: Any
    _update_status: Callable[[], None]
    _render_snapshot_into: Callable[[PreviewBackend, PreviewSnapshot], None]

    def _init_snapshot_pipeline(self) -> None:
        self._controller = PreviewController()
        self._snapshot_serial = 0
        self._snapshot_worker: Worker | None = None
        self._snapshot_request: SnapshotRequest | None = None
        self._pending_snapshot: SnapshotRequest | None = None

    def render_document(
        self,
        xhtml: str,
        epub: Epub | None,
        internal_path: str | None,
        *,
        dirty: Mapping[str, str | bytes] | None = None,
        media_types: Mapping[str, str] | None = None,
    ) -> None:
        """Kopiuje dane edytora i zleca ciężkie przygotowanie poza wątkiem GUI."""
        current_media_types = media_types or {}
        current_dirty = dirty or {}
        current_pending = (
            epub.pending_changes() if epub is not None else PendingChanges({}, frozenset())
        )
        retained_providers: tuple[SnapshotResourceProvider, ...] = ()
        is_css = internal_path is not None and (
            internal_path.lower().endswith(".css")
            or current_media_types.get(internal_path, "").lower() == "text/css"
        )
        violation = find_preview_text_violation(
            current_path=internal_path,
            dirty=current_dirty,
            pending_sizes={path: len(data) for path, data in current_pending.modified.items()},
            media_types=current_media_types,
            document_limit=MAX_MAIN_PREVIEW_BYTES,
            css_limit=MAX_PREVIEW_CSS_BYTES,
        )
        if violation is not None:
            violation_is_css = violation.kind is PreviewTextKind.CSS
            self._reject_oversized_preview(
                _("Arkusz CSS jest zbyt duży do bezpiecznego podglądu.")
                if violation_is_css
                else _("Dokument jest zbyt duży do bezpiecznego podglądu."),
                violation.path,
                "zbyt_duzy_arkusz_css" if violation_is_css else "zbyt_duzy_dokument",
            )
            return
        limit = MAX_PREVIEW_CSS_BYTES if is_css else MAX_MAIN_PREVIEW_BYTES
        if not utf8_fits(xhtml, limit):
            self._reject_oversized_preview(
                _("Arkusz CSS jest zbyt duży do bezpiecznego podglądu.")
                if is_css
                else _("Dokument jest zbyt duży do bezpiecznego podglądu."),
                internal_path,
                "zbyt_duzy_arkusz_css" if is_css else "zbyt_duzy_dokument",
            )
            return
        if epub is not None and internal_path is not None and self._session is not None:
            try:
                retained_providers = self._retained_generation_providers()
                retained_generation_bytes = sum(
                    provider.resident_bytes for provider in retained_providers
                )
                estimate_preview_memory(
                    current_path=internal_path,
                    current_text=xhtml,
                    dirty=current_dirty,
                    pending=current_pending,
                    dirty_pending_limit=MAX_DIRTY_PENDING_BYTES,
                    resident_limit=MAX_PREVIEW_RESIDENT_BYTES,
                    cache_bytes=self._session.cache_stats().limits.total,
                    retained_generation_bytes=retained_generation_bytes,
                    main_document_reserve=MAX_MAIN_PREVIEW_BYTES,
                )
            except PreviewBudgetExceededError as exc:
                diagnostic = _budget_diagnostic(exc, internal_path)
                self._reject_oversized_preview(
                    diagnostic.message,
                    internal_path,
                    diagnostic.problem_kind or "zbyt_duza_sesja_podgladu",
                )
                return
        if epub is None or internal_path is None or self._session is None:
            self._generation += 1
            snapshot = PreviewSnapshot(xhtml, epub, internal_path, self._generation)
            self._last_snapshot = snapshot
            target = self._active if epub is not None else self._text_backend
            self._render_snapshot_into(target, snapshot)
            if self._comparison_backend is not None and target is self._active:
                self._render_snapshot_into(self._comparison_backend, snapshot)
            return
        self._snapshot_serial += 1
        request = SnapshotRequest(
            serial=self._snapshot_serial,
            epub=epub,
            session=self._session,
            current_path=internal_path,
            current_text=str(xhtml),
            dirty=dict(current_dirty),
            media_types=dict(current_media_types),
            pending=current_pending,
            retained_providers=retained_providers,
        )
        self._status = PreviewStatus.RENDERING
        self._update_status()
        if self._snapshot_worker is not None:
            self._pending_snapshot = request
            self._snapshot_worker.cancel()
            return
        self._start_snapshot_worker(request)

    def _retained_generation_providers(self) -> tuple[SnapshotResourceProvider, ...]:
        """Zbiera unikalne providery sesji, snapshotu i backendów."""
        candidates: list[object] = []
        snapshot = self._last_snapshot
        if snapshot is not None and snapshot.generation is not None:
            candidates.append(snapshot.generation.resource_provider)
        if self._session is not None and self._session.resource_provider is not None:
            candidates.append(self._session.resource_provider)
        for backend in (
            self._active,
            getattr(self, "_webengine_backend", None),
            self._comparison_backend,
        ):
            if backend is None:
                continue
            reporter = getattr(backend, "retained_resource_providers", None)
            reported = reporter() if callable(reporter) else ()
            if isinstance(reported, tuple):
                candidates.extend(reported)
            leftover = getattr(backend, "_last_snapshot", None)
            generation = getattr(leftover, "generation", None)
            if generation is not None:
                candidates.append(generation.resource_provider)
        retained: list[SnapshotResourceProvider] = []
        seen: set[int] = set()
        for provider in candidates:
            identity = id(provider)
            if identity in seen:
                continue
            seen.add(identity)
            if not isinstance(provider, SnapshotResourceProvider):
                raise PreviewBudgetExceededError(
                    PreviewBudgetKind.RESIDENT,
                    MAX_PREVIEW_RESIDENT_BYTES + 1,
                    MAX_PREVIEW_RESIDENT_BYTES,
                )
            retained.append(provider)
        return tuple(retained)

    def _reject_oversized_preview(
        self, message: str, internal_path: str | None, problem_kind: str
    ) -> None:
        """Unieważnia starsze żądania i pokazuje diagnostykę bez budowania snapshotu."""
        self._snapshot_serial += 1
        self._pending_snapshot = None
        if self._snapshot_worker is not None:
            self._snapshot_worker.cancel()
        self._status = PreviewStatus.LAST_GOOD
        self._update_status()
        self.fallback_label.setText(message)
        self.fallback_label.setVisible(True)
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.PREVIEW_LIMIT,
                message=message,
                problem_kind=problem_kind,
                internal_path=internal_path,
                requester=internal_path,
            )
        )

    def _start_snapshot_worker(self, request: SnapshotRequest) -> None:
        worker = Worker(build_snapshot_job, self._controller, request)
        self._snapshot_worker = worker
        self._snapshot_request = request
        # Bezpośrednie sloty zachowują kontekst odbiorcy QObject. Qt automatycznie
        # odłącza oczekujące callbacki, gdy BookPreview zostanie usunięty; lambda
        # przechwytująca ``self`` mogła wykonać się już po skasowaniu jego dzieci.
        worker.done.connect(self._snapshot_worker_done)
        worker.failed.connect(self._snapshot_worker_failed)
        worker.finished.connect(self._snapshot_worker_finished)
        # Sprzątanie QThread nie może zależeć od czasu życia widgetu-odbiorcy.
        worker.finished.connect(worker.deleteLater)
        worker.start()

    @Slot(object)
    def _snapshot_worker_done(self, value: object) -> None:
        request = self._snapshot_request
        if request is not None:
            self._snapshot_ready(request, value)

    @Slot(str)
    def _snapshot_worker_failed(self, message: str) -> None:
        request = self._snapshot_request
        if request is not None:
            self._snapshot_failed(request, message)

    def _snapshot_ready(self, request: SnapshotRequest, value: object) -> None:
        if (
            not isValid(self)
            or getattr(self, "_disposed", False)
            or request.serial != self._snapshot_serial
            or request.session is not self._session
            or not isinstance(value, SnapshotResult)
        ):
            return
        if value.snapshot is None:
            self._status = PreviewStatus.LAST_GOOD
            self._update_status()
            if value.diagnostic is not None:
                self.diagnostics.emit(value.diagnostic)
                self.fallback_label.setText(value.diagnostic.message)
                self.fallback_label.setVisible(True)
            return
        snapshot = value.snapshot
        self._generation = snapshot.generation_id
        self._last_snapshot = snapshot
        self.fallback_label.setVisible(False)
        self._active.set_session(self._session)
        self._render_snapshot_into(self._active, snapshot)
        if self._comparison_backend is not None:
            self._comparison_backend.set_session(self._session)
            self._render_snapshot_into(self._comparison_backend, snapshot)

    def _snapshot_failed(self, request: SnapshotRequest, message: str) -> None:
        if (
            not isValid(self)
            or getattr(self, "_disposed", False)
            or request.serial != self._snapshot_serial
            or request.session is not self._session
        ):
            return
        self._status = PreviewStatus.LAST_GOOD
        self._update_status()
        self.diagnostics.emit(
            DiagnosticEvent(
                category=DiagnosticCategory.BOOK_ERROR,
                message=_("Nie udało się przygotować podglądu: {error}").format(error=message),
                problem_kind="snapshot_worker",
                internal_path=request.current_path,
            )
        )

    @Slot()
    def _snapshot_worker_finished(self) -> None:
        if not isValid(self):
            return
        self._snapshot_worker = None
        self._snapshot_request = None
        pending, self._pending_snapshot = self._pending_snapshot, None
        if (
            not getattr(self, "_disposed", False)
            and pending is not None
            and pending.session is self._session
        ):
            self._start_snapshot_worker(pending)

    def _cancel_snapshot_pipeline(self, *, wait_ms: int = 0) -> None:
        """Unieważnia callbacki i opcjonalnie krótko czeka przy niszczeniu widgetu."""
        self._snapshot_serial += 1
        self._pending_snapshot = None
        worker = self._snapshot_worker
        if worker is not None:
            worker.cancel()
            if wait_ms > 0:
                worker.wait(wait_ms)
