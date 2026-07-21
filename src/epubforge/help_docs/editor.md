# Edytor EPUB

Szybki podgląd i edycja plików **wewnątrz** EPUB (quick-fix, nie pełny Sigil). Edycja
jest domyślnie wyłączona — włącz **Tryb edycji**. Pliki nie-UTF-8 są tylko do odczytu.

- **Drzewo plików** — XHTML, CSS, obrazy i fonty z archiwum EPUB
- **Podgląd HTML na żywo** + przełącznik **Kod ⇄ Podgląd** (domyślnie Kod); podgląd
  renderuje przybliżony obraz silnikiem Qt (obrazki osadzone z EPUB)
- **Inspektor CSS / Arkusz** — przy otwartym `.css` panel pokazuje listę reguł,
  podgląd na żywo i zapisuje dokładny span jako jeden krok Undo
- **Inspektor CSS / Element** — w dokładnym podglądzie kliknij element, aby zobaczyć
  breadcrumb DOM, box model, computed style, font, style inline, dziedziczenie oraz
  zwycięskie, przegrane i nieaktywne deklaracje. Możesz filtrować właściwości,
  przejść do właściwej reguły i podświetlić wszystkie dopasowania
- Edycja reguły elementu działa najpierw jako tymczasowa warstwa podglądu. Przycisk
  **Zastosuj** sprawdza revision źródła; konflikt nigdy nie jest nadpisywany cicho
- **Szukaj i zamień** (Ctrl+Shift+F) — w bieżącym pliku lub całym EPUB, literał lub
  **regex** (wielkość liter, całe słowa); wyniki zgrupowane po pliku, dwuklik ustawia
  kursor na trafieniu, a „Zamień wszystkie" raportuje liczbę podmian
- **Zapisz plik** (Ctrl+S; XHTML/OPF walidowany) i **Zapisz EPUB** — utrwala zmiany na
  dysk (kopia `.bak`)

Pasek nad podglądem ma przyciski **Sigil / Calibre Editor** otwierające plik do pełnego
podglądu w zewnętrznym programie (jeśli wykryty).

> ⚠️ Szybki backend nie oblicza pełnego CSS. Tryb Element wymaga dokładnego backendu
> WebEngine. Analiza pseudoelementów, animacji, `@layer`, `@container`, `@scope`,
> złożonych `var()` i fontu dla pojedynczego glifu ma jawnie pokazane ograniczenia.
> Do porównania z konkretnym czytnikiem użyj Sigil / Calibre Editor.

Pełny opis wszystkich funkcji: `docs/user-guide.md`.
