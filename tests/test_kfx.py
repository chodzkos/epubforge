"""Testy konwersji EPUB do KFX.

Zewnętrzne narzędzia są mockowane: nie uruchamiamy Calibre ani Kindle Previewer
w CI.
"""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from epubforge.cli import kfx as cli_kfx
from epubforge.cli.main import main
from epubforge.converters import ConversionResult, KfxOptions, to_kfx
from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.core.process import ProcessResult

kfx_converter = importlib.import_module("epubforge.converters.to_kfx")

FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"


def _tool(name: str, path: str) -> Tool:
    """Buduje dostępne narzędzie do testów."""
    return Tool(name=name, path=Path(path), version=f"{name} 1.0", available=True)


def _missing_tool(name: str) -> Tool:
    """Buduje niedostępne narzędzie do testów."""
    return Tool(name=name, path=None, version="", available=False)


def _path_arg(path: str) -> str:
    """Zwraca ścieżkę tak, jak trafi do argumentów subprocess na danej platformie."""
    return str(Path(path))


def _fake_run(
    calls: list[tuple[list[str], dict[str, object]]],
    *,
    stdout: str = "ok",
    stderr: str = "",
    returncode: int = 0,
    create_kfx: bool = False,
) -> Callable[..., ProcessResult]:
    """Zwraca mock run_process zapisujący wywołania."""

    def run(command: list[str], **kwargs: object) -> ProcessResult:
        calls.append((command, kwargs))
        if create_kfx:
            outdir = Path(command[-1])
            nested = outdir / "output"
            nested.mkdir(parents=True)
            (nested / "book.kfx").write_bytes(b"kfx")
        output = "\n".join(p for p in (stdout, stderr) if p)
        return ProcessResult(returncode=returncode, output=output)

    return run


def test_auto_uses_calibre_when_kfx_plugin_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto wybiera Calibre, jeśli wtyczka KFX Output jest wykryta."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: True))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(kfx_converter, "run_process", _fake_run(calls, stdout="calibre log"))

    source = tmp_path / "book.epub"
    result = to_kfx(source, tmp_path / "out", KfxOptions(engine="auto", fix_epub_first=False))

    target = tmp_path / "out" / "book.kfx"
    assert result == ConversionResult(True, target, "calibre log", "calibre")
    command, _kwargs = calls[0]
    assert command == [_path_arg("/bin/ebook-convert"), str(source), str(target)]


def test_auto_falls_back_to_kindle_previewer_without_calibre_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto przechodzi na KP3, gdy wtyczka Calibre KFX Output nie jest wykryta."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: False))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "kindle_previewer",
        staticmethod(lambda: _tool("kindle_previewer", "/opt/kp3/Kindle Previewer 3")),
    )
    monkeypatch.setattr(
        kfx_converter,
        "run_process",
        _fake_run(calls, stdout="kp3 log", create_kfx=True),
    )

    source = tmp_path / "book.epub"
    result = to_kfx(source, tmp_path / "out", KfxOptions(engine="auto", fix_epub_first=False))

    target = tmp_path / "out" / "book.kfx"
    assert result.engine == "kindle-previewer"
    assert result.output_path == target
    assert target.read_bytes() == b"kfx"
    assert "EXPERIMENTAL" in result.log
    assert "kp3 log" in result.log
    command = calls[0][0]
    assert command[:3] == [_path_arg("/opt/kp3/Kindle Previewer 3"), "-convert", str(source)]
    assert command[3] == "-outdir"
    assert Path(command[4]).name.startswith("epubforge-kp3-")


def test_explicit_kindle_previewer_adds_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wymuszony KP3 też dodaje ostrzeżenie do logu."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        kfx_converter.Tools,
        "kindle_previewer",
        staticmethod(lambda: _tool("kindle_previewer", "/kp3")),
    )
    monkeypatch.setattr(
        kfx_converter,
        "run_process",
        _fake_run(calls, stdout="", stderr="converted", create_kfx=True),
    )

    result = to_kfx(
        tmp_path / "book.epub",
        tmp_path,
        KfxOptions(engine="kindle-previewer", fix_epub_first=False),
    )

    assert result.engine == "kindle-previewer"
    assert "EXPERIMENTAL" in result.log
    assert "converted" in result.log


