"""Testy GUI zakładki walidacji (ValidatorTab) — bez prawdziwej Javy."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.core import ConfigStore, Tool
from epubforge.gui.tabs import validator as validator_module
from epubforge.gui.tabs.validator import ValidatorTab
from epubforge.validators import (
    AceMessage,
    AceReport,
    Severity,
    ValidationMessage,
    ValidationReport,
)

pytestmark = pytest.mark.gui


def _ready_tools() -> dict[str, Tool]:
    return {
        "java": Tool("java", Path("/usr/bin/java"), "17", True),
        "epubcheck": Tool("epubcheck", Path("/opt/epubcheck.jar"), "5.1.0", True),
    }


def _ace_tools() -> dict[str, Tool]:
    return {"ace": Tool("ace", Path("/usr/bin/ace"), "1.3.2", True)}


def _report() -> ValidationReport:
    return ValidationReport(
        Path("book.epub"),
        valid=False,
        epubcheck_version="5.1.0",
        messages=[
            ValidationMessage(Severity.ERROR, "RSC-005", "boom", "OEBPS/ch1.xhtml", 10, 5),
            ValidationMessage(Severity.WARNING, "OPF-003", "warn", None, None, None),
            ValidationMessage(Severity.INFO, "ACC-001", "hint", None, None, None),
        ],
    )


def _ace_report() -> AceReport:
    return AceReport(
        Path("book.epub"),
        accessible=False,
        ace_version="1.3.2",
        messages=[
            AceMessage(Severity.ERROR, "image-alt", "brak alt", "EPUB/ch1.xhtml"),
            AceMessage(Severity.WARNING, "epub-type", "rola ARIA", "EPUB/ch2.xhtml"),
        ],
    )


class _FakeMainWindow:
    """Atrapa głównego okna rejestrująca wywołania open_in_editor."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str | None, int | None]] = []

    def open_in_editor(
        self, epub_path: Path, internal_path: str | None = None, line: int | None = None
    ) -> None:
        self.calls.append((epub_path, internal_path, line))


def test_tree_fills_from_report(qtbot: QtBot) -> None:
    """Po otrzymaniu raportu drzewo ma wiersz na każdy komunikat."""
    tab = ValidatorTab(tools=_ready_tools())
    qtbot.addWidget(tab)
    tab._on_done(_report())
    assert tab.tree.topLevelItemCount() == 3
    assert "✗" in tab.summary_label.text()


def test_filter_hides_info(qtbot: QtBot) -> None:
    """Odznaczenie filtra „Informacje" usuwa wiersze info z drzewa."""
    tab = ValidatorTab(tools=_ready_tools())
    qtbot.addWidget(tab)
    tab._on_done(_report())
    tab.show_info.setChecked(False)
    assert tab.tree.topLevelItemCount() == 2


def test_double_click_calls_open_in_editor(qtbot: QtBot) -> None:
    """Dwuklik wiersza z lokalizacją woła open_in_editor z plikiem i linią."""
    main_window = _FakeMainWindow()
    tab = ValidatorTab(tools=_ready_tools(), main_window=main_window)  # type: ignore[arg-type]
    qtbot.addWidget(tab)
    tab._on_done(_report())
    item = tab.tree.topLevelItem(0)
    tab._on_item_double_clicked(item, 0)
    assert main_window.calls == [(Path("book.epub"), "OEBPS/ch1.xhtml", 10)]


def test_double_click_without_location_does_nothing(qtbot: QtBot) -> None:
    """Dwuklik wiersza bez lokalizacji (warning) nie woła open_in_editor."""
    main_window = _FakeMainWindow()
    tab = ValidatorTab(tools=_ready_tools(), main_window=main_window)  # type: ignore[arg-type]
    qtbot.addWidget(tab)
    tab._on_done(_report())
    tab._on_item_double_clicked(tab.tree.topLevelItem(1), 0)  # warning bez locations
    assert main_window.calls == []


def test_ace_button_disabled_without_ace(qtbot: QtBot) -> None:
    """Bez wykrytego Ace przycisk audytu jest wyszarzony z tooltipem instalacyjnym."""
    tab = ValidatorTab(tools=_ready_tools())
    qtbot.addWidget(tab)
    assert tab.ace_button.isEnabled() is False
    assert "@daisy/ace" in tab.ace_button.toolTip()


