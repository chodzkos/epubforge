"""Audyt dostępności EPUB przez DAISY Ace (``ace --outdir … book.epub``).

Moduł jest czysty (bez Qt): uruchamia Ace w subprocessie, parsuje raport JSON
(``report.json`` w katalogu wyjściowym) i zwraca :class:`AceReport`. Sam wynik
„EPUB jest niedostępny" NIE jest błędem (wraca jako ``accessible=False``);
:class:`ValidationError` rezerwujemy na sytuacje techniczne: brak/zepsuty JSON,
timeout, brak narzędzia.

Parser jest **defensywny** — format raportu Ace (osie ``assertions`` /
``earl:result``) bywa modyfikowany między wersjami, więc każde pole czytamy przez
``.get``. Raport Ace ma strukturę zagnieżdżoną (EARL): zewnętrzna lista
``assertions`` to dokumenty treści (każdy z ``earl:testSubject.url``), a wewnątrz
druga lista ``assertions`` z pojedynczymi naruszeniami (``earl:test`` +
``earl:result``). Poziom istotności Ace (``critical``/``serious``/``moderate``/
``minor``) mapujemy na istniejące :class:`Severity`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epubforge.core.exceptions import ValidationError
from epubforge.core.streaming import CancelCheck, run_subprocess_streaming
from epubforge.i18n import _
from epubforge.validators.epubcheck import Severity

# Flaga ukrywająca okno konsoli na Windows (pułapka #7).
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DEFAULT_TIMEOUT = 600  # sekundy — Ace bywa wolniejszy niż EpubCheck

# Mapowanie poziomów wpływu Ace na nasze poziomy istotności.
_ACE_IMPACT_MAP = {
    "critical": Severity.ERROR,
    "serious": Severity.ERROR,
    "moderate": Severity.WARNING,
    "minor": Severity.INFO,
}


@dataclass(frozen=True)
class AceMessage:
    """Pojedyncze naruszenie dostępności z raportu Ace."""

    severity: Severity
    rule: str
    message: str
    internal_path: str | None = None


@dataclass(frozen=True)
class AceReport:
    """Wynik audytu dostępności jednego pliku EPUB."""

    epub_path: Path
    accessible: bool
    ace_version: str
    messages: list[AceMessage] = field(default_factory=list)
    duration_s: float = 0.0

    def counts(self) -> dict[Severity, int]:
        """Zlicza naruszenia per poziom istotności."""
        counter: Counter[Severity] = Counter(msg.severity for msg in self.messages)
        return {severity: counter.get(severity, 0) for severity in Severity}


def _severity_from_impact(raw: object) -> Severity:
    """Mapuje ``earl:impact`` Ace na :class:`Severity` (fallback: info)."""
    key = str(raw).strip().lower() if raw is not None else ""
    return _ACE_IMPACT_MAP.get(key, Severity.INFO)


def _normalize_path(raw: object) -> str | None:
    """Sprowadza ``url`` podmiotu testowego do ścieżki wewnątrz EPUB-a (lub ``None``)."""
    if not isinstance(raw, str) or not raw:
        return None
    normalized = raw.replace("\\", "/").lstrip("/")
    # Ace potrafi podać "." jako url całej publikacji — to nie jest ścieżka pliku.
    if normalized in {"", "."}:
        return None
    return normalized or None


def _subject_url(subject: object) -> str | None:
    """Wyciąga znormalizowaną ścieżkę z ``earl:testSubject`` (defensywnie)."""
    if not isinstance(subject, dict):
        return None
    return _normalize_path(subject.get("url"))


def _dict(value: object) -> dict[str, Any]:
    """Zwraca ``value`` jako słownik albo pusty słownik."""
    return value if isinstance(value, dict) else {}


def _leaf_message(assertion: dict[str, Any], subject_path: str | None) -> AceMessage | None:
    """Buduje :class:`AceMessage` z pojedynczego naruszenia (``earl:test`` + ``earl:result``)."""
    test = _dict(assertion.get("earl:test"))
    result = _dict(assertion.get("earl:result"))
    # Wynik "pass" nie jest naruszeniem — pomijamy (interesują nas tylko problemy).
    outcome = str(result.get("earl:outcome", "")).strip().lower()
    if outcome in {"pass", "passed", "inapplicable"}:
        return None
    rule = str(test.get("dct:title", "") or "")
    message = str(result.get("dct:description", "") or test.get("dct:description", "") or "")
    # Lokalizacja pojedynczego wyniku (jeśli jest) ma pierwszeństwo przed podmiotem.
    location = _normalize_path(result.get("location")) or subject_path
    return AceMessage(
        severity=_severity_from_impact(test.get("earl:impact")),
        rule=rule,
        message=message,
        internal_path=location,
    )


def _walk_assertions(raw: object, subject_path: str | None) -> Iterator[AceMessage]:
    """Rekurencyjnie przechodzi drzewo ``assertions`` i zwraca naruszenia.

    Zewnętrzne wpisy to dokumenty treści (z ``earl:testSubject.url``), a ich
    zagnieżdżona lista ``assertions`` — pojedyncze naruszenia. Obsługujemy oba
    warianty (płaski i zagnieżdżony), bo format bywa zmienny między wersjami Ace.
    """
    if not isinstance(raw, list):
        return
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        entry_subject = _subject_url(entry.get("earl:testSubject")) or subject_path
        if "earl:test" in entry:
            message = _leaf_message(entry, entry_subject)
            if message is not None:
                yield message
        nested = entry.get("assertions")
        if isinstance(nested, list):
            yield from _walk_assertions(nested, entry_subject)


def _report_version(data: dict[str, Any]) -> str:
    """Odczytuje wersję Ace z raportu (kilka wariantów pól, fallback: puste)."""
    for key in ("dct:hasVersion", "ace-version", "aceVersion"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _is_accessible(data: dict[str, Any], messages: list[AceMessage]) -> bool:
    """Ustala, czy EPUB jest dostępny: z ``earl:result`` lub braku błędów krytycznych."""
    outcome = str(_dict(data.get("earl:result")).get("earl:outcome", "")).strip().lower()
    if outcome in {"pass", "passed"}:
        return True
    if outcome in {"fail", "failed"}:
        return False
    return not any(msg.severity is Severity.ERROR for msg in messages)


def parse_ace_report(data: dict[str, Any], epub_path: Path) -> AceReport:
    """Parsuje słownik JSON raportu Ace do :class:`AceReport` (defensywnie)."""
    root_subject = _subject_url(data.get("earl:testSubject"))
    messages = list(_walk_assertions(data.get("assertions"), root_subject))
    return AceReport(
        epub_path=epub_path,
        accessible=_is_accessible(data, messages),
        ace_version=_report_version(data),
        messages=messages,
    )


def run_ace(
    epub_path: Path,
    ace: Path,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    should_cancel: CancelCheck | None = None,
) -> AceReport:
    """Uruchamia DAISY Ace na pliku EPUB i zwraca sparsowany raport dostępności.

    Args:
        epub_path: audytowany plik EPUB.
        ace: ścieżka do pliku wykonywalnego ``ace``.
        timeout: maksymalny czas audytu w sekundach.
        should_cancel: opcjonalny predykat anulowania. Gdy podany, audyt biegnie
            strumieniowo (proces da się ubić); ``None`` = klasyczny ``subprocess.run``.

    Returns:
        :class:`AceReport`; ``accessible`` odzwierciedla wynik audytu. Niedostępny
        EPUB to NIE wyjątek.

    Raises:
        ValidationError: timeout, anulowanie, brak raportu JSON lub niepoprawny JSON.
    """
    with tempfile.TemporaryDirectory(prefix="epubforge-ace-") as tmp_dir:
        # Ace odmawia pisania do NIEPUSTEGO katalogu bez --force; wskazujemy podkatalog,
        # którego jeszcze nie ma — Ace go tworzy i zapisuje tam report.json.
        outdir = Path(tmp_dir) / "report"
        report_path = outdir / "report.json"
        # Argumenty listą — bezpieczne dla polskich znaków w ścieżkach (pułapka #3).
        cmd = [str(ace), "--outdir", str(outdir), str(epub_path)]
        started = time.monotonic()
        if should_cancel is not None:
            stderr = _run_cancellable(cmd, timeout, should_cancel)
        else:
            stderr = _run_blocking(cmd, timeout)
        duration = time.monotonic() - started
        data = _load_report_json(report_path, stderr)

    report = parse_ace_report(data, epub_path)
    return AceReport(
        epub_path=report.epub_path,
        accessible=report.accessible,
        ace_version=report.ace_version,
        messages=report.messages,
        duration_s=round(duration, 3),
    )


def _run_blocking(cmd: list[str], timeout: int) -> str:
    """Uruchamia Ace synchronicznie (``subprocess.run``); zwraca ``stderr``.

    Kod wyjścia Ace ignorujemy — o dostępności decyduje raport (Ace zwraca
    niezerowy kod także dla znalezionych naruszeń, co nie jest błędem technicznym).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValidationError(
            _("Ace przekroczył limit czasu ({timeout}s).").format(timeout=timeout)
        ) from exc
    except OSError as exc:
        raise ValidationError(
            _("Nie udało się uruchomić Ace: {error}").format(error=exc)
        ) from exc
    return result.stderr


def _run_cancellable(cmd: list[str], timeout: int, should_cancel: CancelCheck) -> str:
    """Uruchamia Ace strumieniowo z możliwością anulowania; zwraca zebrany log jako ``stderr``."""
    captured: list[str] = []
    result = run_subprocess_streaming(
        cmd,
        lambda text, _level: captured.append(text),
        should_cancel=should_cancel,
        timeout=timeout,
    )
    stderr = "\n".join(captured)
    if result.cancelled:
        raise ValidationError(_("Audyt dostępności anulowano."))
    if result.timed_out:
        raise ValidationError(
            _("Ace przekroczył limit czasu ({timeout}s).").format(timeout=timeout)
        )
    return stderr


def _load_report_json(report_path: Path, stderr: str) -> dict[str, Any]:
    """Wczytuje i waliduje raport JSON; przy braku/uszkodzeniu rzuca błąd ze ``stderr``."""
    if not report_path.is_file():
        raise ValidationError(
            _("Ace nie utworzył raportu JSON.\n{stderr}").format(stderr=stderr.strip())
        )
    try:
        with report_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValidationError(
            _("Nie udało się odczytać raportu Ace: {error}").format(error=exc)
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError(_("Raport Ace ma nieoczekiwany format."))
    return data
