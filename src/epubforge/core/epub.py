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
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from epubforge.core.exceptions import (
    EpubNotOpenError,
    InvalidEpubError,
    OpfNotFoundError,
)
from epubforge.core.metadata import Metadata

logger = logging.getLogger(__name__)

# Stałe ścieżki i przestrzenie nazw wg specyfikacji OCF/OPF.
_CONTAINER_PATH = "META-INF/container.xml"
_MIMETYPE_PATH = "mimetype"
_MIMETYPE_CONTENT = b"application/epub+zip"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF_NS = "http://www.idpf.org/2007/opf"


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


def _write_epub(source: Path, target: Path, modified: dict[str, bytes]) -> None:
    """Zapisuje EPUB kopiując niezmienione wpisy strumieniowo ze źródła.

    W pamięci trzymamy wyłącznie zmodyfikowane pliki (``modified``); resztę
    czytamy i przepisujemy wpis po wpisie z ``source``. Zapis jest atomowy.

    Args:
        source: oryginalny EPUB — źródło niezmienionych wpisów.
        target: plik docelowy (może być identyczny z ``source``).
        modified: zmienione/nowe pliki jako ``{ścieżka_wewnętrzna: dane}``.
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    written: set[str] = set()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(tmp, "w") as zout:
        # 1. mimetype PIERWSZY i BEZ kompresji.
        zout.writestr(_MIMETYPE_PATH, _MIMETYPE_CONTENT, compress_type=zipfile.ZIP_STORED)
        written.add(_MIMETYPE_PATH)
        # 2. Reszta wpisów ze źródła: zmienione bierzemy z dict, inne kopiujemy.
        for item in zin.infolist():
            if item.filename == _MIMETYPE_PATH:
                continue
            data = modified.get(item.filename)
            if data is None:
                data = zin.read(item.filename)
            zout.writestr(item.filename, data, compress_type=zipfile.ZIP_DEFLATED)
            written.add(item.filename)
        # 3. Pliki dodane przez write_file, których nie ma jeszcze w źródle.
        for name, data in modified.items():
            if name not in written:
                zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, target)


def _parse_opf_path(container_xml: bytes) -> str:
    """Wyciąga ścieżkę pliku OPF z zawartości ``META-INF/container.xml``.

    Raises:
        OpfNotFoundError: gdy XML jest niepoprawny albo brak elementu
            ``<rootfile full-path=...>``.
    """
    try:
        root = ET.fromstring(container_xml)
    except ET.ParseError as exc:
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

    def __init__(self, path: Path) -> None:
        """Inicjalizuje obiekt bez otwierania pliku.

        Args:
            path: ścieżka do pliku ``.epub`` na dysku.
        """
        self.path = Path(path)
        self._zip: zipfile.ZipFile | None = None
        self._modified: dict[str, bytes] = {}
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
        if _CONTAINER_PATH not in zf.namelist():
            zf.close()
            raise OpfNotFoundError(f"Brak {_CONTAINER_PATH} — to nie jest poprawny EPUB")
        self._zip = zf
        logger.debug("Otwarto EPUB: %s", self.path)

    def close(self) -> None:
        """Zamyka archiwum i czyszcze bufor zmian oraz cache.

        Niezapisane zmiany (z :meth:`write_file`) są przy tym tracone.
        """
        if self._zip is not None:
            self._zip.close()
            self._zip = None
        self._modified.clear()
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
            self._opf_path = _parse_opf_path(self.read_file(_CONTAINER_PATH))
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
        return Metadata.from_opf(self.read_file(self.opf_path))

    @metadata.setter
    def metadata(self, value: Metadata) -> None:
        """Wpisuje metadane do OPF i utrwala zmianę na dysku (z backupem)."""
        new_opf = value.to_opf(self.read_file(self.opf_path))
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
        self._modified[internal_path] = data
        # Modyfikacja OPF unieważnia zcache'owany manifest/spine.
        if internal_path == self._opf_path:
            self._manifest = None
            self._spine = None

    def list_files(self) -> list[str]:
        """Zwraca listę wszystkich plików w archiwum (z dodanymi przez bufor).

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        zf = self._ensure_open()
        names = list(zf.namelist())
        for name in self._modified:
            if name not in names:
                names.append(name)
        return names

    # ── Zapis i backup ───────────────────────────────────────────────────────

    def save(self, output_path: Path | None = None) -> Path:
        """Zapisuje EPUB z poprawną strukturą ZIP.

        Args:
            output_path: gdy ``None`` — nadpisuje oryginał (po wykonaniu
                :meth:`backup`); w przeciwnym razie zapisuje pod wskazaną
                ścieżką, a bieżąca sesja pozostaje otwarta na oryginale.

        Returns:
            Ścieżka faktycznie zapisanego pliku.

        Raises:
            EpubNotOpenError: gdy EPUB nie jest otwarty.
        """
        self._ensure_open()
        modified = dict(self._modified)
        if output_path is not None:
            target = Path(output_path)
            _write_epub(self.path, target, modified)
            logger.debug("Zapisano EPUB jako: %s", target)
            return target
        # Nadpisanie oryginału: backup, zamknięcie uchwytu (Windows), zapis, reopen.
        self.backup()
        assert self._zip is not None
        self._zip.close()
        self._zip = None
        _write_epub(self.path, self.path, modified)
        self._modified.clear()
        self._reset_cache()
        self.open()
        logger.debug("Nadpisano EPUB: %s", self.path)
        return self.path

    def backup(self) -> Path:
        """Tworzy kopię ``.bak`` oryginału obok niego.

        Returns:
            Ścieżka utworzonego pliku backupu.
        """
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        shutil.copy2(self.path, backup_path)
        logger.debug("Utworzono backup: %s", backup_path)
        return backup_path

    # ── Wewnętrzne ────────────────────────────────────────────────────────────

    def _ensure_open(self) -> zipfile.ZipFile:
        """Zwraca otwarty uchwyt ZIP albo rzuca :class:`EpubNotOpenError`."""
        if self._zip is None:
            raise EpubNotOpenError("EPUB nie jest otwarty — wywołaj open() lub użyj 'with'.")
        return self._zip

    def _reset_cache(self) -> None:
        """Czyści zcache'owaną ścieżkę OPF, manifest i spine."""
        self._opf_path = None
        self._manifest = None
        self._spine = None

    def _parse_opf(self) -> None:
        """Parsuje plik OPF i wypełnia cache manifestu oraz spine."""
        try:
            root = ET.fromstring(self.read_file(self.opf_path))
        except ET.ParseError as exc:
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
