"""Testy strumieniowych wariantów konwerterów i przerywalnej walidacji (Etap 19)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ValidationError
from epubforge.core.streaming import ProcessResult
from epubforge.validators import epubcheck as ec

# Pakiet ``converters`` re-eksportuje funkcje (to_epub itd.), przez co nazwy
# submodułów są w nim przesłonięte — pobieramy prawdziwe moduły z sys.modules.
epub_mod = importlib.import_module("epubforge.converters.to_epub")
mobi_mod = importlib.import_module("epubforge.converters.to_mobi")
kfx_mod = importlib.import_module("epubforge.converters.to_kfx")

_NOOP_LINE = lambda text, level: None  # noqa: E731


def _tool(name: str, path: str) -> Tool:
    return Tool(name, Path(path), available=True)


# ── to_epub_streaming ────────────────────────────────────────────────────────


def test_to_epub_streaming_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kod 0 → sukces, brak anulowania."""
    monkeypatch.setattr(
        epub_mod, "_resolve_engine", lambda s, e: ("pandoc", _tool("pandoc", "/bin/pandoc"))
    )
    monkeypatch.setattr(epub_mod, "run_command_streaming", lambda *a, **k: ProcessResult(0))
    result = epub_mod.to_epub_streaming(tmp_path / "a.txt", tmp_path / "a.epub", on_line=_NOOP_LINE)
    assert result.success and not result.cancelled


def test_to_epub_streaming_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """cancelled=True → success=False, cancelled=True."""
    monkeypatch.setattr(
        epub_mod, "_resolve_engine", lambda s, e: ("pandoc", _tool("pandoc", "/bin/pandoc"))
    )
    monkeypatch.setattr(
        epub_mod, "run_command_streaming", lambda *a, **k: ProcessResult(0, cancelled=True)
    )
    result = epub_mod.to_epub_streaming(tmp_path / "a.txt", tmp_path / "a.epub", on_line=_NOOP_LINE)
    assert result.cancelled and not result.success


def test_to_epub_streaming_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Niezerowy kod → ConversionError."""
    monkeypatch.setattr(
        epub_mod, "_resolve_engine", lambda s, e: ("calibre", _tool("calibre", "/bin/ec"))
    )
    monkeypatch.setattr(epub_mod, "run_command_streaming", lambda *a, **k: ProcessResult(5))
    with pytest.raises(ConversionError):
        epub_mod.to_epub_streaming(tmp_path / "a.txt", tmp_path / "a.epub", on_line=_NOOP_LINE)


# ── to_mobi_streaming ────────────────────────────────────────────────────────


def test_to_mobi_streaming_calibre_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silnik calibre: kod 0 → sukces (bez naprawy EPUB)."""
    monkeypatch.setattr(
        mobi_mod, "_resolve_engine", lambda e: ("calibre", _tool("calibre", "/bin/ec"))
    )
    monkeypatch.setattr(mobi_mod, "run_command_streaming", lambda *a, **k: ProcessResult(0))
    result = mobi_mod.to_mobi_streaming(
        tmp_path / "a.epub",
        tmp_path / "out" / "a.mobi",
        mobi_mod.MobiOptions(engine="calibre", fix_epub_first=False),
        on_line=_NOOP_LINE,
    )
    assert result.success and result.engine == "calibre"


def test_to_mobi_streaming_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Anulowanie w trakcie → cancelled."""
    monkeypatch.setattr(
        mobi_mod, "_resolve_engine", lambda e: ("calibre", _tool("calibre", "/bin/ec"))
    )
    monkeypatch.setattr(
        mobi_mod, "run_command_streaming", lambda *a, **k: ProcessResult(0, cancelled=True)
    )
    result = mobi_mod.to_mobi_streaming(
        tmp_path / "a.epub",
        tmp_path / "a.mobi",
        mobi_mod.MobiOptions(engine="calibre", fix_epub_first=False),
        on_line=_NOOP_LINE,
    )
    assert result.cancelled


def test_to_mobi_streaming_kindlegen_moves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silnik kindlegen: plik utworzony obok źródła jest przenoszony do celu."""
    src = tmp_path / "a.epub"
    src.write_bytes(b"epub")
    monkeypatch.setattr(
        mobi_mod, "_resolve_engine", lambda e: ("kindlegen", _tool("kindlegen", "/bin/kg"))
    )

    def fake_run(cmd: list[str], on_line: object, *a: object, **k: object) -> ProcessResult:
        # kindlegen tworzy plik obok źródła (nazwa z -o).
        (src.parent / cmd[cmd.index("-o") + 1]).write_bytes(b"mobi")
        return ProcessResult(0)

    monkeypatch.setattr(mobi_mod, "run_command_streaming", fake_run)
    target = tmp_path / "out" / "a.mobi"
    result = mobi_mod.to_mobi_streaming(
        src,
        target,
        mobi_mod.MobiOptions(engine="kindlegen", fix_epub_first=False),
        on_line=_NOOP_LINE,
    )
    assert result.success and target.is_file()


