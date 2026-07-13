"""Walidacja EPUB przez EpubCheck 5.x (``java -jar epubcheck.jar … --json``).

Moduł jest czysty (bez Qt): uruchamia EpubCheck w subprocessie, parsuje raport
JSON i zwraca :class:`ValidationReport`. Sam wynik „EPUB jest niepoprawny" NIE
jest błędem (wraca jako ``valid=False``); :class:`ValidationError` rezerwujemy na
sytuacje techniczne: brak/zepsuty JSON, timeout, brak narzędzi.

Parser jest **defensywny** — format JSON EpubChecka bywa modyfikowany między
wersjami, więc każde pole czytamy przez ``.get`` i normalizujemy ścieżki lokalizacji
do ścieżek WEWNĄTRZ EPUB-a (EpubCheck potrafi prefiksować je nazwą archiwum).
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

from epubforge.core.exceptions import ValidationError
from epubforge.core.process import DEFAULT_PROCESS_LIMITS, run_process
from epubforge.core.streaming import CancelCheck, run_subprocess_streaming
from epubforge.i18n import _

_DEFAULT_TIMEOUT = 300  # sekundy

# Wytnij wszystko do „<nazwa>.epub/" włącznie — zostaje ścieżka wewnątrz EPUB-a.
_EPUB_PREFIX = re.compile(r"^.*?\.epub/", re.IGNORECASE)


class Severity(str, Enum):
    """Poziom istotności komunikatu walidacji (znormalizowany).

    Dziedziczy po ``str``, więc serializuje się do JSON jako swoja wartość
    (``dataclasses.asdict`` + ``json.dumps`` działają bez konwersji).
    """

    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Mapowanie surowych poziomów EpubChecka na nasze (USAGE/SUPPRESSED → info).
_SEVERITY_MAP = {
    "fatal": Severity.FATAL,
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
    "usage": Severity.INFO,
    "suppressed": Severity.INFO,
}


@dataclass(frozen=True)
class ValidationMessage:
    """Pojedynczy komunikat z raportu EpubChecka."""

    severity: Severity
    code: str
    message: str
    internal_path: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Wynik walidacji jednego pliku EPUB."""

    epub_path: Path
    valid: bool
    epubcheck_version: str
    messages: list[ValidationMessage] = field(default_factory=list)
    duration_s: float = 0.0

    def counts(self) -> dict[Severity, int]:
        """Zlicza komunikaty per poziom istotności."""
        counter: Counter[Severity] = Counter(msg.severity for msg in self.messages)
        return {severity: counter.get(severity, 0) for severity in Severity}


def _severity_from_raw(raw: object) -> Severity:
    """Mapuje surowy poziom EpubChecka na :class:`Severity` (fallback: info)."""
    key = str(raw).strip().lower() if raw is not None else ""
    return _SEVERITY_MAP.get(key, Severity.INFO)


def _normalize_path(raw: object) -> str | None:
    """Sprowadza ścieżkę lokalizacji do postaci wewnątrz EPUB-a (lub ``None``)."""
    if not isinstance(raw, str) or not raw:
        return None
    normalized = raw.replace("\\", "/")
    normalized = _EPUB_PREFIX.sub("", normalized)
    return normalized.lstrip("/") or None


def _as_int(raw: object) -> int | None:
    """Zwraca dodatnią liczbę całkowitą albo ``None`` (EpubCheck używa -1 dla braku)."""
    if isinstance(raw, bool):  # bool jest podtypem int — odrzucamy jawnie
        return None
    if isinstance(raw, int) and raw >= 0:
        return raw
    return None


def _parse_message(raw: object) -> ValidationMessage | None:
    """Buduje :class:`ValidationMessage` z surowego wpisu ``messages[]`` (defensywnie)."""
    if not isinstance(raw, dict):
        return None
    locations = raw.get("locations")
    location = locations[0] if isinstance(locations, list) and locations else {}
    location = location if isinstance(location, dict) else {}
    return ValidationMessage(
        severity=_severity_from_raw(raw.get("severity")),
        code=str(raw.get("ID", "") or ""),
        message=str(raw.get("message", "") or ""),
        internal_path=_normalize_path(location.get("path")),
        line=_as_int(location.get("line")),
        column=_as_int(location.get("column")),
    )


def parse_report(data: dict[str, Any], epub_path: Path, *, valid: bool) -> ValidationReport:
    """Parsuje słownik JSON EpubChecka do :class:`ValidationReport`."""
    checker = data.get("checker")
    checker = checker if isinstance(checker, dict) else {}
    version = str(checker.get("checkerVersion", "") or "")

    raw_messages = data.get("messages")
    raw_messages = raw_messages if isinstance(raw_messages, list) else []
    messages = [parsed for raw in raw_messages if (parsed := _parse_message(raw)) is not None]
    return ValidationReport(
        epub_path=epub_path,
        valid=valid,
        epubcheck_version=version,
        messages=messages,
    )


