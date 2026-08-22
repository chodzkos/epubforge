"""Bezpieczny, atomowy zapis archiwum EPUB oraz rotacja backupów (F-14).

Wydzielone z :mod:`epubforge.core.epub`, by trzymać moduły poniżej 500 linii.
Tu mieszka niska warstwa zapisu:

* budowa poprawnego strukturalnie ZIP-a (mimetype pierwszy, kopie strumieniowe),
* **atomowy** zapis przez unikalny tempfile w KATALOGU DOCELOWYM + ``os.replace``,
* **fsync** pliku i (na POSIX) katalogu — trwałość podmiany przy awarii zasilania,
* sprzątanie tempa po dowolnym błędzie — **oryginał nigdy nie zostaje uszkodzony**,
* **rotacja backupów** (logrotate) z konfigurowalną retencją.
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
import zlib
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from epubforge.core._archive import (
    DEFAULT_LIMITS,
    ArchiveLimits,
    copy_entry_streamed,
    validate_archive,
    validate_epub_archive,
    validate_member_name,
)
from epubforge.core.exceptions import ResourceLimitError

_MIMETYPE_PATH = "mimetype"
_MIMETYPE_CONTENT = b"application/epub+zip"

# Stały timestamp ZIP (1980-01-01 — minimum formatu) dla wpisów zapisywanych po nazwie.
# ``writestr`` z gołą nazwą wstawia ``time.localtime()``, więc te same dane logiczne dawały
# różne bajty przy kolejnych zapisach (zależnie od zegara) — łamało to reprodukowalność i
# idempotencję (np. dwukrotny upgrade EPUB 2→3). Wpisy KOPIOWANE ze źródła zachowują swój
# oryginalny ``date_time`` (przez ZipInfo), więc niezmieniona treść daje niezmienne bajty.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class StagedEpub:
    """Gotowy, zwalidowany kandydat oraz jego tożsamość z chwili walidacji."""

    path: Path
    validated_stat: os.stat_result
    limits: ArchiveLimits


def _named_entry(name: str, compress_type: int) -> zipfile.ZipInfo:
    """Buduje :class:`zipfile.ZipInfo` z **deterministycznym** ``date_time`` (:data:`_ZIP_EPOCH`).

    Używane zamiast gołej nazwy w ``writestr``, by zapis był reprodukowalny (bez zegara
    ściennego w nagłówku ZIP).
    """
    info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
    info.compress_type = compress_type
    return info


def _payload_compress_type(data: bytes, limits: ArchiveLimits) -> int:
    """Wybiera STORED, gdy własny DEFLATE przekroczyłby limit openera.

    To optymalizacja legalnych danych wygenerowanych przez aplikację, nie osłabienie
    walidacji: skończony kandydat nadal przechodzi pełną politykę archiwum.
    """
    if len(data) <= limits.ratio_check_min_size:
        return zipfile.ZIP_DEFLATED
    compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(data) + compressor.flush()
    if not compressed or len(data) / len(compressed) > limits.max_compression_ratio:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def write_epub(
    source: Path,
    target: Path,
    modified: dict[str, bytes],
    deleted: set[str],
    limits: ArchiveLimits = DEFAULT_LIMITS,
) -> None:
    """Zapisuje EPUB kopiując niezmienione wpisy **strumieniowo** ze źródła (atomowo).

    W pamięci trzymamy wyłącznie zmodyfikowane pliki (``modified``); niezmienione
    wpisy kopiujemy strumieniowo, więc pamięć szczytowa NIE rośnie z rozmiarem
    największego wpisu. Nowa treść trafia do UNIKALNEGO tempa w katalogu docelowym,
    jest fsyncowana i podmieniana atomowo (``os.replace``). Przy dowolnym błędzie
    (brak miejsca, brak uprawnień, przerwana podmiana) temp jest sprzątany, a
    **oryginał ``target`` pozostaje nietknięty**.

    Args:
        source: oryginalny EPUB — źródło niezmienionych wpisów.
        target: plik docelowy (może być identyczny z ``source``).
        modified: zmienione/nowe pliki jako ``{ścieżka_wewnętrzna: dane}``.
        deleted: ścieżki wpisów, których nie należy kopiować do wyjścia.
        limits: limity bezpieczeństwa (walidacja źródła + rozmiar bufora kopii).
    """
    staged = stage_epub(source, target, modified, deleted, limits)
    try:
        publish_staged(staged, target)
    except BaseException:
        with suppress(OSError):
            discard_staged(staged)
        raise


def stage_epub(
    source: Path,
    target: Path,
    modified: dict[str, bytes],
    deleted: set[str],
    limits: ArchiveLimits = DEFAULT_LIMITS,
) -> StagedEpub:
    """Buduje, fsyncuje i waliduje unikalny tempfile bez publikowania celu."""
    # Walidacja przed jakąkolwiek zmianą katalogu/docelowej ścieżki jest granicą
    # niskopoziomowego API także dla callerów omijających ``Epub.write_file``.
    for name in (*modified, *deleted):
        validate_member_name(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        _write_zip_entries(source, tmp, modified, deleted, limits)
        with tmp.open("rb") as candidate_file:
            with zipfile.ZipFile(candidate_file) as candidate:
                validate_epub_archive(candidate, limits)
            with suppress(OSError):
                os.fsync(candidate_file.fileno())
            validated_stat = os.fstat(candidate_file.fileno())
        staged = StagedEpub(tmp, validated_stat, limits)
        assert_staged_identity(staged)
        return staged
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def assert_staged_identity(staged: StagedEpub) -> None:
    """Wykrywa podmianę lub modyfikację kandydata po pełnej walidacji."""
    current = os.stat(staged.path, follow_symlinks=False)
    if not _same_identity(current, staged.validated_stat):
        raise OSError("Plik tymczasowy EPUB zmienił się po walidacji; publikacja przerwana.")


def _same_identity(current: os.stat_result, validated: os.stat_result) -> bool:
    """Porównuje tożsamość i metadane istotne dla zwalidowanej zawartości."""
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    return all(getattr(current, field) == getattr(validated, field) for field in fields)


def publish_staged(staged: StagedEpub, target: Path) -> None:
    """Ponownie waliduje dokładny uchwyt i atomowo publikuje kandydat."""
    assert_staged_identity(staged)
    # Backup i zamknięcie źródła mogły trwać. Ponownie sprawdź gotowy ZIP na
    # uchwycie, a potem potwierdź, że pathname nadal wskazuje ten sam obiekt.
    with staged.path.open("rb") as candidate_file:
        with zipfile.ZipFile(candidate_file) as candidate:
            validate_epub_archive(candidate, staged.limits)
        if not _same_identity(os.fstat(candidate_file.fileno()), staged.validated_stat):
            raise OSError("Plik tymczasowy EPUB zmienił się po walidacji; publikacja przerwana.")
    assert_staged_identity(staged)
    os.replace(staged.path, target)
    _fsync_dir(target.parent)


def discard_staged(staged: StagedEpub) -> None:
    """Usuwa nieopublikowany tempfile; bez błędu, gdy replace już go przeniósł."""
    with suppress(OSError):
        staged.path.unlink(missing_ok=True)


def _write_zip_entries(
    source: Path,
    tmp: Path,
    modified: dict[str, bytes],
    deleted: set[str],
    limits: ArchiveLimits,
) -> None:
    """Składa poprawny strukturalnie EPUB w pliku ``tmp`` (mimetype pierwszy, kopie strumieniowe)."""
    written: set[str] = set()
    operations = 0
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(tmp, "w") as zout:
        # Odrzuć złośliwe źródło PRZED kosztowną dekompresją/kopiowaniem.
        validate_archive(zin, limits)
        # 1. mimetype PIERWSZY i BEZ kompresji (deterministyczny timestamp).
        zout.writestr(_named_entry(_MIMETYPE_PATH, zipfile.ZIP_STORED), _MIMETYPE_CONTENT)
        written.add(_MIMETYPE_PATH)
        # 2. Reszta wpisów ze źródła: zmienione bierzemy z dict, inne kopiujemy.
        for item in zin.infolist():
            if item.filename == _MIMETYPE_PATH or item.filename in deleted:
                continue
            operations += 1
            if operations > limits.max_operations:
                raise ResourceLimitError("Przekroczono budżet operacji zapisu EPUB.")
            data = modified.get(item.filename)
            if data is None:
                # Niezmieniony wpis — kopia STRUMIENIOWA (stały bufor), zachowuje
                # compress_type źródła (STORED, np. obrazy, nie są rekompresowane).
                copy_entry_streamed(zin, zout, item, buffer_size=limits.copy_buffer_size)
            else:
                # Legalne dane własne: STORED tylko gdy DEFLATE złamałby własny ratio.
                zout.writestr(
                    _named_entry(item.filename, _payload_compress_type(data, limits)), data
                )
            written.add(item.filename)
        # 3. Pliki dodane przez write_file, których nie ma jeszcze w źródle.
        for name, data in modified.items():
            if name not in deleted and name not in written:
                zout.writestr(_named_entry(name, _payload_compress_type(data, limits)), data)


def _fsync_dir(directory: Path) -> None:
    """Utrwala wpis katalogu (rename) przez ``fsync`` na deskryptorze katalogu.

    Katalogów NIE da się fsyncować na Windows (``os.open(dir)`` zawodzi) — tam
    pomijamy bez błędu. Na POSIX to domyka trwałość atomowej podmiany. Dodatni
    guard ``!= "win32"`` (a nie wczesny ``return``) — bez martwego kodu na Windows.
    """
    if sys.platform != "win32":
        try:
            fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)


def is_same_target(a: Path, b: Path) -> bool:
    """Czy dwie ścieżki wskazują ten sam plik (obsługa ``output_path == source``)."""
    try:
        if a.exists() and b.exists():
            return a.samefile(b)
    except OSError:
        pass
    return a.resolve() == b.resolve()


def numbered_backup(primary: Path, index: int) -> Path:
    """Ścieżka rotowanego backupu o numerze ``index`` (``<plik>.bak.<index>``)."""
    return primary.with_name(f"{primary.name}.{index}")


def rotate_backups(primary: Path, retention: int) -> None:
    """Rotuje backupy przed nadpisaniem ``primary`` (logrotate: .bak → .bak.1 → …).

    Zachowuje łącznie ``retention`` kopii (najnowszy ``primary`` + starsze
    numerowane). ``retention <= 1`` = brak rotacji (kopia nadpisze ``primary``).
    """
    if retention <= 1 or not primary.exists():
        return
    # Usuń najstarszy, którego już nie zmieścimy, i przesuń resztę o jeden w górę.
    numbered_backup(primary, retention - 1).unlink(missing_ok=True)
    for index in range(retention - 2, 0, -1):
        source = numbered_backup(primary, index)
        if source.exists():
            source.replace(numbered_backup(primary, index + 1))
    primary.replace(numbered_backup(primary, 1))