# ── to_kfx_streaming ─────────────────────────────────────────────────────────


def test_to_kfx_streaming_calibre_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silnik calibre: kod 0 → sukces, cel .kfx."""
    monkeypatch.setattr(
        kfx_mod, "_resolve_engine", lambda e: ("calibre", _tool("calibre", "/bin/ec"))
    )
    monkeypatch.setattr(kfx_mod, "run_command_streaming", lambda *a, **k: ProcessResult(0))
    result = kfx_mod.to_kfx_streaming(
        tmp_path / "a.epub",
        tmp_path / "out",
        kfx_mod.KfxOptions(engine="calibre", fix_epub_first=False),
        on_line=_NOOP_LINE,
    )
    assert result.success and result.output_path.name == "a.kfx"


def test_to_kfx_streaming_kp3_moves_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kindle Previewer 3: plik z katalogu tymczasowego jest przenoszony do celu."""
    monkeypatch.setattr(
        kfx_mod, "_resolve_engine", lambda e: ("kindle-previewer", _tool("kp3", "/bin/kp3"))
    )

    def fake_run(cmd: list[str], on_line: object, *a: object, **k: object) -> ProcessResult:
        outdir = Path(cmd[cmd.index("-outdir") + 1])
        (outdir / "a.kfx").write_bytes(b"kfx")
        return ProcessResult(0)

    monkeypatch.setattr(kfx_mod, "run_command_streaming", fake_run)
    result = kfx_mod.to_kfx_streaming(
        tmp_path / "a.epub",
        tmp_path / "out",
        kfx_mod.KfxOptions(engine="kindle-previewer", fix_epub_first=False),
        on_line=_NOOP_LINE,
    )
    assert result.success and result.output_path.is_file()


# ── run_epubcheck (wariant przerywalny) ──────────────────────────────────────


def test_run_epubcheck_cancellable_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should_cancel podany → ścieżka strumieniowa; kod 0 czyta raport JSON."""

    def fake_stream(cmd: list[str], on_line: object, **k: object) -> ProcessResult:
        report = Path(cmd[cmd.index("--json") + 1])
        report.write_text('{"checker":{"checkerVersion":"5.1.0"},"messages":[]}', encoding="utf-8")
        return ProcessResult(0)

    monkeypatch.setattr(ec, "run_subprocess_streaming", fake_stream)
    report = ec.run_epubcheck(
        tmp_path / "a.epub", Path("/bin/java"), Path("/x.jar"), should_cancel=lambda: False
    )
    assert report.valid and report.epubcheck_version == "5.1.0"


def test_run_epubcheck_cancellable_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowanie procesu Javy → ValidationError."""
    monkeypatch.setattr(
        ec, "run_subprocess_streaming", lambda *a, **k: ProcessResult(0, cancelled=True)
    )
    with pytest.raises(ValidationError):
        ec.run_epubcheck(
            tmp_path / "a.epub", Path("/bin/java"), Path("/x.jar"), should_cancel=lambda: True
        )


def test_run_epubcheck_cancellable_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout w wariancie strumieniowym → ValidationError."""
    monkeypatch.setattr(
        ec, "run_subprocess_streaming", lambda *a, **k: ProcessResult(-1, timed_out=True)
    )
    with pytest.raises(ValidationError):
        ec.run_epubcheck(
            tmp_path / "a.epub", Path("/bin/java"), Path("/x.jar"), should_cancel=lambda: False
        )
