"""Lekki detektor zabezpieczeń DRM w plikach Kindle (MOBI/AZW/AZW3/PRC).

Czyta wyłącznie nagłówek PalmDB i nagłówek PalmDOC z rekordu 0 — nie dekoduje
treści ani nie usuwa zabezpieczeń. Służy do **uprzejmego** odrzucenia konwersji
plików DRM, zanim odpalimy Calibre.

Układ nagłówków (big-endian, ``>``):

* **Nagłówek PalmDB** (78 bajtów):
  - offset 0..31  — nazwa bazy (32 bajty),
  - …
  - offset 76     — liczba rekordów (``>H``),
  - offset 78     — lista rekordów: po 8 bajtów na rekord
    (``>I`` offset danych rekordu + 4 bajty atrybuty/uid).
* **Rekord 0** (nagłówek PalmDOC, od offsetu rekordu 0):
  - offset 12     — typ szyfrowania (``>H``): ``0`` brak DRM, ``1``/``2`` DRM,
  - offset 16     — magic ``MOBI`` (potwierdza, że to nagłówek MOBI).

Plik zbyt krótki albo bez magicu ``MOBI`` → :data:`False` (niech wypowie się Calibre).
"""

from __future__ import annotations

import struct
from pathlib import Path

# Offsety w nagłówku (zob. docstring modułu).
_NUM_RECORDS_OFFSET = 76
_RECORD_LIST_OFFSET = 78
_PALMDB_HEADER_MIN = 78
_REC0_ENCRYPTION_OFFSET = 12
_REC0_MAGIC_OFFSET = 16
_MOBI_MAGIC = b"MOBI"
_DRM_ENCRYPTION_TYPES = {1, 2}


def has_kindle_drm(path: Path) -> bool:
    """Sprawdza, czy plik Kindle jest zabezpieczony DRM (typ szyfrowania 1/2).

    Args:
        path: ścieżka do pliku ``.mobi``/``.azw``/``.azw3``/``.prc``.

    Returns:
        ``True`` tylko gdy nagłówek MOBI jednoznacznie wskazuje DRM. Przy zbyt
        krótkim pliku, braku magicu ``MOBI`` lub błędzie odczytu — ``False``
        (decyzję pozostawiamy Calibre).
    """
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if len(data) < _PALMDB_HEADER_MIN:
        return False

    (num_records,) = struct.unpack(">H", data[_NUM_RECORDS_OFFSET:_PALMDB_HEADER_MIN])
    if num_records < 1 or len(data) < _RECORD_LIST_OFFSET + 8:
        return False

    # Pierwszy wpis listy rekordów: offset danych rekordu 0 (>I).
    (record0_offset,) = struct.unpack(">I", data[_RECORD_LIST_OFFSET : _RECORD_LIST_OFFSET + 4])
    magic_end = record0_offset + _REC0_MAGIC_OFFSET + len(_MOBI_MAGIC)
    if len(data) < magic_end:
        return False
    if data[record0_offset + _REC0_MAGIC_OFFSET : magic_end] != _MOBI_MAGIC:
        return False

    enc_start = record0_offset + _REC0_ENCRYPTION_OFFSET
    (encryption_type,) = struct.unpack(">H", data[enc_start : enc_start + 2])
    return encryption_type in _DRM_ENCRYPTION_TYPES
