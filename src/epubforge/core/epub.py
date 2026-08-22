"""Klasa :class:`Epub` — odczyt, edycja i bezpieczny zapis plików EPUB.

EPUB to archiwum ZIP o rygorystycznej strukturze. Naiwny zapis przez
``zipfile.write()`` w pętli tworzy plik odrzucany przez EpubCheck i część
czytników. Ten moduł respektuje wymogi specyfikacji OCF:

* wpis ``mimetype`` jest **pierwszy** w archiwum i zapisany **bez kompresji**;
* ścieżka pliku OPF jest **odczytywana** z ``META-INF/container.xml`` (nie zgadywana);
* zapis jest **atomowy** (plik tymczasowy + :func:`os.replace`);
* niezmienione wpisy są **kopiowane strumieniowo** ze źródłowego archiwum,
  więc do pamięci trafiają tylko zmodyfikowane pliki (istotne dla dużych EPUB-ów).
"""

from __future__ import annotations

import logging
import os
import posixpath
import shutil
import tempfile
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from lxml import etree

from epubforge.core._archive import (
    DEFAULT_LIMITS,
    EPUB_CONTAINER_PATH,
    ArchiveLimits,
    validate_epub_archive,
    validate_member_name,
)
from epubforge.core._epub_write import (
    assert_staged_identity,
    discard_staged,
    is_same_target,
    publish_staged,
    rotate_backups,
    stage_epub,
    write_epub,
)
from epubforge.core._xml_safe import parse_untrusted
from epubforge.core.exceptions import (
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
    ResourceLimitError,
)
from epubforge.core.metadata import Metadata

logger = logging.getLogger(__name__)

# Stałe ścieżki i przestrzenie nazw wg specyfikacji OCF/OPF.
_CONTAINER_PATH = EPUB_CONTAINER_PATH
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF_NS = "http://www.idpf.org/2007/opf"

# Domyślna liczba przechowywanych backupów (najnowszy + starsze rotowane).
# Konfigurowalne per-wywołanie przez ``Epub.save(backup_retention=…)`` / ``backup``.
DEFAULT_BACKUP_RETENTION = 5


@dataclass(frozen=True)
class ManifestItem:
    """Pojedynczy wpis z manifestu OPF (``<item>``).

    Attributes:
        id: identyfikator wpisu (atrybut ``id``), używany jako idref w spine.
        href: ścieżka do zasobu **względem katalogu pliku OPF**.
        media_type: typ MIME zasobu (np. ``application/xhtml+xml``).
        properties: wartość atrybutu ``properties`` lub ``None`` gdy brak.
    """

    id: str
    href: str
    media_type: str
    properties: str | None = None


@dataclass(frozen=True)
class PendingChanges:
    """Migawka niezapisanych zmian w buforze :class:`Epub`.

    ``modified`` jest kopią słownika zmian, a ``deleted`` niemutowalnym zbiorem
    ścieżek, więc wywołujący nie dostaje referencji do wewnętrznych struktur.
    """

    modified: dict[str, bytes]
    deleted: frozenset[str]


def _parse_opf_path(container_xml: bytes) -> str:
    """Wyciąga ścieżkę pliku OPF z zawartości ``META-INF/container.xml``.

    Raises:
        OpfNotFoundError: gdy XML jest niepoprawny albo brak elementu
            ``<rootfile full-path=...>``.
    """
    try:
        root = parse_untrusted(container_xml)
    except etree.XMLSyntaxError as exc:
        raise OpfNotFoundError(f"Niepoprawny {_CONTAINER_PATH}: {exc}") from exc
    rootfile = root.find(f"{{{_CONTAINER_NS}}}rootfiles/{{{_CONTAINER_NS}}}rootfile")
    full_path = rootfile.get("full-path") if rootfile is not None else None
    if not full_path:
        raise OpfNotFoundError(f"Brak <rootfile full-path> w {_CONTAINER_PATH}")
    return full_path


