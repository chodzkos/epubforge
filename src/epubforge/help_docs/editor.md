# Edytor EPUB

Szybki podgląd i edycja plików **wewnątrz** EPUB (quick-fix, nie pełny Sigil). Edycja
jest domyślnie wyłączona — włącz **Tryb edycji**. Pliki nie-UTF-8 są tylko do odczytu.

- **Drzewo plików** — XHTML, CSS, obrazy i fonty z archiwum EPUB
- **Podgląd HTML na żywo** + przełącznik **Kod ⇄ Podgląd** (domyślnie Kod); podgląd
  renderuje przybliżony obraz silnikiem Qt (obrazki osadzone z EPUB)
- **Inspektor CSS** — przy otwartym `.css` panel pokazuje listę reguł i podgląd na
  żywo; „Zastosuj do arkusza" wpisuje regułę z powrotem do pliku
- **Szukaj i zamień** (Ctrl+Shift+F) — w bieżącym pliku lub całym EPUB, literał lub
  **regex** (wielkość liter, całe słowa); wyniki zgrupowane po pliku, dwuklik ustawia
  kursor na trafieniu, a „Zamień wszystkie" raportuje liczbę podmian
- **Zapisz plik** (Ctrl+S; XHTML/OPF walidowany) i **Zapisz EPUB** — utrwala zmiany na
  dysk (kopia `.bak`)

Pasek nad podglądem ma przyciski **Sigil / Calibre Editor** otwierające plik do pełnego
podglądu w zewnętrznym programie (jeśli wykryty).

> ⚠️ **Podgląd HTML jest przybliżony** — silnik rich-text Qt obsługuje tylko podzbiór
> CSS i nie odwzorowuje układu czytnika. Do wiernego podglądu użyj Sigil / Calibre
> Editor. Pełny opis: `docs/user-guide.md`.
