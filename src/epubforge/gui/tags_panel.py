"""Panel „Tagi" i dialogi tagowania (propozycje + ustawienia AI) dla zakładki Metadane.

Warstwa GUI nad kaskadą :func:`epubforge.bookmeta.suggest_tags_cascade`. Tagowanie
deterministyczne (mapowanie taksonomii) działa zawsze; AI jest **opt-in** (checkbox)
i uruchamiane w :class:`Worker` (nie blokuje UI). Brak/awaria endpointu AI → czytelny
komunikat, a propozycje z taksonomii i tak się pokazują.

Ustawienia AI świadomie mieszkają w **osobnym modalnym dialogu**, a nie w samej
zakładce: konfiguracja (preset, base_url, model, nazwa zmiennej z kluczem) jest
przekrojowa i wielokrotnego użytku, a zakładka Metadane jest już rozbudowana —
modal grupuje powiązane ustawienia bez zaśmiecania formularza. Klucz API nigdy nie
trafia do pliku konfiguracyjnego — trzymamy tam wyłącznie **nazwę zmiennej środowiskowej**.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from epubforge.bookmeta import (
    PRESETS,
    AIConfig,
    TaggingResult,
    extract_content_sample,
    load_taxonomy,
    suggest_tags_cascade,
)
from epubforge.bookmeta.ai import DEFAULT_PRESET
from epubforge.core import ConfigStore, Epub, EpubError
from epubforge.gui.widgets import Section
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _

# Sygnatura dostawcy kontekstu z zakładki: (tematy, opis, ścieżka EPUB).
ContextProvider = Callable[[], tuple[list[str], str, "Path | None"]]
# Sygnatura odbiornika wybranych tagów (dopisuje je do formularza).
TagsApplier = Callable[[list[str]], None]


def _propose_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    subjects: list[str],
    description: str,
    path_str: str,
    use_ai: bool,
    ai_config: AIConfig,
) -> TaggingResult:
    """Funkcja robocza wątku: uruchamia kaskadę tagowania (bez dotykania GUI)."""
    taxonomy = load_taxonomy()
    content_sample = ""
    if use_ai and not description and path_str:
        try:
            with Epub(Path(path_str)) as epub:
                content_sample = extract_content_sample(epub)
        except (EpubError, OSError, KeyError):
            content_sample = ""
    return suggest_tags_cascade(
        subjects, description, "", taxonomy, ai_config, content_sample=content_sample, use_ai=use_ai
    )


class TagsPanel(QWidget):
    """Sekcja „Tagi": propozycje tagów (taksonomia + opcjonalnie AI) i ustawienia AI."""

    def __init__(
        self,
        *,
        context_provider: ContextProvider,
        tags_applier: TagsApplier,
        config: ConfigStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._context_provider = context_provider
        self._tags_applier = tags_applier
        self._config = config
        self._worker: Worker | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        """Buduje pasek akcji sekcji Tagi."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        section = Section(_("Tagi"))
        outer.addWidget(section)

        row = QHBoxLayout()
        self.propose_button = QPushButton(_("Zaproponuj tagi"))
        self.propose_button.setToolTip(
            _("Proponuje tagi z taksonomii (deskryptory/kategorie), opcjonalnie z AI")
        )
        self.propose_button.clicked.connect(self._propose)
        row.addWidget(self.propose_button)

        self.use_ai_check = QCheckBox(_("Użyj AI (opt-in)"))
        self.use_ai_check.setToolTip(_("Domyślnie lokalna Ollama; ustaw w „Ustawienia AI…"))
        row.addWidget(self.use_ai_check)

        settings_button = QPushButton(_("Ustawienia AI…"))
        settings_button.clicked.connect(self._open_ai_settings)
        row.addWidget(settings_button)
        row.addStretch(1)
        section.content_layout().addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        section.content_layout().addWidget(self.status_label)

    # ── Propozycje ───────────────────────────────────────────────────────────────

    def _propose(self) -> None:
        """Zbiera kontekst z zakładki i uruchamia kaskadę tagowania w wątku."""
        if self._worker is not None:
            return
        subjects, description, path = self._context_provider()
        use_ai = self.use_ai_check.isChecked()
        ai_config = load_ai_config(self._config)
        self.propose_button.setEnabled(False)
        self.status_label.setText(_("Analizuję…"))
        worker = Worker(
            _propose_worker,
            subjects,
            description,
            str(path) if path is not None else "",
            use_ai,
            ai_config,
        )
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_done(self, result: object) -> None:
        """Pokazuje dialog propozycji; komunikuje ewentualny błąd AI."""
        self._worker = None
        self.propose_button.setEnabled(True)
        if not isinstance(result, TaggingResult):
            self.status_label.setText(_("Nie udało się zaproponować tagów"))
            return
        if result.ai_error:
            self.status_label.setText(
                _("AI niedostępne ({error}). Pokazuję tagi z taksonomii.").format(
                    error=result.ai_error
                )
            )
        elif not result.proposals:
            self.status_label.setText(_("Brak propozycji — dodaj opis lub metadane"))
            return
        else:
            self.status_label.setText("")
        if not result.proposals:
            return
        dialog = TagProposalsDialog(result, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selected_tags()
            if selected:
                self._tags_applier(selected)
                self.status_label.setText(
                    _("Dodano {n} tagów — sprawdź i zapisz").format(n=len(selected))
                )

    def _on_failed(self, message: str) -> None:
        """Nieoczekiwana awaria wątku."""
        self._worker = None
        self.propose_button.setEnabled(True)
        self.status_label.setText(_("Błąd tagowania: {error}").format(error=message))

    def _open_ai_settings(self) -> None:
        """Otwiera dialog ustawień AI i zapisuje wynik do konfiguracji."""
        dialog = AISettingsDialog(load_ai_config(self._config), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            save_ai_config(self._config, dialog.result_config())
            self.use_ai_check.setChecked(True)
            self.status_label.setText(_("Zapisano ustawienia AI"))


class TagProposalsDialog(QDialog):
    """Dialog wyboru proponowanych tagów (checkbox per tag + źródło)."""

    def __init__(self, result: TaggingResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checks: list[tuple[QCheckBox, str]] = []
        self.setWindowTitle(_("Proponowane tagi"))
        self.setMinimumWidth(420)
        self._build_layout(result)

    def _build_layout(self, result: TaggingResult) -> None:
        """Buduje listę checkboxów (domyślnie zaznaczone) i przyciski."""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Zaznacz tagi do dopisania (dc:subject):")))
        for proposal in result.proposals:
            checkbox = QCheckBox(f"{proposal.tag}  ·  {proposal.category}  ·  {proposal.source}")
            checkbox.setChecked(True)
            layout.addWidget(checkbox)
            self._checks.append((checkbox, proposal.tag))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_tags(self) -> list[str]:
        """Zwraca zaznaczone tagi (bez duplikatów, w kolejności listy)."""
        result: list[str] = []
        for checkbox, tag in self._checks:
            if checkbox.isChecked() and tag not in result:
                result.append(tag)
        return result


class AISettingsDialog(QDialog):
    """Dialog konfiguracji backendu AI (preset, base_url, model, nazwa zmiennej z kluczem)."""

    def __init__(self, config: AIConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Ustawienia AI"))
        self.setMinimumWidth(460)
        self._build_layout(config)

    def _build_layout(self, config: AIConfig) -> None:
        """Buduje formularz ustawień AI."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        self.preset_combo.setCurrentText(
            config.preset if config.preset in PRESETS else DEFAULT_PRESET
        )
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        form.addRow(_("Preset"), self.preset_combo)

        self.base_url_edit = QLineEdit(config.base_url)
        form.addRow("base_url", self.base_url_edit)
        self.model_edit = QLineEdit(config.model)
        form.addRow(_("Model"), self.model_edit)
        self.api_key_env_edit = QLineEdit(config.api_key_env)
        self.api_key_env_edit.setToolTip(
            _("Nazwa zmiennej środowiskowej z kluczem API (nie sam klucz)")
        )
        form.addRow(_("Zmienna z kluczem"), self.api_key_env_edit)

        note = QLabel(
            _(
                "Klucz API czytany jest wyłącznie ze zmiennej środowiskowej o podanej nazwie. "
                "Domyślnie: lokalna Ollama (bez klucza)."
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_preset_changed(self, name: str) -> None:
        """Wypełnia pola domyślnymi wartościami wybranego presetu (edytowalne dalej)."""
        preset = PRESETS.get(name)
        if preset is None:
            return
        self.base_url_edit.setText(preset.base_url)
        self.model_edit.setText(preset.model)
        self.api_key_env_edit.setText(preset.api_key_env)

    def result_config(self) -> AIConfig:
        """Buduje :class:`AIConfig` z wartości formularza."""
        return AIConfig(
            preset=self.preset_combo.currentText(),
            base_url=self.base_url_edit.text().strip(),
            model=self.model_edit.text().strip(),
            api_key_env=self.api_key_env_edit.text().strip(),
        )


def load_ai_config(config: ConfigStore | None) -> AIConfig:
    """Czyta konfigurację AI z sekcji ``ai`` (domyślny Ollama, gdy brak)."""
    section = config.get("ai") if config is not None else None
    if not isinstance(section, dict):
        return AIConfig()
    base = AIConfig.from_preset(str(section.get("preset", DEFAULT_PRESET)))
    return AIConfig(
        preset=base.preset,
        base_url=str(section.get("base_url", base.base_url)),
        model=str(section.get("model", base.model)),
        api_key_env=str(section.get("api_key_env", base.api_key_env)),
    )


def save_ai_config(config: ConfigStore | None, ai_config: AIConfig) -> None:
    """Zapisuje konfigurację AI do sekcji ``ai`` (bez klucza — tylko nazwa zmiennej)."""
    if config is None:
        return
    config["ai"] = {
        "preset": ai_config.preset,
        "base_url": ai_config.base_url,
        "model": ai_config.model,
        "api_key_env": ai_config.api_key_env,
    }
    config.save_now()