class Epub:
    """Reprezentuje plik EPUB otwarty do odczytu i edycji.

    Manifest i spine są wczytywane leniwie (dopiero przy pierwszym dostępie).
    Zmiany wprowadzone przez :meth:`write_file` trafiają do bufora w pamięci
    i są utrwalane dopiero w :meth:`save`.

    Można używać jako context managera::

        with Epub(Path("book.epub")) as epub:
            data = epub.read_file(epub.opf_path)
            epub.write_file("OEBPS/text/ch1.xhtml", new_html)
            epub.save()
    """

    def __init__(self, path: Path, *, limits: ArchiveLimits | None = None) -> None:
        """Inicjalizuje obiekt bez otwierania pliku.

        Args:
            path: ścieżka do pliku ``.epub`` na dysku.
            limits: limity bezpieczeństwa dla niezaufanego archiwum. ``None`` =
                :data:`~epubforge.core._archive.DEFAULT_LIMITS` (bezpieczne dla
                typowych dużych EPUB-ów). Podaj własne, by świadomie je podnieść.
        """
        self.path = Path(path)
        self._limits = limits if limits is not None else DEFAULT_LIMITS
        self._zip: zipfile.ZipFile | None = None
        self._source_stat: os.stat_result | None = None
        self._modified: dict[str, bytes] = {}
        self._deleted: set[str] = set()
        self._opf_path: str | None = None
        self._manifest: list[ManifestItem] | None = None
        self._spine: list[str] | None = None

    # ── Cykl życia ──────────────────────────────────────────────────────────

    def open(self) -> None:
        """Otwiera archiwum do odczytu i waliduje, że to EPUB.

        Raises:
            InvalidEpubError: plik nie istnieje lub nie jest archiwum ZIP.
            OpfNotFoundError: brak ``META-INF/container.xml``.
        """
        if self._zip is not None:
            return
        if not self.path.is_file():
            raise InvalidEpubError(f"Plik EPUB nie istnieje: {self.path}")
        try:
            zf = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as exc:
            raise InvalidEpubError(f"Plik nie jest poprawnym archiwum ZIP: {self.path}") from exc
        # Centralna walidacja niezaufanego archiwum PRZED jakimkolwiek odczytem
        # treści — bomby ZIP i niekanoniczne nazwy odrzucamy na metadanych.
        try:
            validate_epub_archive(zf, self._limits)
        except (ResourceLimitError, OpfNotFoundError):
            zf.close()
            raise
        self._zip = zf
        assert zf.fp is not None
        self._source_stat = os.fstat(zf.fp.fileno())
        logger.debug("Otwarto EPUB: %s", self.path)

    def close(self) -> None:
        """Zamyka archiwum i czyszcze bufor zmian oraz cache.

        Niezapisane zmiany (z :meth:`write_file`) są przy tym tracone.
        """
        if self._zip is not None:
            self._zip.close()
            self._zip = None
        self._source_stat = None
        self._modified.clear()
        self._deleted.clear()
        self._reset_cache()

    def __enter__(self) -> Epub:
        """Otwiera EPUB przy wejściu do bloku ``with``."""
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Zamyka EPUB przy wyjściu z bloku ``with`` (nie tłumi wyjątków)."""
        self.close()

    # ── Właściwości (leniwe) ────────────────────────────────────────────────

    @property
    def opf_path(self) -> str:
        """Ścieżka pliku OPF wewnątrz archiwum (z ``container.xml``)."""
        if self._opf_path is None:
            self._opf_path = _parse_opf_path(self._read_xml(_CONTAINER_PATH))
        return self._opf_path

    @property
    def manifest(self) -> list[ManifestItem]:
        """Lista wpisów manifestu OPF (wczytywana leniwie)."""
        if self._manifest is None:
            self._parse_opf()
        assert self._manifest is not None
        return self._manifest

    @property
    def spine(self) -> list[str]:
        """Kolejność czytania jako lista idref (wczytywana leniwie)."""
        if self._spine is None:
            self._parse_opf()
        assert self._spine is not None
        return self._spine

    @property
    def metadata(self) -> Metadata:
        """Metadane Dublin Core sparsowane z bieżącego OPF."""
        return Metadata.from_opf(self._read_xml(self.opf_path))

    @metadata.setter
    def metadata(self, value: Metadata) -> None:
        """Wpisuje metadane do OPF i utrwala zmianę na dysku (z backupem)."""
        new_opf = value.to_opf(self._read_xml(self.opf_path))
        self.write_file(self.opf_path, new_opf)
        self.save()

    # ── Operacje na plikach wewnętrznych ─────────────────────────────────────

    def read_file(self, internal_path: str) -> bytes:
        """Zwraca zawartość pliku wewnątrz EPUB-a.

        Uwzględnia niezapisane zmiany z :meth:`write_file`.

        Args:
            internal_path: ścieżka względna wewnątrz archiwum (z ``/``).

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
            KeyError: gdy plik nie istnieje w archiwum.
        """
        zf = self._ensure_open()
        if internal_path in self._deleted:
            raise KeyError(internal_path)
        if internal_path in self._modified:
            return self._modified[internal_path]
        return zf.read(internal_path)

    def write_file(self, internal_path: str, data: bytes) -> None:
        """Zapisuje zmianę pliku do bufora w pamięci (utrwalane w :meth:`save`).

        Args:
            internal_path: ścieżka względna wewnątrz archiwum (z ``/``).
            data: nowa zawartość pliku.

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        self._ensure_open()
        validate_member_name(internal_path)
        self._deleted.discard(internal_path)
        self._modified[internal_path] = data
        # Modyfikacja OPF unieważnia zcache'owany manifest/spine.
        if internal_path == self._opf_path:
            self._manifest = None
            self._spine = None

    def delete_file(self, internal_path: str) -> None:
        """Oznacza plik wewnętrzny do usunięcia przy następnym :meth:`save`.

        Args:
            internal_path: ścieżka względna wewnątrz archiwum (z ``/``).

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        self._ensure_open()
        validate_member_name(internal_path)
        self._modified.pop(internal_path, None)
        self._deleted.add(internal_path)
        if internal_path == self._opf_path:
            self._reset_cache()

    def list_files(self) -> list[str]:
        """Zwraca listę wszystkich plików w archiwum (z dodanymi przez bufor).

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        zf = self._ensure_open()
        names = [name for name in zf.namelist() if name not in self._deleted]
        for name in self._modified:
            if name not in names:
                names.append(name)
        return names

    def pending_changes(self) -> PendingChanges:
        """Zwraca bufor także po błędzie save, gdy recovery nie otworzył uchwytu."""
        return PendingChanges(modified=dict(self._modified), deleted=frozenset(self._deleted))

    # ── Zapis i backup ───────────────────────────────────────────────────────

    def save(
        self,
        output_path: Path | None = None,
        *,
        backup_retention: int = DEFAULT_BACKUP_RETENTION,
    ) -> Path:
        """Zapisuje EPUB z poprawną strukturą ZIP (atomowo, z fsync i backupem).

        Zapis nadpisujący oryginał jest bezpieczny: najpierw powstaje rotowany
        backup, potem nowa treść trafia do unikalnego tempa w katalogu docelowym,
        jest fsyncowana i podmieniana atomowo. Przy dowolnym błędzie (brak miejsca,
        brak uprawnień, przerwana podmiana) **oryginał zostaje nietknięty**.

        Args:
            output_path: gdy ``None`` — nadpisuje oryginał (po :meth:`backup`).
                Wskazanie ścieżki równej źródłu jest traktowane jak nadpisanie
                oryginału (backup + reopen), NIE jako zapis „obok". Inna ścieżka
                zapisuje kopię, a bieżąca sesja pozostaje otwarta na oryginale.
            backup_retention: liczba przechowywanych backupów przy nadpisaniu
                oryginału (najnowszy + starsze rotowane). ``<= 1`` = tylko najnowszy.

        Returns:
            Ścieżka faktycznie zapisanego pliku.

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        self._ensure_open()
        self._assert_source_unchanged()
        modified = dict(self._modified)
        deleted = set(self._deleted)
        target = self.path if output_path is None else Path(output_path)
        if not is_same_target(target, self.path):
            # Zapis „obok" — sesja zostaje otwarta na oryginale, bez backupu.
            write_epub(self.path, target, modified, deleted, self._limits)
            logger.debug("Zapisano EPUB jako: %s", target)
            return target
        # Overwrite transaction: stage+validate while source is open, then backup,
        # close for Windows, atomic publish, reopen, and only then commit memory.
        staged = stage_epub(self.path, self.path, modified, deleted, self._limits)
        try:
            # Do not rotate backup history for a candidate already changed/rejected.
            assert_staged_identity(staged)
            self._assert_source_unchanged()
            self.backup(retention=backup_retention)
            self._assert_source_unchanged()
            assert self._zip is not None
            self._zip.close()
            self._zip = None
            try:
                publish_staged(staged, self.path)
                self._reset_cache()
                self.open()
            except BaseException:
                # Preserve the original failure. Recovery errors are logged only;
                # pending remains observable and is never cleared on this path.
                self._reset_cache()
                if self._zip is None:
                    try:
                        self.open()
                    except BaseException:
                        logger.exception("Nie udało się odtworzyć sesji EPUB po błędzie zapisu")
                raise
        finally:
            with suppress(OSError):
                discard_staged(staged)
        self._modified.clear()
        self._deleted.clear()
        self._reset_cache()
        logger.debug("Nadpisano EPUB: %s", self.path)
        return self.path

    def backup(self, *, retention: int = DEFAULT_BACKUP_RETENTION) -> Path:
        """Tworzy rotowany backup oryginału obok niego.

        Najnowszy backup zawsze leży pod stabilną nazwą ``<plik>.bak``; wcześniejsze
        są rotowane do ``<plik>.bak.1``, ``<plik>.bak.2``… aż do ``retention``
        (starsze są usuwane). Dzięki temu żaden zapis nie nadpisuje po cichu jedynej
        kopii bezpieczeństwa.

        Args:
            retention: łączna liczba zachowywanych backupów. ``<= 1`` = brak rotacji
                (tylko najnowszy ``.bak``).

        Returns:
            Ścieżka najnowszego backupu (``<plik>.bak``).
        """
        primary = self.path.with_name(self.path.name + ".bak")
        fd, tmp_name = tempfile.mkstemp(
            dir=primary.parent, prefix=f".{primary.name}.", suffix=".tmp"
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            # Copy first: a read/copy failure must not mutate existing history.
            zf = self._ensure_open()
            assert zf.fp is not None
            original_offset = zf.fp.tell()
            duplicate = os.dup(zf.fp.fileno())
            try:
                with os.fdopen(duplicate, "rb") as source, tmp.open("wb") as destination:
                    source.seek(0)
                    shutil.copyfileobj(source, destination, self._limits.copy_buffer_size)
            finally:
                zf.fp.seek(original_offset)
            rotate_backups(primary, retention)
            os.replace(tmp, primary)
        finally:
            with suppress(OSError):
                tmp.unlink(missing_ok=True)
        logger.debug("Utworzono backup: %s (retention=%d)", primary, retention)
        return primary

    # ── Wewnętrzne ────────────────────────────────────────────────────────────

    def _ensure_open(self) -> zipfile.ZipFile:
        """Zwraca otwarty uchwyt ZIP albo rzuca :class:`EpubNotOpenError`."""
        if self._zip is None:
            raise EpubNotOpenError("EPUB nie jest otwarty — wywołaj open() lub użyj 'with'.")
        return self._zip

    def _assert_source_unchanged(self) -> None:
        """Odrzuca save, gdy pathname nie wskazuje archiwum otwartego przez sesję."""
        if self._source_stat is None:
            raise EpubNotOpenError("Brak tożsamości otwartego źródła EPUB.")
        current = os.stat(self.path, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(current, field) != getattr(self._source_stat, field) for field in fields):
            raise OSError("Plik źródłowy EPUB zmienił się od czasu otwarcia; zapis przerwany.")

    def _read_xml(self, internal_path: str) -> bytes:
        """Odczyt wpisu przeznaczonego do parsowania XML/tekstu — z limitem ``max_text_size``.

        Dla wpisów z dysku sprawdza rozmiar nieskompresowany na metadanych ZIP PRZED
        odczytem, więc „duży XML” zostaje odrzucony zanim trafi do parsera lxml.
        Bufor zapisów w pamięci (nasze własne bajty) nie jest limitowany.
        """
        if internal_path not in self._modified and internal_path not in self._deleted:
            zf = self._ensure_open()
            try:
                info = zf.getinfo(internal_path)
            except KeyError:
                info = None
            if info is not None and info.file_size > self._limits.max_text_size:
                raise ResourceLimitError(
                    f"Plik XML/tekst {internal_path!r} przekracza limit "
                    f"({info.file_size} > {self._limits.max_text_size} B)."
                )
        return self.read_file(internal_path)

    def _reset_cache(self) -> None:
        """Czyści zcache'owaną ścieżkę OPF, manifest i spine."""
        self._opf_path = None
        self._manifest = None
        self._spine = None

    def _parse_opf(self) -> None:
        """Parsuje plik OPF i wypełnia cache manifestu oraz spine."""
        try:
            root = parse_untrusted(self._read_xml(self.opf_path))
        except etree.XMLSyntaxError as exc:
            raise OpfNotFoundError(f"Niepoprawny plik OPF ({self.opf_path}): {exc}") from exc

        manifest: list[ManifestItem] = []
        for item in root.iterfind(f"{{{_OPF_NS}}}manifest/{{{_OPF_NS}}}item"):
            item_id = item.get("id")
            href = item.get("href")
            media_type = item.get("media-type")
            if item_id is None or href is None or media_type is None:
                continue
            manifest.append(
                ManifestItem(
                    id=item_id,
                    href=href,
                    media_type=media_type,
                    properties=item.get("properties"),
                )
            )

        spine: list[str] = []
        for itemref in root.iterfind(f"{{{_OPF_NS}}}spine/{{{_OPF_NS}}}itemref"):
            idref = itemref.get("idref")
            if idref is not None:
                spine.append(idref)

        self._manifest = manifest
        self._spine = spine

    def opf_dir(self) -> str:
        """Zwraca katalog pliku OPF (przydatny do rozwiązywania ``href``)."""
        return posixpath.dirname(self.opf_path)
