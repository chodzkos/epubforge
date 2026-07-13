"""Bramka least-privilege dla workflowów GitHub Actions (F-12).

Egzekwuje kryterium Promptu 11: kod zależności (instalacja z locka, testy, build
`.exe`, `pdoc`) NIE może dysponować tokenem `contents: write` ani utrwalonymi
credentials, a uprawnienia workflowów są jawne na poziomie jobów. Test parsuje
pliki `.github/workflows/*.yml` i sprawdza niezmienniki — regresja (np. dodanie
`contents: write` do joba budującego) wywala tę bramkę.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# Joby uruchamiające kod zależności — MUSZĄ mieć wyłącznie odczyt i checkout bez
# utrwalonych credentials. (plik workflow -> nazwy jobów).
DEPENDENCY_JOBS = {
    "test.yml": {"test", "base-cli", "package"},
    "build.yml": {"build-windows"},
    "docs.yml": {"build"},
    "codeql.yml": {"analyze"},
}


def _load(name: str) -> dict[str, Any]:
    """Wczytuje workflow YAML z katalogu `.github/workflows`."""
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def _effective_permissions(workflow: dict[str, Any], job: dict[str, Any]) -> Any:
    """Zwraca uprawnienia joba (per-job override albo dziedziczone z workflow)."""
    if "permissions" in job:
        return job["permissions"]
    return workflow.get("permissions")


def _checkout_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    """Zwraca kroki używające akcji `actions/checkout` w danym jobie."""
    return [
        step
        for step in job.get("steps", [])
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout")
    ]


@pytest.mark.parametrize("filename", sorted(DEPENDENCY_JOBS))
def test_workflow_default_permissions_are_zero(filename: str) -> None:
    """Domyślny poziom workflow to jawne, minimalne uprawnienia (nie dziedziczone)."""
    workflow = _load(filename)
    assert "permissions" in workflow, (
        f"{filename}: brak jawnego bloku permissions na poziomie workflow"
    )
    perms = workflow["permissions"]
    # Albo zero ({}), albo tylko-odczyt na poziomie całego workflow.
    assert perms == {} or perms.get("contents") == "read", (
        f"{filename}: domyślne permissions workflow nie są minimalne: {perms!r}"
    )


@pytest.mark.parametrize(
    ("filename", "job_name"),
    [(f, j) for f, jobs in DEPENDENCY_JOBS.items() for j in sorted(jobs)],
)
def test_dependency_jobs_have_no_write_and_no_persisted_creds(filename: str, job_name: str) -> None:
    """Joby z kodem zależności: brak `*: write` (poza security-events) + persist-credentials:false."""
    workflow = _load(filename)
    job = workflow["jobs"][job_name]

    perms = _effective_permissions(workflow, job)
    assert isinstance(perms, dict), (
        f"{filename}:{job_name}: uprawnienia muszą być jawne (dict), są {perms!r}"
    )

    for scope, level in perms.items():
        # CodeQL wymaga security-events:write, by zapisać wynik do zakładki Security —
        # to jedyny dozwolony write dla jobów zależnościowych i NIE jest to contents.
        if scope == "security-events":
            continue
        assert level != "write", (
            f"{filename}:{job_name}: job z kodem zależności ma {scope}: write (zakazane)"
        )
    # Kluczowe: żaden taki job nie może mieć prawa zapisu treści repo.
    assert perms.get("contents", "read") == "read", (
        f"{filename}:{job_name}: contents musi być 'read', jest {perms.get('contents')!r}"
    )

    checkouts = _checkout_steps(job)
    assert checkouts, f"{filename}:{job_name}: oczekiwano kroku actions/checkout"
    for step in checkouts:
        with_block = step.get("with") or {}
        assert with_block.get("persist-credentials") is False, (
            f"{filename}:{job_name}: checkout musi mieć persist-credentials: false"
        )


def test_release_job_has_no_project_dependencies() -> None:
    """Job publikujący Release ma contents:write, ale NIE instaluje zależności projektu."""
    workflow = _load("build.yml")
    release = workflow["jobs"]["release"]
    assert release["permissions"].get("contents") == "write"

    steps = release.get("steps", [])
    # Nie instaluje zależności: brak `uv sync`/`pip install` i brak checkoutu repo
    # (konsumuje wyłącznie gotowy artefakt).
    for step in steps:
        run = str(step.get("run", ""))
        assert "uv sync" not in run and "pip install" not in run, (
            "job release nie może instalować zależności projektu"
        )
        assert not str(step.get("uses", "")).startswith("actions/checkout"), (
            "job release nie powinien checkoutować repo (tylko pobrać artefakt)"
        )
    # Musi zweryfikować sumy pobranego artefaktu przed publikacją.
    joined = "\n".join(str(step.get("run", "")) for step in steps)
    assert "sha256sum -c" in joined, "job release musi weryfikować SHA256SUMS przed publikacją"


def test_deploy_pages_job_uses_official_mechanism() -> None:
    """Deploy docs idzie oficjalnym mechanizmem Pages (pages+id-token write, bez contents:write)."""
    workflow = _load("docs.yml")
    deploy = workflow["jobs"]["deploy"]
    perms = deploy["permissions"]
    assert perms.get("pages") == "write"
    assert perms.get("id-token") == "write"
    assert perms.get("contents", "read") != "write", "deploy Pages nie może mieć contents:write"

    uses = [str(step.get("uses", "")) for step in deploy.get("steps", [])]
    assert any(u.startswith("actions/deploy-pages@") for u in uses), (
        "deploy musi używać actions/deploy-pages (oficjalny mechanizm Pages)"
    )
    # Deploy nie instaluje zależności projektu ani nie checkoutuje repo.
    for step in deploy.get("steps", []):
        assert not str(step.get("uses", "")).startswith("actions/checkout")


def test_all_actions_pinned_by_full_sha() -> None:
    """Każda zewnętrzna akcja (uses: owner/repo@ref) jest przypięta po pełnym SHA (40 hex)."""
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses")
                if not uses or uses.startswith("./"):
                    continue  # akcje lokalne nie mają pinu SHA
                ref = uses.split("@", 1)[1] if "@" in uses else ""
                assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), (
                    f"{path.name}: akcja '{uses}' nie jest przypięta po pełnym SHA"
                )


def test_inno_setup_pinned_with_checksum_verification() -> None:
    """Inno Setup instalowany w przypiętej wersji z wymuszoną weryfikacją sumy."""
    workflow = _load("build.yml")
    build_job = workflow["jobs"]["build-windows"]
    inno_steps = [
        step
        for step in build_job.get("steps", [])
        if "innosetup" in str(step.get("run", "")).lower()
    ]
    assert inno_steps, "brak kroku instalującego Inno Setup"
    run = str(inno_steps[0]["run"])
    assert "--version=" in run, "Inno Setup musi mieć przypiętą dokładną wersję"
    assert "--require-checksums" in run, "instalacja Inno Setup musi wymuszać weryfikację sumy"
