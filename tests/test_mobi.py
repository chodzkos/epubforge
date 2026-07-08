"""Testy konwersji EPUB do MOBI/AZW3.

Zewnętrzne narzędzia (Calibre, kindlegen) są mockowane — w CI nie uruchamiamy
prawdziwych binariów.
"""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from epubforge.cli.main import main
from epubforge.converters import ConversionResult, MobiOptions, to_mobi
from epubforge.core.detection import Tool
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError

mobi_converter = importlib.import_module("epubforge.converters.to_mobi")

FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"


def _tool(name: str, path: str) -> Tool:
    """Buduje dostępne narzędzie do testów."""
    return Tool(name=name, path=Path(path), version=f"{name} 1.0", available=True)


def _missing(name: str) -> Tool:
    """Buduje niedostępne narzędzie do testów."""
    return Tool(name=name, path=None, version="", available=False)


def _fake_run(
    calls: list[tuple[list[str], dict[str, object]]],
    *,
    stdout: str = "ok",
    stderr: str = "",
    returncode: int = 0,
    create_kindlegen: bool = False,
) -> Callable[..., SimpleNamespace]:
    """Zwraca mock subprocess.run zapisujący wywołania."""

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        if create_kindlegen:
            source = Path(command[1])
            out_name = command[-1]
            (source.parent / out_name).write_bytes(b"mobi")
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return run


def test_calibre_builds_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silnik Calibre buduje ebook-convert source target."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(mobi_converter.subprocess, "run", _fake_run(calls, stdout="calibre log"))

    source = tmp_path / "book.epub"
    target = tmp_path / "out" / "book.mobi"
    result = to_mobi(source, target, MobiOptions(engine="calibre", fix_epub_first=False))

    assert result == ConversionResult(True, target, "calibre log", "calibre")
    command, _kwargs = calls[0]
    assert command == [str(Path("/bin/ebook-convert")), str(source), str(target)]


def test_auto_prefers_calibre(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto wybiera Calibre, gdy jest dostępny."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(mobi_converter.subprocess, "run", _fake_run(calls))

    result = to_mobi(
        tmp_path / "b.epub", tmp_path / "b.mobi", MobiOptions(engine="auto", fix_epub_first=False)
    )
    assert result.engine == "calibre"


def test_auto_falls_back_to_kindlegen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto przechodzi na kindlegen, gdy Calibre niedostępny."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools, "calibre_ebook_convert", staticmethod(lambda: _missing("calibre"))
    )
    monkeypatch.setattr(
        mobi_converter.Tools,
        "kindlegen",
        staticmethod(lambda: _tool("kindlegen", "/bin/kindlegen")),
    )
    monkeypatch.setattr(mobi_converter.subprocess, "run", _fake_run(calls, create_kindlegen=True))

    source = tmp_path / "book.epub"
    target = tmp_path / "out" / "book.mobi"
    result = to_mobi(source, target, MobiOptions(engine="auto", fix_epub_first=False))

    assert result.engine == "kindlegen"
    assert target.read_bytes() == b"mobi"


