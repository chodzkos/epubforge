"""Testy panelu Tagów i dialogów tagowania (:mod:`epubforge.gui.tags_panel`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.bookmeta import AIConfig, TaggingResult, TagProposal
from epubforge.gui.tags_panel import (
    AISettingsDialog,
    TagProposalsDialog,
    TagsPanel,
    load_ai_config,
    save_ai_config,
)

pytestmark = pytest.mark.gui


class _FakeConfig(dict):
    """Atrapa ConfigStore: dict + save_now (rejestruje zapis)."""

    saved: bool = False

    def save_now(self) -> None:
        self.saved = True


# ── Dialog propozycji ─────────────────────────────────────────────────────────────


def _result() -> TaggingResult:
    return TaggingResult(
        proposals=[
            TagProposal("science fiction", "gatunek", "AI"),
            TagProposal("kosmos", "miejsce", "AI"),
            TagProposal("komiks", "gatunek", "taksonomia"),
        ]
    )


def test_proposals_dialog_default_checked(qtbot: QtBot) -> None:
    """Wszystkie propozycje są domyślnie zaznaczone."""
    dialog = TagProposalsDialog(_result())
    qtbot.addWidget(dialog)
    assert dialog.selected_tags() == ["science fiction", "kosmos", "komiks"]


def test_proposals_dialog_deselect(qtbot: QtBot) -> None:
    """Odznaczenie wyklucza tag z wyniku."""
    dialog = TagProposalsDialog(_result())
    qtbot.addWidget(dialog)
    dialog._checks[1][0].setChecked(False)  # odznacz "kosmos"
    assert dialog.selected_tags() == ["science fiction", "komiks"]


# ── Dialog ustawień AI ────────────────────────────────────────────────────────────


def test_ai_settings_preset_change_fills_fields(qtbot: QtBot) -> None:
    """Zmiana presetu wypełnia base_url/model/nazwę zmiennej domyślnymi wartościami."""
    dialog = AISettingsDialog(AIConfig())
    qtbot.addWidget(dialog)
    dialog.preset_combo.setCurrentText("openai")
    assert dialog.base_url_edit.text() == "https://api.openai.com/v1"
    assert dialog.api_key_env_edit.text() == "OPENAI_API_KEY"
    config = dialog.result_config()
    assert config.preset == "openai"
    assert config.model == "gpt-4o-mini"


# ── Trwałość konfiguracji ─────────────────────────────────────────────────────────


def test_ai_config_roundtrip() -> None:
    """save_ai_config zapisuje sekcję ai (bez klucza), load_ai_config ją odczytuje."""
    config = _FakeConfig()
    save_ai_config(
        config,
        AIConfig(
            preset="deepseek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
        ),
    )
    assert config.saved
    assert "api_key" not in config["ai"]  # nigdy sam klucz
    loaded = load_ai_config(config)
    assert loaded.preset == "deepseek"
    assert loaded.model == "deepseek-chat"
    assert loaded.api_key_env == "DEEPSEEK_API_KEY"


def test_load_ai_config_defaults_when_empty() -> None:
    """Brak sekcji ai → domyślny Ollama."""
    assert load_ai_config(None).preset == "ollama"
    assert load_ai_config(_FakeConfig()).preset == "ollama"


# ── Panel: przepływ propozycji ────────────────────────────────────────────────────


def test_panel_applies_selected_tags(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """_on_done pokazuje dialog, a zaznaczone tagi trafiają do applier."""
    applied: list[str] = []
    panel = TagsPanel(
        context_provider=lambda: (["Powieść"], "opis", None),
        tags_applier=applied.extend,
    )
    qtbot.addWidget(panel)

    # Podmień exec dialogu na natychmiastową akceptację (bez modala).
    monkeypatch.setattr(
        TagProposalsDialog, "exec", lambda self: int(TagProposalsDialog.DialogCode.Accepted)
    )
    panel._on_done(_result())
    assert applied == ["science fiction", "kosmos", "komiks"]


def test_panel_context_provider_wired(qtbot: QtBot) -> None:
    """Panel korzysta z dostawcy kontekstu z zakładki."""
    ctx: tuple[list[str], str, Path | None] = (["Fantasy"], "opis", None)
    panel = TagsPanel(context_provider=lambda: ctx, tags_applier=lambda _t: None)
    qtbot.addWidget(panel)
    assert panel._context_provider() == ctx


def test_panel_reports_ai_error(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd AI w wyniku → komunikat w statusie, propozycje deterministyczne pokazane."""
    monkeypatch.setattr(
        TagProposalsDialog, "exec", lambda self: int(TagProposalsDialog.DialogCode.Rejected)
    )
    panel = TagsPanel(context_provider=lambda: ([], "", None), tags_applier=lambda _t: None)
    qtbot.addWidget(panel)
    result = TaggingResult(
        proposals=[TagProposal("komiks", "gatunek", "taksonomia")], ai_error="brak Ollamy"
    )
    panel._on_done(result)
    assert "AI niedostępne" in panel.status_label.text()
