"""Wczesna, idempotentna inicjalizacja Qt WebEngine (fundament Prompt 1).

Qt wymaga, aby **rejestracja własnego schematu URL nastąpiła zanim powstaną
jakiekolwiek klasy WebEngine** (a najlepiej przed ``QApplication``). Ten moduł
jest jedynym punktem tej rejestracji; woła się go raz w ``main()`` GUI, zanim
utworzone zostaną widgety WebEngine.

Zasady (Prompt 1 §3):

* rejestracja jest **idempotentna** i wykonywana **najwyżej raz na proces**;
* sam import ``epubforge`` / core / CLI **nie może** tego uruchamiać — dlatego
  woła się to jawnie w ``main()``, a nie na poziomie importu;
* **nie ustawiamy bezwarunkowo** ``Qt.AA_ShareOpenGLContexts`` (patrz niżej);
* brak WebEngine to no-op — funkcja nigdy nie może wywrócić startu aplikacji.

Decyzja o ``AA_ShareOpenGLContexts``: w torze **Widgets** (``QWebEngineView``)
bieżąca dokumentacja Qt 6.8 nie wymaga tego atrybutu — jest on potrzebny przy
współdzieleniu kontekstu z ``QOpenGLWidget``/``QtQuick``, czego tu nie robimy.
Dlatego atrybutu **nie** ustawiamy; gdyby przyszły test techniczny wykazał
regresję renderowania, decyzję należy udokumentować i dopiero wtedy włączyć.

Kontrakt samego schematu (flagi ``SecureScheme`` itd.) należy do Prompt 2 —
tutaj rejestrujemy nazwę wcześnie, a właściwy handler instaluje profil sesji.
"""

from __future__ import annotations

import logging

from epubforge.gui.preview.availability import probe_webengine

logger = logging.getLogger(__name__)

#: Nazwa własnego, bezpiecznego schematu podglądu (origin per sesja — Prompt 2).
EPUB_PREVIEW_SCHEME = "epub-preview"

# Idempotencja: rejestrujemy najwyżej raz na proces (Qt i tak by ostrzegło).
_registered = False


def preview_scheme_registered() -> bool:
    """Czy własny schemat został bezpiecznie zarejestrowany przed QApplication."""
    return _registered

def preinit_webengine() -> bool:
    """Rejestruje schemat ``epub-preview`` wcześnie, jeśli WebEngine jest dostępny.

    Bezpieczne do wielokrotnego wołania (idempotentne). Zwraca ``True``, gdy po
    wyjściu schemat jest zarejestrowany; ``False``, gdy WebEngine niedostępny lub
    rejestracja się nie powiodła (GUI działa dalej na lekkim backendzie).
    """
    global _registered
    if _registered:
        return True
    if not probe_webengine().available:
        return False

    # Import Chromium bywa awaryjny — nie wywracamy startu, tylko odpuszczamy
    # dokładny podgląd. Import + rejestracja są tu, by mypy widział realne typy
    # QtWebEngineCore (a nie luźne ``type``).
    try:
        from PySide6.QtWebEngineCore import QWebEngineUrlScheme

        name = EPUB_PREVIEW_SCHEME.encode("ascii")
        # Pusta nazwa = schemat jeszcze niezarejestrowany (schemeByName zwraca
        # wtedy domyślny wpis). Niepusta = już jest — nie rejestrujemy ponownie.
        if QWebEngineUrlScheme.schemeByName(name).name().isEmpty():
            scheme = QWebEngineUrlScheme(name)
            scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
            # Pełny zestaw flag (SecureScheme bez LocalAccessAllowed /
            # ServiceWorkersAllowed / CorsEnabled) doprecyzuje Prompt 2 — tu
            # ustawiamy host + bezpieczny origin, spójne z późniejszym zaostrzeniem.
            scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
            QWebEngineUrlScheme.registerScheme(scheme)
    except Exception as exc:
        logger.warning("Pre-init WebEngine pominięty: %s", exc)
        return False

    _registered = True
    logger.debug("Zarejestrowano schemat podglądu %s", EPUB_PREVIEW_SCHEME)
    return True
