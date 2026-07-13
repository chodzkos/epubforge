"""Testy preflightu kolizji i polityki nadpisywania eksportu receptur.

Pokrywają: wykrycie kolizji wejść o tym samym stem, powtórzonego kroku eksportu i
istniejących plików; determinizm listy konfliktów niezależnie od kolejności wejść;
atomowy zapis eksportu (temp + os.replace); oraz zachowanie CLI ``run`` — przerwanie
przed zapisem (sekwencyjnie i dla jobs>1) i rozdzielenie wyjść przez ``unique``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge import recipes
from epubforge.cli.main import main
from epubforge.converters import ConversionResult, MobiOptions
from epubforge.recipes import STEP_REGISTRY, Recipe, RecipeStep, StepSpec
from epubforge.recipes_plan import plan_recipe_outputs

_TO_MOBI_RECIPE = """
name = "r"

[[steps]]
op = "to_mobi"
[steps.options]
fmt = "mobi"
"""


def _mobi_recipe(steps: int = 1) -> Recipe:
    """Receptura z ``steps`` krokami eksportu ``to_mobi`` (fmt=mobi)."""
    parts = tuple(RecipeStep("to_mobi", MobiOptions(fmt="mobi")) for _ in range(steps))
    return Recipe(name="r", description="", steps=parts, path=Path("r.toml"))


def _touch(path: Path, data: bytes = b"") -> Path:
    """Tworzy plik (z katalogami nadrzędnymi)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _fake_mobi_spec(record: list[Path] | None = None) -> StepSpec:
    """StepSpec eksportu, który zamiast konwersji zapisuje mały plik (bez Calibre)."""

    def fake_export(source: Path, out_dir: Path, options: MobiOptions) -> ConversionResult:
        if record is not None:
            record.append(out_dir)
        target = out_dir / f"{source.stem}.{options.fmt}"
        target.write_bytes(b"mobi:" + source.stem.encode())
        return ConversionResult(success=True, output_path=target, log="ok", engine="fake")

    return StepSpec(
        "export",
        fake_export,
        MobiOptions,
        output_name=lambda options, source: f"{source.stem}.{options.fmt}",
    )


# ── Planner: wykrywanie kolizji ─────────────────────────────────────────────


def test_planner_detects_input_collision(tmp_path: Path) -> None:
    """Dwa ``book.epub`` z różnych katalogów → kolizja tej samej ścieżki wyjściowej."""
    src_a = _touch(tmp_path / "a" / "book.epub")
    src_b = _touch(tmp_path / "b" / "book.epub")
    out = tmp_path / "out"
    plan = plan_recipe_outputs(_mobi_recipe(), [src_a, src_b], out, layout="preserve")
    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert conflict.kind == "input-collision"
    assert conflict.path == out / "book.mobi"
    assert conflict.sources == (src_a, src_b)


def test_planner_unique_layout_avoids_collision(tmp_path: Path) -> None:
    """Układ ``unique`` rozdziela wyjścia do podkatalogów per wejście — brak kolizji."""
    src_a = _touch(tmp_path / "a" / "book.epub")
    src_b = _touch(tmp_path / "b" / "book.epub")
    out = tmp_path / "out"
    plan = plan_recipe_outputs(_mobi_recipe(), [src_a, src_b], out, layout="unique")
    assert plan.conflicts == ()
    assert len({planned.path for planned in plan.outputs}) == 2


def test_planner_detects_duplicate_export_step(tmp_path: Path) -> None:
    """Dwa kroki eksportu o tym samym wyniku dla jednego wejścia → duplicate-step."""
    src = _touch(tmp_path / "book.epub")
    plan = plan_recipe_outputs(_mobi_recipe(steps=2), [src], tmp_path / "out")
    assert [c.kind for c in plan.conflicts] == ["duplicate-step"]


def test_planner_detects_existing_file_unless_force(tmp_path: Path) -> None:
    """Istniejący plik wyjściowy → konflikt ``exists``, chyba że ``force=True``."""
    src = _touch(tmp_path / "book.epub")
    out = tmp_path / "out"
    _touch(out / "book.mobi", b"old")
    plan = plan_recipe_outputs(_mobi_recipe(), [src], out)
    assert [c.kind for c in plan.conflicts] == ["exists"]
    forced = plan_recipe_outputs(_mobi_recipe(), [src], out, force=True)
    assert forced.conflicts == ()


