# Statystyki

Liczby książki — przydatne przy korekcie i opisie. Kliknij **Oblicz**:

- Liczba **słów** i **znaków**
- Szacowana liczba **stron** i **czas czytania**
- **Najczęstsze słowa** (z listą stop-słów pl/en/de)
- **Rozdziały** — tytuł i liczba słów

**Eksport HTML…** zapisuje samowystarczalny raport (do druku Ctrl+P → PDF),
**Otwórz raport** pokazuje go w przeglądarce.

Wykrywanie języka wymaga extra `[stats]` — bez niego język pochodzi z metadanych
EPUB-a.

Szacowana liczba stron wynika domyślnie z przelicznika 250 słów na stronę. Nie
oznacza liczby stron wydania papierowego ani technicznych stron podglądu w
symulatorze. Ten sam wynik można wstawić przyciskiem **Oblicz** w polu **Liczba
stron** zakładki Metadane, a następnie — tylko dla EPUB 3 — zapisać jako
`schema:numberOfPages`.

> Odpowiednik CLI: `epubforge stats --report stats.html` (zakładka **Wiersz poleceń**).
> Pełny opis: `docs/user-guide.md`.