def test_ace_results_fill_same_tree(qtbot: QtBot) -> None:
    """Raport Ace wypełnia to samo drzewo wyników co EpubCheck."""
    tab = ValidatorTab(tools=_ace_tools())
    qtbot.addWidget(tab)
    assert tab.stack.currentIndex() == 0  # panel wyników, bo Ace dostępny
    tab._on_ace_done(_ace_report())
    assert tab.tree.topLevelItemCount() == 2
    assert "⚠" in tab.summary_label.text()


def test_ace_double_click_jumps_to_editor(qtbot: QtBot) -> None:
    """Dwuklik wiersza Ace z lokalizacją woła open_in_editor (line=None)."""
    main_window = _FakeMainWindow()
    tab = ValidatorTab(tools=_ace_tools(), main_window=main_window)  # type: ignore[arg-type]
    qtbot.addWidget(tab)
    tab._on_ace_done(_ace_report())
    tab._on_item_double_clicked(tab.tree.topLevelItem(0), 0)
    assert main_window.calls == [(Path("book.epub"), "EPUB/ch1.xhtml", None)]


def test_ace_accessible_verdict(qtbot: QtBot) -> None:
    """Raport dostępny pokazuje werdykt DOSTĘPNY na pasku statusu."""
    tab = ValidatorTab(tools=_ace_tools())
    qtbot.addWidget(tab)
    tab._on_ace_done(AceReport(Path("book.epub"), accessible=True, ace_version="1.3.2"))
    assert "DOSTĘPNY" in tab.status_label.text()
    assert tab.tree.topLevelItemCount() == 0


def test_ace_export_json_and_html(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eksport aktywnego raportu Ace zapisuje JSON i HTML z naruszeniami."""
    tab = ValidatorTab(tools=_ace_tools())
    qtbot.addWidget(tab)
    tab._on_ace_done(_ace_report())

    out_json = tmp_path / "ace.json"
    monkeypatch.setattr(validator_module, "save_file", lambda *a, **k: str(out_json))
    tab._export_report()
    assert "image-alt" in out_json.read_text(encoding="utf-8")

    out_html = tmp_path / "ace.html"
    monkeypatch.setattr(validator_module, "save_file", lambda *a, **k: str(out_html))
    tab._export_report()
    assert "DAISY Ace" in out_html.read_text(encoding="utf-8")


def test_run_ace_check_starts_worker(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """„Sprawdź dostępność (Ace)" startuje workera z plikiem i ścieżką ace."""
    monkeypatch.setattr(validator_module, "Worker", fake_worker)
    tab = ValidatorTab(tools=_ace_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    book.write_text("x")
    tab.file_list.add_files([book])
    tab.file_list.select_first()
    tab._run_ace_check()

    fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert fn is validator_module._run_ace_worker
    assert args == (book, Path("/usr/bin/ace"))


def test_run_ace_worker_calls_run_ace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Funkcja robocza deleguje do run_ace i zwraca raport."""
    report = _ace_report()
    monkeypatch.setattr(validator_module, "run_ace", lambda *a, **k: report)
    result = validator_module._run_ace_worker(
        lambda text, level: None,
        lambda cur, total: None,
        lambda: False,
        tmp_path / "b.epub",
        Path("ace"),
    )
    assert result is report


def test_help_panel_when_tools_missing(qtbot: QtBot) -> None:
    """Bez Javy/epubchecka pokazuje się panel pomocy, nie wyniki."""
    tab = ValidatorTab(tools={"java": Tool("java", None, "", False)})
    qtbot.addWidget(tab)
    assert tab.stack.currentIndex() == 1  # _PAGE_HELP
    assert "Temurin" in tab.help_label.text()
    assert tab.pick_java_button.text().startswith("Wskaż java")


def test_pick_java_sets_override_and_redetects(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """„Wskaż java.exe…" zapisuje override do config['tools']['java_path'] i re-detekuje."""
    config = ConfigStore("epubforge", path=tmp_path / "config.json")
    tab = ValidatorTab(tools={"java": Tool("java", None, "", False)}, config=config)
    qtbot.addWidget(tab)
    java = tmp_path / "java.exe"
    java.write_text("x")

    monkeypatch.setattr(validator_module, "open_file", lambda *a, **k: str(java))
    monkeypatch.setattr(validator_module, "detect_with_cache", lambda *a, **k: _ready_tools())
    tab._pick_java()

    assert config["tools"]["java_path"] == str(java)
    assert tab.stack.currentIndex() == 0  # wyniki — narzędzia gotowe po re-detekcji