def test_planner_conflicts_deterministic_regardless_of_order(tmp_path: Path) -> None:
    """Lista konfliktów jest identyczna niezależnie od kolejności wejść."""
    src_a = _touch(tmp_path / "a" / "book.epub")
    src_b = _touch(tmp_path / "b" / "book.epub")
    out = tmp_path / "out"
    first = plan_recipe_outputs(_mobi_recipe(), [src_a, src_b], out)
    second = plan_recipe_outputs(_mobi_recipe(), [src_b, src_a], out)
    assert first.conflicts == second.conflicts


# ── Atomowy zapis eksportu ──────────────────────────────────────────────────


def test_export_step_writes_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Eksport pisze przez katalog tymczasowy + os.replace; brak śmieci temp w celu."""
    out = tmp_path / "out"
    out.mkdir()
    seen_dirs: list[Path] = []
    monkeypatch.setitem(STEP_REGISTRY, "to_mobi", _fake_mobi_spec(seen_dirs))

    step = RecipeStep("to_mobi", MobiOptions(fmt="mobi"))
    result = recipes._run_export_step(step, tmp_path / "book.epub", out)

    assert result.output_path == out / "book.mobi"
    assert (out / "book.mobi").read_bytes() == b"mobi:book"
    # Konwerter dostał katalog TYMCZASOWY (nie finalny), a ten został posprzątany.
    assert seen_dirs[0] != out
    assert not seen_dirs[0].exists()
    # W katalogu docelowym został tylko finalny plik — żadnych pozostałości ``.tmp``.
    assert [child.name for child in out.iterdir()] == ["book.mobi"]


# ── CLI run: przerwanie przed zapisem i układ unique ────────────────────────


@pytest.mark.parametrize("jobs", [1, 2])
def test_run_aborts_on_input_collision(
    tmp_path: Path, jobs: int, capsys: pytest.CaptureFixture[str]
) -> None:
    """``run`` przerywa PRZED zapisem przy kolizji dwóch book.epub — sekwencyjnie i dla jobs>1.

    Bez preflightu jobs>1 nadpisałby jeden plik drugim niedeterministycznie; preflight
    daje deterministyczne przerwanie i nic nie zapisuje.
    """
    src_a = _touch(tmp_path / "a" / "book.epub")
    src_b = _touch(tmp_path / "b" / "book.epub")
    out = tmp_path / "out"
    recipe_path = _touch(tmp_path / "r.toml", _TO_MOBI_RECIPE.encode())

    code = main(
        [
            "run",
            str(recipe_path),
            str(src_a),
            str(src_b),
            "--out-dir",
            str(out),
            "--jobs",
            str(jobs),
        ]
    )
    assert code == 2
    assert "kolizj" in capsys.readouterr().err.lower()
    assert not out.exists()  # nic nie zapisano


def test_run_unique_layout_produces_distinct_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--output-layout unique`` pozwala przetworzyć kolidujące stemy do osobnych wyjść."""
    src_a = _touch(tmp_path / "a" / "book.epub")
    src_b = _touch(tmp_path / "b" / "book.epub")
    out = tmp_path / "out"
    recipe_path = _touch(tmp_path / "r.toml", _TO_MOBI_RECIPE.encode())
    monkeypatch.setitem(STEP_REGISTRY, "to_mobi", _fake_mobi_spec())

    code = main(
        [
            "run",
            str(recipe_path),
            str(src_a),
            str(src_b),
            "--out-dir",
            str(out),
            "--output-layout",
            "unique",
            "--jobs",
            "1",
        ]
    )
    assert code == 0
    produced = sorted(out.rglob("book.mobi"))
    assert len(produced) == 2  # osobne podkatalogi per wejście


def test_run_force_overwrites_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bez ``--force`` istniejący plik przerywa; z ``--force`` jest atomowo nadpisany."""
    src = _touch(tmp_path / "book.epub")
    out = tmp_path / "out"
    _touch(out / "book.mobi", b"old")
    recipe_path = _touch(tmp_path / "r.toml", _TO_MOBI_RECIPE.encode())
    monkeypatch.setitem(STEP_REGISTRY, "to_mobi", _fake_mobi_spec())

    blocked = main(["run", str(recipe_path), str(src), "--out-dir", str(out)])
    assert blocked == 2
    assert (out / "book.mobi").read_bytes() == b"old"  # nietknięty

    forced = main(["run", str(recipe_path), str(src), "--out-dir", str(out), "--force"])
    assert forced == 0
    assert (out / "book.mobi").read_bytes() == b"mobi:book"  # nadpisany
