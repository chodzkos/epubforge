"""Konserwatywne rozliczanie pamięci jednej sesji podglądu."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from epubforge.core import PendingChanges

_MIB = 1024 * 1024
_UTF8_CHUNK_CHARS = 64 * 1024

MAX_DIRTY_PENDING_BYTES = 64 * _MIB
# Konserwatywny model sesji (overlay + transition + retained providers +
# limit cache + rezerwa dokumentu), nie Chromium/OS RSS.
MAX_PREVIEW_RESIDENT_BYTES = 128 * _MIB


class PreviewBudgetKind(str, Enum):
    """Granica pamięci przekroczona przez żądanie podglądu."""

    DIRTY_PENDING = "dirty_pending"
    RESIDENT = "resident"


@dataclass(frozen=True)
class PreviewMemoryEstimate:
    """Logiczny overlay i konserwatywny koszt rezydentny generacji."""

    effective_bytes: int
    retained_generation_bytes: int
    cache_bytes: int
    main_document_reserve: int
    transition_bytes: int = 0

    @property
    def resident_bytes(self) -> int:
        """Zwraca przewidywany koszt aktywnej i budowanej generacji."""
        return (
            self.effective_bytes
            + self.transition_bytes
            + self.retained_generation_bytes
            + self.cache_bytes
            + self.main_document_reserve
        )


class PreviewBudgetExceededError(ValueError):
    """Kontrolowane przekroczenie jednego z budżetów podglądu."""

    def __init__(self, kind: PreviewBudgetKind, current_bytes: int, limit_bytes: int) -> None:
        super().__init__(f"{kind.value}: {current_bytes} > {limit_bytes}")
        self.kind = kind
        self.current_bytes = current_bytes
        self.limit_bytes = limit_bytes


def format_preview_bytes(value: int) -> str:
    """Formatuje bezpieczny rozmiar bez ujawniania treści ani ścieżek."""
    if value < 0:
        raise ValueError("Rozmiar pamięci nie może być ujemny")
    if value >= _MIB and value % _MIB == 0:
        return f"{value // _MIB} MiB"
    return f"{value} B"


def estimate_preview_memory(
    *,
    current_path: str,
    current_text: str,
    dirty: Mapping[str, str | bytes],
    pending: PendingChanges,
    dirty_pending_limit: int = MAX_DIRTY_PENDING_BYTES,
    resident_limit: int = MAX_PREVIEW_RESIDENT_BYTES,
    cache_bytes: int,
    retained_generation_bytes: int,
    main_document_reserve: int,
) -> PreviewMemoryEstimate:
    """Liczy effective overlay z precedence current > dirty > pending."""
    if (
        min(
            dirty_pending_limit,
            resident_limit,
            cache_bytes,
            retained_generation_bytes,
            main_document_reserve,
        )
        < 0
    ):
        raise ValueError("Rozmiary i limity pamięci nie mogą być ujemne")

    effective_bytes = _utf8_size(current_text)
    transition_bytes = _utf8_size(current_text)
    for path, value in dirty.items():
        if path != current_path:
            size = _payload_size(value)
            effective_bytes += size
            if isinstance(value, str):
                transition_bytes += size
    for path, value in pending.modified.items():
        if path != current_path and path not in dirty:
            effective_bytes += len(value)

    if effective_bytes > dirty_pending_limit:
        raise PreviewBudgetExceededError(
            PreviewBudgetKind.DIRTY_PENDING,
            effective_bytes,
            dirty_pending_limit,
        )
    estimate = PreviewMemoryEstimate(
        effective_bytes=effective_bytes,
        retained_generation_bytes=retained_generation_bytes,
        cache_bytes=cache_bytes,
        main_document_reserve=main_document_reserve,
        transition_bytes=transition_bytes,
    )
    if estimate.resident_bytes > resident_limit:
        raise PreviewBudgetExceededError(
            PreviewBudgetKind.RESIDENT,
            estimate.resident_bytes,
            resident_limit,
        )
    return estimate


def _payload_size(value: str | bytes) -> int:
    """Zwraca rozmiar payloadu bez tworzenia jego pełnej kopii bytes."""
    return _utf8_size(value) if isinstance(value, str) else len(value)


def _utf8_size(value: str) -> int:
    """Liczy UTF-8 przez małe bufory przejściowe."""
    total = 0
    for start in range(0, len(value), _UTF8_CHUNK_CHARS):
        total += len(value[start : start + _UTF8_CHUNK_CHARS].encode("utf-8"))
    return total
