# Fixer (naprawa + CSS)

Naprawa i ujednolicenie EPUB pod czytniki — wsadowo dla wielu plików. Naprawa
działa **w miejscu** (kopia `.bak`).

## Dzielenie wyrazów (hyphenacja)

- **Język słownika** (pyphen), np. `pl`, `en_US`
- **Metoda** — uwaga: *soft-hyphen* może psuć słownik i wyszukiwarkę na Kindle
- **Pomiń nagłówki** — nie dziel wyrazów w nagłówkach (h1-h3)

## Typografia polska

- **Cudzysłowy** — proste cudzysłowy → pary typograficzne wg języka (pl/en/de)
- **Pauzy** — dywizy w dialogach i wtrąceniach → pauza `—`
- **Wielokropek** — trzy kropki → `…`
- **Twarde spacje** — po polskich sierotach (a/i/o/u/w/z) i opcjonalnie przy liczbach

## CSS Fixer

- **Usuń kolory** — usuwa `color`/`background` (czytnik narzuca własne)
- **Usuń fonty** — zdejmuje narzucone kroje (czytelnik wybiera font)
- **Dodaj reset CSS** — delikatny reset marginesów/paddingu dla spójności
- **Zamień justowanie na lewe** — `justify` → `left` (mniej dużych odstępów)
- **Wyłącz hyphenację nagłówków** — reguła CSS blokująca dzielenie w nagłówkach
- **Margines książki** — wstrzykuje margines strony w pikselach (0-120)

**Przytnij fonty do użytych znaków** (subsetting) — przycina osadzone fonty do znaków
faktycznie użytych w treści (zwykle o 70-90% rozmiaru fontu). Wymaga extra `[fonts]`
(fonttools); zwróć uwagę na licencje fontów. Nie mylić z **Usuń fonty** powyżej.

## Optymalizacja obrazów

- **Kompresja JPEG/PNG** — mniejszy plik bez zmiany formatu (bez WebP); okładka pomijana
- **Maks. dłuższy bok (px)** — skalowanie w dół (0 = bez skalowania)
- **Jakość JPEG** (1-95) oraz **skala szarości (e-ink)** pod czytniki e-ink
- EXIF/ICC usuwane; zapis tylko, gdy wynik jest mniejszy (wymaga extra `[images]`)

## Uaktualnij do EPUB 3

Konwersja EPUB 2 → 3: `nav.xhtml` z NCX, `dcterms:modified`, landmarks z guide. Na
wejściu EPUB 3 = brak zmian (no-op). Przycisk niezależny od „Napraw", z potwierdzeniem.

## Preset CSS i receptury

- **Preset CSS** — dołącza (Dołącz/Zastąp) wybrany arkusz stylów do EPUB podczas
  naprawy. **Importuj własny…** kopiuje plik `.css` do katalogu presetów.
- **Uruchom recepturę…** — zapisany pipeline fixerów na jednym otwartym EPUB-ie (jeden
  zapis): wbudowane `kindle-pl` / `czytnik-epub`, a własne receptury TOML w katalogu
  konfiguracji przykrywają wbudowane po nazwie.

> Odpowiedniki CLI: `epubforge fix`, `hyphenate`, `typo`, `upgrade`, `run`, `presets`
> (zakładka **Wiersz poleceń**). Pełny opis: `docs/user-guide.md`.