def test_kindlegen_moves_output_and_notes_deprecation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """kindlegen tworzy plik obok źródła, a wynik jest przenoszony do celu."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "kindlegen",
        staticmethod(lambda: _tool("kindlegen", "/bin/kindlegen")),
    )
    monkeypatch.setattr(
        mobi_converter.subprocess,
        "run",
        _fake_run(calls, stdout="Info: build OK", returncode=1, create_kindlegen=True),
    )

    source = tmp_path / "book.epub"
    target = tmp_path / "out" / "book.mobi"
    result = to_mobi(source, target, MobiOptions(engine="kindlegen", fix_epub_first=False))

    # Mimo kodu 1 (ostrzeżenia) sukces, bo plik powstał.
    assert result.engine == "kindlegen"
    assert target.read_bytes() == b"mobi"
    assert not (source.parent / "book.mobi").exists()
    assert "discontinued" in result.log
    command = calls[0][0]
    assert command == [str(Path("/bin/kindlegen")), str(source), "-o", "book.mobi"]


def test_kindlegen_missing_output_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak pliku wynikowego kindlegen → ConversionError."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "kindlegen",
        staticmethod(lambda: _tool("kindlegen", "/bin/kindlegen")),
    )
    monkeypatch.setattr(
        mobi_converter.subprocess, "run", _fake_run(calls, stderr="error", returncode=2)
    )

    with pytest.raises(ConversionError, match="nie utworzył"):
        to_mobi(
            tmp_path / "book.epub",
            tmp_path / "book.mobi",
            MobiOptions(engine="kindlegen", fix_epub_first=False),
        )


def test_calibre_nonzero_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Niezerowy kod Calibre → ConversionError z fragmentem logu."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(
        mobi_converter.subprocess, "run", _fake_run(calls, stderr="boom", returncode=1)
    )

    with pytest.raises(ConversionError, match="boom"):
        to_mobi(
            tmp_path / "book.epub",
            tmp_path / "book.azw3",
            MobiOptions(fmt="azw3", engine="calibre", fix_epub_first=False),
        )


def test_calibre_required_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wymuszony Calibre, gdy niedostępny → ConverterNotFoundError."""
    monkeypatch.setattr(
        mobi_converter.Tools, "calibre_ebook_convert", staticmethod(lambda: _missing("calibre"))
    )
    with pytest.raises(ConverterNotFoundError, match="Calibre"):
        to_mobi(
            tmp_path / "b.epub",
            tmp_path / "b.mobi",
            MobiOptions(engine="calibre", fix_epub_first=False),
        )


def test_kindlegen_required_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wymuszony kindlegen, gdy niedostępny → ConverterNotFoundError."""
    monkeypatch.setattr(
        mobi_converter.Tools, "kindlegen", staticmethod(lambda: _missing("kindlegen"))
    )
    with pytest.raises(ConverterNotFoundError, match="kindlegen"):
        to_mobi(
            tmp_path / "b.epub",
            tmp_path / "b.mobi",
            MobiOptions(engine="kindlegen", fix_epub_first=False),
        )


def test_fix_epub_first_does_not_mutate_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fix_epub_first pracuje na kopii — źródło nietknięte i bez ``.bak`` obok."""
    source = tmp_path / "book.epub"
    shutil.copy2(FIXTURE, source)
    original = source.read_bytes()

    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        mobi_converter.Tools,
        "calibre_ebook_convert",
        staticmethod(lambda: _tool("calibre_ebook_convert", "/bin/ebook-convert")),
    )
    monkeypatch.setattr(mobi_converter.subprocess, "run", _fake_run(calls))

    target = tmp_path / "out" / "book.mobi"
    to_mobi(source, target, MobiOptions(engine="calibre", fix_epub_first=True))

    # Wejściowy plik użytkownika nietknięty i bez backupu obok niego.
    assert source.read_bytes() == original
    assert not (tmp_path / "book.epub.bak").exists()
    # Konwersja dostała ścieżkę kopii (w katalogu tymczasowym), nie oryginału.
    convert_source = Path(calls[0][0][1])
    assert convert_source != source
    assert convert_source.name == "book.epub"


def test_cli_mobi_invokes_converter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI ``mobi`` buduje opcje z argumentów i woła to_mobi z poprawnym celem."""
    captured: dict[str, object] = {}

    def fake_to_mobi(source: Path, target: Path, options: MobiOptions) -> ConversionResult:
        captured["source"] = source
        captured["target"] = target
        captured["options"] = options
        return ConversionResult(True, target, "ok", "calibre")

    from epubforge.cli import mobi as cli_mobi

    monkeypatch.setattr(cli_mobi, "to_mobi", fake_to_mobi)

    book = tmp_path / "book.epub"
    code = main(["mobi", str(book), "--format", "azw3", "--engine", "kindlegen"])

    assert code == 0
    assert captured["target"] == book.with_suffix(".azw3")
    options = captured["options"]
    assert isinstance(options, MobiOptions)
    assert options.fmt == "azw3"
    assert options.engine == "kindlegen"
