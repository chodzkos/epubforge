"""Bezpieczny model niezaufanego archiwum EPUB (ZIP) — walidacja przed odczytem.

EPUB to archiwum dostarczone przez użytkownika. Naiwny odczyt/zapis otwiera projekt
na ataki wyczerpania zasobów (bomby ZIP, ekstremalny współczynnik kompresji, miliony
wpisów) oraz na niekanoniczne nazwy (traversal ``..``, ścieżki absolutne, backslash,
NUL). Ten moduł centralizuje **walidację metadanych nagłówka ZIP** (bez dekompresji)
oraz **strumieniowe kopiowanie** wpisów, tak by:

* każde odrzucenie następowało PRZED kosztowną dekompresją (patrzymy tylko na
  ``file_size``/``compress_size``/``flag_bits``/nazwę z centralnego katalogu ZIP);
* pamięć szczytowa zapisu nie rosła z rozmiarem największego niezmienionego wpisu
  (kopiujemy ``zin.open`` → ``zout.open`` przez :func:`shutil.copyfileobj` z
  ograniczonym buforem, zamiast wczytywać cały wpis do RAM).

Limity są konfigurowalne (:class:`ArchiveLimits`) i domyślnie na tyle wysokie, by
typowe duże EPUB-y (grafika/audio, 50-150 MB) działały — można je świadomie podnieść
przez ``Epub(path, limits=ArchiveLimits(...))``.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass

from epubforge.core.exceptions import ResourceLimitError

# Flaga „traversal” w nagłówku ZIP: bit 0 ``flag_bits`` oznacza wpis zaszyfrowany.
_ENCRYPTED_FLAG = 0x1


@dataclass(frozen=True)
class ArchiveLimits:
    """Konfigurowalne limity bezpieczeństwa dla niezaufanego archiwum EPUB.

    Wszystkie rozmiary w bajtach. Domyślne wartości są celowo wysokie — mają nie
    blokować typowych dużych EPUB-ów (grafika/audio), a jedynie odciąć jawne
    nadużycia. Kto ufa źródłu, może je świadomie podnieść.

    Attributes:
        max_entries: maksymalna liczba wpisów w archiwum.
        max_total_uncompressed: maksymalna suma rozmiarów nieskompresowanych.
        max_entry_size: maksymalny rozmiar (nieskompresowany) pojedynczego wpisu.
        max_text_size: maksymalny rozmiar wpisu odczytywanego do parsowania
            XML/tekstu (container.xml, OPF, XHTML) — tnie bomby „dużego XML-a”.
        max_compression_ratio: maksymalny współczynnik ``file_size/compress_size``
            (bomba ZIP ma ekstremalne ratio; typowy tekst ~10-15x).
        max_operations: budżet operacji (liczba wpisów przetworzonych przy
            walidacji/zapisie) — backstop na patologiczne archiwa.
        ratio_check_min_size: poniżej tego rozmiaru nieskompresowanego nie liczymy
            współczynnika (małe wpisy nie są zagrożeniem, a dają fałszywe alarmy).
        copy_buffer_size: rozmiar bufora strumieniowego kopiowania wpisów.
    """

    max_entries: int = 50_000
    max_total_uncompressed: int = 4 * 1024**3  # 4 GiB
    max_entry_size: int = 512 * 1024**2  # 512 MiB
    max_text_size: int = 64 * 1024**2  # 64 MiB
    max_compression_ratio: float = 200.0
    max_operations: int = 500_000
    ratio_check_min_size: int = 64 * 1024  # 64 KiB
    copy_buffer_size: int = 1024 * 1024  # 1 MiB


# Domyślny, współdzielony zestaw limitów (bezpieczny dla typowych EPUB-ów).
DEFAULT_LIMITS = ArchiveLimits()


def _has_drive(name: str) -> bool:
    """Czy nazwa zaczyna się od litery dysku (np. ``C:``) — ścieżka absolutna Windows."""
    return len(name) >= 2 and name[1] == ":" and name[0].isalpha()


def _validate_name(name: str, seen: set[str]) -> None:
    """Odrzuca niekanoniczne/niebezpieczne nazwy wpisów (duplikaty, traversal, NUL…).

    Raises:
        ResourceLimitError: gdy nazwa jest pusta, zawiera NUL/backslash, jest
            ścieżką absolutną, ma segment ``.``/``..`` albo się powtarza.
    """
    if not name:
        raise ResourceLimitError("Archiwum EPUB zawiera wpis o pustej nazwie.")
    if "\x00" in name:
        raise ResourceLimitError("Nazwa wpisu w archiwum EPUB zawiera znak NUL.")
    if "\\" in name:
        raise ResourceLimitError(f"Nazwa wpisu z backslashem (niedozwolona): {name!r}.")
    if name.startswith("/") or _has_drive(name):
        raise ResourceLimitError(f"Ścieżka absolutna wpisu w archiwum EPUB: {name!r}.")
    segments = name.split("/")
    for index, segment in enumerate(segments):
        if segment == "..":
            raise ResourceLimitError(f"Wpis wychodzi poza archiwum (segment '..'): {name!r}.")
        if segment == ".":
            raise ResourceLimitError(f"Niekanoniczna nazwa wpisu (segment '.'): {name!r}.")
        # Pusty segment dozwolony tylko jako końcowy (wpis-katalog ``dir/``).
        if segment == "" and index != len(segments) - 1:
            raise ResourceLimitError(f"Niekanoniczna nazwa wpisu (pusty segment): {name!r}.")
    if name in seen:
        raise ResourceLimitError(f"Zdublowana nazwa wpisu w archiwum EPUB: {name!r}.")
    seen.add(name)


def _validate_entry_budgets(info: zipfile.ZipInfo, limits: ArchiveLimits) -> None:
    """Sprawdza limity pojedynczego wpisu (rozmiar, ratio, szyfrowanie) — bez dekompresji.

    Raises:
        ResourceLimitError: przy zaszyfrowanym wpisie, przekroczeniu rozmiaru
            pojedynczego wpisu lub zbyt wysokim współczynniku kompresji.
    """
    if info.flag_bits & _ENCRYPTED_FLAG:
        raise ResourceLimitError(f"Zaszyfrowany wpis w archiwum EPUB: {info.filename!r}.")
    if info.file_size > limits.max_entry_size:
        raise ResourceLimitError(
            f"Wpis {info.filename!r} przekracza limit rozmiaru "
            f"({info.file_size} > {limits.max_entry_size} B)."
        )
    # Współczynnik kompresji liczymy dopiero powyżej progu (małe wpisy nie grożą DoS).
    if info.file_size > limits.ratio_check_min_size and info.compress_size > 0:
        ratio = info.file_size / info.compress_size
        if ratio > limits.max_compression_ratio:
            raise ResourceLimitError(
                f"Podejrzanie wysoki współczynnik kompresji wpisu {info.filename!r} "
                f"({ratio:.0f}x > {limits.max_compression_ratio:.0f}x) — możliwa bomba ZIP."
            )


def validate_archive(zf: zipfile.ZipFile, limits: ArchiveLimits = DEFAULT_LIMITS) -> None:
    """Waliduje niezaufane archiwum EPUB na podstawie metadanych (bez dekompresji).

    Wywoływana PRZED jakimkolwiek odczytem treści (w :meth:`Epub.open`), więc każde
    odrzucenie następuje zanim cokolwiek zostanie zdekompresowane.

    Args:
        zf: otwarte archiwum ZIP.
        limits: zestaw limitów (domyślnie :data:`DEFAULT_LIMITS`).

    Raises:
        ResourceLimitError: przy przekroczeniu dowolnego limitu lub niekanonicznej
            nazwie wpisu.
    """
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ResourceLimitError(
            f"Archiwum EPUB ma za dużo wpisów ({len(infos)} > {limits.max_entries})."
        )
    seen: set[str] = set()
    total = 0
    for operations, info in enumerate(infos, start=1):
        if operations > limits.max_operations:
            raise ResourceLimitError("Przekroczono budżet operacji walidacji archiwum EPUB.")
        _validate_name(info.filename, seen)
        _validate_entry_budgets(info, limits)
        total += info.file_size
        if total > limits.max_total_uncompressed:
            raise ResourceLimitError(
                f"Suma rozmiarów nieskompresowanych przekracza limit "
                f"({total} > {limits.max_total_uncompressed} B)."
            )


def _dest_info(item: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """Świeży :class:`ZipInfo` dla wpisu docelowego, przenoszący metadane źródła.

    Zachowuje ``compress_type`` (wpisy STORED, np. obrazy, nie są rekompresowane),
    ``date_time`` i atrybuty — bez współdzielenia obiektu ze źródłem.
    """
    dest = zipfile.ZipInfo(item.filename, date_time=item.date_time)
    dest.compress_type = item.compress_type
    dest.external_attr = item.external_attr
    dest.internal_attr = item.internal_attr
    dest.create_system = item.create_system
    return dest


def copy_entry_streamed(
    zin: zipfile.ZipFile,
    zout: zipfile.ZipFile,
    item: zipfile.ZipInfo,
    *,
    buffer_size: int,
) -> None:
    """Kopiuje wpis ze źródła do wyjścia **strumieniowo** (bufor ``buffer_size``).

    Pamięć szczytowa nie zależy od rozmiaru wpisu — czytamy i zapisujemy w kawałkach
    (``zin.open`` → ``zout.open`` + :func:`shutil.copyfileobj`), zamiast wczytywać
    cały wpis do RAM (``zin.read``). ``compress_type`` źródła jest zachowany.
    """
    with zin.open(item) as source, zout.open(_dest_info(item), "w") as dest:
        shutil.copyfileobj(source, dest, buffer_size)
