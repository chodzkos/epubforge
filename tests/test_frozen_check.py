"""Testy samokontroli zasobów zamrożonego artefaktu (``epubforge._frozen_check``).

Logika jest czysto-core (bez Qt), więc biegnie też w torze base-cli. Sprawdzamy,
że wszystkie zasoby ładują się w drzewie źródeł oraz że brak zasobu daje kod 1
i wpis ``FAIL`` w logu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge import _frozen_check


def test_check_bundled_resources_passes() -> None:
    """Wszystkie pięć zasobów ładuje się i zwraca opis."""
    details = _frozen_check.check_bundled_resources()
    assert len(details) == len(_frozen_check.CHECKS)
    joined = " ".join(details)
    assert "taksonomia" in joined
    assert "receptury" in joined


def test_run_self_check_ok_writes_log(tmp_path: Path) -> None:
    """``run_self_check`` zwraca 0 i zapisuje log z samymi OK."""
    log = tmp_path / "selfcheck.log"
    assert _frozen_check.run_self_check([str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert "FAIL" not in text
    assert "wszystkie zasoby wczytane z bundla" in text


def test_run_self_check_detects_missing_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brak wbudowanej receptury → kod 1 i wpis FAIL w logu."""
    monkeypatch.setattr("epubforge.recipes.discover_recipes", lambda **_kwargs: [])
    log = tmp_path / "selfcheck.log"
    assert _frozen_check.run_self_check([str(log)]) == 1
    text = log.read_text(encoding="utf-8")
    assert "FAIL" in text
    assert "receptur" in text


def test_run_self_check_default_log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bez argumentu log trafia do domyślnego pliku w bieżącym katalogu."""
    monkeypatch.chdir(tmp_path)
    assert _frozen_check.run_self_check([]) == 0
    assert (tmp_path / _frozen_check._DEFAULT_LOG).is_file()
