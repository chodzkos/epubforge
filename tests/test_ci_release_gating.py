"""Test strukturalny bramki CI przed publikacją GitHub Release (EF-A12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build.yml"


def _load_jobs() -> dict[str, dict[str, Any]]:
    """Wczytuje joby workflow wydania bez modyfikowania YAML."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]


def _needs(job: dict[str, Any]) -> set[str]:
    """Normalizuje `needs` joba do zbioru identyfikatorów jobów."""
    value = job.get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def _ancestors(jobs: dict[str, dict[str, Any]], job_id: str) -> set[str]:
    """Wylicza przechodnich przodków joba w DAG GitHub Actions."""
    result: set[str] = set()
    pending = list(_needs(jobs[job_id]))
    while pending:
        dependency = pending.pop()
        assert dependency in jobs, f"nieznany job w needs: {dependency}"
        if dependency not in result:
            result.add(dependency)
            pending.extend(_needs(jobs[dependency]))
    return result


def test_release_requires_successful_tests_and_codeql_for_exact_sha() -> None:
    """Release czeka na kompletne Tests i CodeQL zakończone sukcesem dla tag SHA."""
    jobs = _load_jobs()
    release = jobs["release"]
    ancestors = _ancestors(jobs, "release")

    assert "verify-ci" in ancestors
    assert "always()" not in str(release.get("if", ""))

    gate = jobs["verify-ci"]
    assert gate.get("permissions") == {"actions": "read"}
    assert gate.get("continue-on-error") is not True
    assert "always()" not in str(gate.get("if", ""))

    script = "\n".join(str(step.get("run", "")) for step in gate.get("steps", []))
    assert "test.yml" in script
    assert "codeql.yml" in script
    assert "head_sha=${GITHUB_SHA}" in script
    assert "event=push" in script
    assert "status=success" in script