def test_requested_calibre_requires_kfx_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calibre bez KFX Output daje czytelny ConverterNotFoundError."""
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: False))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/ebook-convert")),
    )

    with pytest.raises(ConverterNotFoundError, match="KFX Output"):
        to_kfx(tmp_path / "book.epub", tmp_path, KfxOptions(engine="calibre", fix_epub_first=False))


def test_nonzero_subprocess_raises_conversion_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Błąd procesu jest propagowany jako ConversionError z fragmentem logu."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: True))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/ebook-convert")),
    )
    monkeypatch.setattr(
        kfx_converter,
        "run_process",
        _fake_run(calls, stdout="stdout", stderr="boom", returncode=2),
    )

    with pytest.raises(ConversionError, match="boom"):
        to_kfx(tmp_path / "book.epub", tmp_path, KfxOptions(engine="calibre", fix_epub_first=False))


def test_kindle_previewer_requires_kfx_output_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KP3 musi utworzyć plik .kfx w katalogu tymczasowym."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        kfx_converter.Tools,
        "kindle_previewer",
        staticmethod(lambda: _tool("kindle_previewer", "/kp3")),
    )
    monkeypatch.setattr(kfx_converter, "run_process", _fake_run(calls, stdout="no output"))

    with pytest.raises(ConversionError, match="nie utworzył"):
        to_kfx(
            tmp_path / "book.epub",
            tmp_path,
            KfxOptions(engine="kindle-previewer", fix_epub_first=False),
        )


def test_fix_epub_first_runs_before_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fix_epub_first uruchamia CSS fixer przed subprocess konwersji."""
    events: list[str] = []

    class FakeEpub:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> FakeEpub:
            events.append("open")
            return self

        def __exit__(self, *args: object) -> None:
            events.append("close")

        def save(self) -> None:
            events.append("save")

    def fake_fix_css(epub: FakeEpub, options: object) -> None:
        events.append(f"fix:{epub.path.name}:{type(options).__name__}")

    def fake_run(command: list[str], **kwargs: object) -> ProcessResult:
        events.append("convert")
        return ProcessResult(returncode=0, output="ok")

    monkeypatch.setattr(kfx_converter, "Epub", FakeEpub)
    monkeypatch.setattr(kfx_converter, "fix_css", fake_fix_css)
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: True))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/ebook-convert")),
    )
    monkeypatch.setattr(kfx_converter, "run_process", fake_run)

    # _fix_epub kopiuje źródło do katalogu tymczasowego (praca na kopii), więc
    # plik musi istnieć; FakeEpub i tak nie czyta jego zawartości.
    source = tmp_path / "book.epub"
    source.write_bytes(b"epub")
    to_kfx(source, tmp_path, KfxOptions(engine="calibre", fix_epub_first=True))

    # Kopia zachowuje nazwę pliku, więc kolejność zdarzeń pozostaje ta sama.
    assert events == ["open", "fix:book.epub:CssFixOptions", "save", "close", "convert"]


def test_fix_epub_first_does_not_mutate_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fix_epub_first pracuje na kopii — źródło nietknięte i bez ``.bak`` obok."""
    source = tmp_path / "book.epub"
    shutil.copy2(FIXTURE, source)
    original = source.read_bytes()

    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(kfx_converter.Tools, "calibre_kfx_plugin", staticmethod(lambda: True))
    monkeypatch.setattr(
        kfx_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(kfx_converter, "run_process", _fake_run(calls))

    to_kfx(source, tmp_path / "out", KfxOptions(engine="calibre", fix_epub_first=True))

    # Wejściowy plik użytkownika nietknięty i bez backupu obok niego.
    assert source.read_bytes() == original
    assert not (tmp_path / "book.epub.bak").exists()
    # Konwersja dostała ścieżkę kopii (w katalogu tymczasowym), nie oryginału.
    convert_source = Path(calls[0][0][1])
    assert convert_source != source
    assert convert_source.name == "book.epub"


def test_cli_kfx_subcommand(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI przekazuje FILE, engine i --no-fix do warstwy konwersji."""
    seen: dict[str, object] = {}

    def fake_to_kfx(source: Path, target_dir: Path, options: KfxOptions) -> ConversionResult:
        seen.update({"source": source, "target_dir": target_dir, "options": options})
        return ConversionResult(True, target_dir / "book.kfx", "cli log", "calibre")

    monkeypatch.setattr(cli_kfx, "to_kfx", fake_to_kfx)
    source = tmp_path / "book.epub"

    exit_code = main(["kfx", str(source), "--engine", "calibre", "--no-fix"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["source"] == source
    assert seen["target_dir"] == tmp_path
    assert seen["options"] == KfxOptions(engine="calibre", fix_epub_first=False)
    assert "cli log" in captured.out
    assert f"Utworzono KFX: {tmp_path / 'book.kfx'}" in captured.out
