"""Deterministyczny model budżetu pamięci sesji podglądu."""

from __future__ import annotations

import pytest

from epubforge.core import PendingChanges
from epubforge.gui.preview.memory_budget import (
    MAX_DIRTY_PENDING_BYTES,
    PreviewBudgetExceededError,
    PreviewBudgetKind,
    estimate_preview_memory,
)


def test_dirty_total_below_limit_is_accepted() -> None:
    estimate = estimate_preview_memory(
        current_path="OEBPS/text/current.xhtml",
        current_text="x",
        dirty={"OEBPS/styles/a.css": b"a" * 6},
        pending=PendingChanges({}, frozenset()),
        dirty_pending_limit=8,
        resident_limit=128,
        cache_bytes=0,
        retained_generation_bytes=0,
        main_document_reserve=0,
    )

    assert estimate.effective_bytes == 7
    assert estimate.effective_bytes <= MAX_DIRTY_PENDING_BYTES


def test_exact_dirty_pending_limit_is_accepted() -> None:
    estimate = estimate_preview_memory(
        current_path="current.xhtml",
        current_text="x",
        dirty={"a.css": b"a" * 7},
        pending=PendingChanges({}, frozenset()),
        dirty_pending_limit=8,
        resident_limit=128,
        cache_bytes=0,
        retained_generation_bytes=0,
        main_document_reserve=0,
    )

    assert estimate.effective_bytes == 8


def test_dirty_pending_limit_plus_one_is_rejected() -> None:
    with pytest.raises(PreviewBudgetExceededError) as captured:
        estimate_preview_memory(
            current_path="current.xhtml",
            current_text="x",
            dirty={"a.css": b"a" * 8},
            pending=PendingChanges({}, frozenset()),
            dirty_pending_limit=8,
            resident_limit=128,
            cache_bytes=0,
            retained_generation_bytes=0,
            main_document_reserve=0,
        )

    assert captured.value.kind is PreviewBudgetKind.DIRTY_PENDING
    assert captured.value.current_bytes == 9
    assert captured.value.limit_bytes == 8


def test_dirty_and_pending_different_paths_are_added() -> None:
    estimate = estimate_preview_memory(
        current_path="current.xhtml",
        current_text="x",
        dirty={"dirty.css": b"dd"},
        pending=PendingChanges({"pending.css": b"ppp"}, frozenset()),
        dirty_pending_limit=8,
        resident_limit=128,
        cache_bytes=0,
        retained_generation_bytes=0,
        main_document_reserve=0,
    )

    assert estimate.effective_bytes == 6


def test_dirty_shadows_pending_for_the_same_path() -> None:
    estimate = estimate_preview_memory(
        current_path="current.xhtml",
        current_text="x",
        dirty={"same.css": b"dd"},
        pending=PendingChanges({"same.css": b"pending"}, frozenset()),
        dirty_pending_limit=3,
        resident_limit=128,
        cache_bytes=0,
        retained_generation_bytes=0,
        main_document_reserve=0,
    )

    assert estimate.effective_bytes == 3


def test_resident_model_includes_provider_cache_and_main_document() -> None:
    estimate = estimate_preview_memory(
        current_path="current.xhtml",
        current_text="xx",
        dirty={"dirty.css": b"ddd"},
        pending=PendingChanges({"pending.css": b"pppp"}, frozenset()),
        dirty_pending_limit=16,
        resident_limit=28,
        cache_bytes=7,
        retained_generation_bytes=5,
        main_document_reserve=5,
    )

    assert estimate.effective_bytes == 9
    assert estimate.transition_bytes == 2
    assert estimate.resident_bytes == 28


def test_dirty_str_transition_counts_source_and_encoded_peak() -> None:
    """Prospective resident obejmuje str requestu i osobną kopię UTF-8."""
    estimate = estimate_preview_memory(
        current_path="current.xhtml",
        current_text="xx",
        dirty={"dirty.css": "ddd"},
        pending=PendingChanges({}, frozenset()),
        dirty_pending_limit=16,
        resident_limit=16,
        cache_bytes=0,
        retained_generation_bytes=0,
        main_document_reserve=0,
    )

    assert estimate.effective_bytes == 5
    assert estimate.transition_bytes == 5
    assert estimate.resident_bytes == 10
