"""Asynchroniczne ładowanie bounded modelu arkusza dla inspektora CSS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from PySide6.QtCore import QObject, Signal

from epubforge.fixers.css_rules import CssRuleParseResult, parse_rules_bounded
from epubforge.gui.css_inspector_limits import (
    CSS_INSPECTOR_WORKER_THRESHOLD_BYTES,
    MAX_CSS_INSPECTOR_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULES,
    utf8_fits,
)
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel, Worker

Parser = Callable[..., CssRuleParseResult]
_RETIRED_WORKERS: set[Worker] = set()


@dataclass(frozen=True)
class CssSheetLoadRequest:
    """Niemutowalny snapshot jednego żądania parsera."""

    serial: int
    source: str
    revision: int


@dataclass(frozen=True)
class CssSheetLoadResult:
    """Wynik związany z dokładnym snapshotem i numerem żądania."""

    request: CssSheetLoadRequest
    parsed: CssRuleParseResult


class CssSheetLoader(QObject):
    """Serializuje parsery, odrzuca stale wyniki i nie dotyka widgetów w workerze."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        parser: Parser = parse_rules_bounded,
        parent: QObject | None = None,
        *,
        max_rules: int = MAX_CSS_INSPECTOR_RULES,
        max_declarations: int = MAX_CSS_INSPECTOR_DECLARATIONS,
        max_rule_declarations: int = MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
    ) -> None:
        super().__init__(parent)
        self._parser = parser
        self._max_rules = max_rules
        self._max_declarations = max_declarations
        self._max_rule_declarations = max_rule_declarations
        self._serial = 0
        self._worker: Worker | None = None
        self._pending: CssSheetLoadRequest | None = None
        self._active: CssSheetLoadRequest | None = None
        self._disposed = False

    def request(self, source: str, revision: int) -> None:
        """Parsuje mały snapshot od razu, a kosztowny poza GUI thread."""
        self._serial += 1
        request = CssSheetLoadRequest(self._serial, source, revision)
        if self._worker is not None:
            self._pending = request
            self._worker.cancel()
            return
        if utf8_fits(source, CSS_INSPECTOR_WORKER_THRESHOLD_BYTES):
            self.loaded.emit(CssSheetLoadResult(request, self._parse(source)))
            return
        self._start(request)

    def invalidate(self) -> None:
        """Unieważnia aktywne i oczekujące żądanie bez uruchamiania nowego."""
        self._serial += 1
        self._pending = None
        if self._worker is not None:
            self._worker.cancel()

    def dispose(self, wait_ms: int = 0) -> None:
        """Anuluje bez blokowania GUI; kończący QThread przechowuje globalny reaper."""
        if self._disposed:
            return
        self._disposed = True
        self.invalidate()
        worker = self._worker
        if worker is not None and not worker.wait(wait_ms):
            _RETIRED_WORKERS.add(worker)
            worker.finished.connect(lambda: _RETIRED_WORKERS.discard(worker))
        self._worker = None
        self._active = None

    def _parse(self, source: str) -> CssRuleParseResult:
        return self._parser(
            source,
            max_rules=self._max_rules,
            max_declarations=self._max_declarations,
            max_rule_declarations=self._max_rule_declarations,
        )

    def _start(self, request: CssSheetLoadRequest) -> None:
        worker = Worker(
            _parse_worker,
            self._parser,
            request,
            self._max_rules,
            self._max_declarations,
            self._max_rule_declarations,
        )
        self._worker = worker
        self._active = request
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        worker.start()

    def _on_done(self, value: object) -> None:
        outcome = cast(CssSheetLoadResult, value)
        if not self._disposed and outcome.request.serial == self._serial:
            self.loaded.emit(outcome)

    def _on_failed(self, message: str) -> None:
        active = self._active
        if not self._disposed and active is not None and active.serial == self._serial:
            self.failed.emit(message)

    def _on_finished(self) -> None:
        self._worker = None
        self._active = None
        pending, self._pending = self._pending, None
        if not self._disposed and pending is not None and pending.serial == self._serial:
            if utf8_fits(pending.source, CSS_INSPECTOR_WORKER_THRESHOLD_BYTES):
                self.loaded.emit(CssSheetLoadResult(pending, self._parse(pending.source)))
            else:
                self._start(pending)


def _parse_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    parser: Parser,
    request: CssSheetLoadRequest,
    max_rules: int,
    max_declarations: int,
    max_rule_declarations: int,
) -> CssSheetLoadResult | None:
    """Buduje wyłącznie pure-Python model z jednego snapshotu źródła."""
    if should_cancel():
        return None
    parsed = parser(
        request.source,
        max_rules=max_rules,
        max_declarations=max_declarations,
        max_rule_declarations=max_rule_declarations,
    )
    return None if should_cancel() else CssSheetLoadResult(request, parsed)