def run_epubcheck(
    epub_path: Path,
    java: Path,
    jar: Path,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    should_cancel: CancelCheck | None = None,
) -> ValidationReport:
    """Uruchamia EpubCheck na pliku EPUB i zwraca sparsowany raport.

    Args:
        epub_path: walidowany plik EPUB.
        java: ścieżka do pliku wykonywalnego ``java``.
        jar: ścieżka do ``epubcheck.jar``.
        timeout: maksymalny czas walidacji w sekundach.
        should_cancel: opcjonalny predykat anulowania. Gdy podany, walidacja biegnie
            strumieniowo (log na żywo); ``None`` = wariant synchroniczny. Oba idą
            przez wspólny runner (``core/process.py``) — ta sama semantyka i timeout.

    Returns:
        :class:`ValidationReport`; ``valid`` odzwierciedla kod wyjścia EpubChecka
        (0 = poprawny). Niepoprawny EPUB to NIE wyjątek.

    Raises:
        ValidationError: timeout, anulowanie, brak raportu JSON lub niepoprawny JSON.
    """
    with tempfile.TemporaryDirectory(prefix="epubforge-check-") as tmp_dir:
        report_path = Path(tmp_dir) / "report.json"
        # Argumenty listą — bezpieczne dla polskich znaków w ścieżkach (pułapka #3).
        cmd = [str(java), "-jar", str(jar), str(epub_path), "--json", str(report_path)]
        started = time.monotonic()
        if should_cancel is not None:
            returncode, stderr = _run_cancellable(cmd, timeout, should_cancel)
        else:
            returncode, stderr = _run_blocking(cmd, timeout)
        duration = time.monotonic() - started
        data = _load_report_json(report_path, stderr)

    report = parse_report(data, epub_path, valid=returncode == 0)
    return ValidationReport(
        epub_path=report.epub_path,
        valid=report.valid,
        epubcheck_version=report.epubcheck_version,
        messages=report.messages,
        duration_s=round(duration, 3),
    )


def _run_blocking(cmd: list[str], timeout: int) -> tuple[int, str]:
    """Uruchamia EpubCheck synchronicznie przez wspólny runner; zwraca ``(kod, log)``.

    Semantyka identyczna z wariantem strumieniowym: ten sam runner, ten sam
    timeout ubijający całe drzewo procesu, ten sam (scalony) log jako kontekst.
    """
    try:
        result = run_process(cmd, limits=replace(DEFAULT_PROCESS_LIMITS, timeout=timeout))
    except OSError as exc:
        raise ValidationError(
            _("Nie udało się uruchomić EpubCheck: {error}").format(error=exc)
        ) from exc
    if result.timed_out:
        raise ValidationError(
            _("EpubCheck przekroczył limit czasu ({timeout}s).").format(timeout=timeout)
        )
    return result.returncode, result.output


def _run_cancellable(cmd: list[str], timeout: int, should_cancel: CancelCheck) -> tuple[int, str]:
    """Uruchamia EpubCheck strumieniowo z możliwością anulowania; zwraca ``(kod, stderr)``.

    Log EpubChecka trafia (przez ``stderr`` scalony ze ``stdout``) do bufora, który
    zwracamy jako drugi element — służy jako kontekst błędu, tak jak w wariancie
    synchronicznym.
    """
    captured: list[str] = []
    result = run_subprocess_streaming(
        cmd,
        lambda text, _level: captured.append(text),
        should_cancel=should_cancel,
        timeout=timeout,
    )
    stderr = "\n".join(captured)
    if result.cancelled:
        raise ValidationError(_("Walidację anulowano."))
    if result.timed_out:
        raise ValidationError(
            _("EpubCheck przekroczył limit czasu ({timeout}s).").format(timeout=timeout)
        )
    return result.returncode, stderr


def _load_report_json(report_path: Path, stderr: str) -> dict[str, Any]:
    """Wczytuje i waliduje raport JSON; przy braku/uszkodzeniu rzuca błąd ze ``stderr``."""
    if not report_path.is_file():
        raise ValidationError(
            _("EpubCheck nie utworzył raportu JSON.\n{stderr}").format(stderr=stderr.strip())
        )
    try:
        with report_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValidationError(
            _("Nie udało się odczytać raportu EpubCheck: {error}").format(error=exc)
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError(_("Raport EpubCheck ma nieoczekiwany format."))
    return data
