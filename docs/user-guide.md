# Przewodnik użytkownika EpubForge

EpubForge to narzędzie do walidacji, naprawy i konwersji plików EPUB — dostępne
jako aplikacja graficzna (GUI), linia poleceń (CLI) i biblioteka Python.

---

## Instalacja

### Windows — bez Pythona
Pobierz z [Releases](https://github.com/chodzkos/epubforge/releases):

- **`epubforge.exe`** — portable, jeden plik, uruchamiasz bez instalacji.
- **`epubforge-setup.exe`** — instalator: skrót w menu Start, opcjonalnie na pulpicie,
  odinstalowanie przez „Dodaj/usuń programy".

### Z PyPI (Python 3.10+)
```bash
pip install epubforge
```

### Ze źródeł
```bash
git clone https://github.com/chodzkos/epubforge
cd epubforge
pip install -e ".[dev,gui]"
```

---

## Narzędzia zewnętrzne (opcjonalne)

Część funkcji korzysta z zewnętrznych programów — EpubForge wykrywa je automatycznie:

| Narzędzie | Do czego |
|---|---|
| **Pandoc** | konwersja TXT/MD/DOCX/HTML/ODT/RTF → EPUB |
| **Calibre** (`ebook-convert`) | konwersja (w tym PDF), eksport KFX/MOBI/AZW3 |
| **Calibre — wtyczka KFX Output** | zalecany silnik eksportu KFX |
| **Sigil**, **Calibre Editor/Viewer** | edycja/podgląd EPUB z poziomu zakładki Metadane |
| **Kindle Previewer 3** | eksperymentalny silnik KFX |
| **kindlegen** | wycofany silnik MOBI (zalecane Calibre) |
| **Java (Temurin JRE 17+)** + **EpubCheck 5.x** | walidacja EPUB (zakładka Walidacja / `epubforge check`) |

**EpubCheck.** Walidacja wymaga Javy (Temurin JRE 17+) oraz pliku `epubcheck.jar`
([EpubCheck 5.x z W3C](https://github.com/w3c/epubcheck/releases)). Rozpakuj jara do
`<katalog konfiguracji>/epubcheck/epubcheck.jar` albo wskaż go przyciskiem
**Wskaż epubcheck.jar…** w zakładce Walidacja (ścieżka zapisuje się w configu).

Status wykrytych narzędzi widać na dolnym pasku GUI.

---

## GUI

Uruchom `epubforge-gui` (lub plik `.exe`). Okno ma górny pasek (nazwa, przełącznik
motywu, „O programie") i zakładki robocze:

- **Metadane** — wybierz folder z EPUB-ami, kliknij plik, edytuj pola Dublin Core
  (tytuł, autorzy, język, wydawca, data, ISBN, tematy, opis) i zapisz (tworzy backup
  `.bak`). Przyciski Sigil / Calibre Editor / Viewer otwierają plik w zewnętrznym programie.
- **Konwerter** — dodaj pliki wejściowe, ustaw metadane i okładkę, wybierz silnik
  (Auto / Pandoc / Calibre) i folder wyjściowy, kliknij **Konwertuj**. PDF wymaga
  potwierdzenia (konwersja eksperymentalna). Formaty Kindle (MOBI/AZW3/AZW/PRC)
  wymuszają silnik Calibre; pliki zabezpieczone **DRM** są odrzucane ostrzeżeniem
  — EpubForge nie usuwa zabezpieczeń.
- **Fixer** — hyphenacja (język, metoda soft-hyphen/CSS) i normalizacja CSS
  (usuń kolory/fonty, reset, justify→lewo, margines). Sekcja **Preset CSS** dołącza
  gotowy szablon stylów (Dołącz/Zastąp), z możliwością **Importuj własny…** (plik
  `.css` trafia do katalogu presetów). Naprawa działa **w miejscu**.
- **Eksport Kindle** — wybierz format (KFX / MOBI / AZW3) i silnik, opcjonalnie napraw
  EPUB przed konwersją, wskaż folder wyjściowy.
- **Edytor** — otwórz EPUB, przeglądaj pliki w drzewie (Tekst/Style/Obrazy/Fonty/Inne),
  edytuj HTML/CSS z podświetlaniem i wyszukiwarką (Ctrl+F). Edycja jest domyślnie
  wyłączona — włącz **Tryb edycji**. Zapis pliku: Ctrl+S (XHTML/OPF jest walidowany);
  **Zapisz EPUB** utrwala zmiany na dysk (kopia `.bak`). Pliki nie-UTF-8 są tylko do odczytu.
  Przy otwartym `.css` panel **Inspektor CSS** pokazuje listę reguł i podgląd na żywo —
  edytujesz regułę, a „Zastosuj do arkusza" wpisuje ją z powrotem do pliku.
  Dla plików HTML/XHTML prawy panel ma przełącznik **Kod ⇄ Podgląd** (domyślnie Kod):
  podgląd renderuje przybliżony obraz silnikiem Qt (obrazki osadzone z EPUB) i
  odświeża się z niezapisanej treści. Pasek nad podglądem ma przyciski **Sigil /
  Calibre Editor** otwierające plik do pełnego podglądu w zewnętrznym programie.

  > ⚠️ **Podgląd HTML jest przybliżony** — silnik `QTextDocument` nie wykonuje
  > JavaScriptu ani pełnego CSS i nie odwzorowuje układu czytnika. Do wiernego
  > podglądu użyj przycisków Sigil/Calibre Editor.

  > ⚠️ **Podgląd jest przybliżony.** Renderuje go silnik rich text Qt, który obsługuje
  > tylko podzbiór CSS (m.in. `font-*`, `color`, `text-align`, `margin/padding`,
  > `line-height`). Właściwości spoza tego zakresu (np. `letter-spacing`, `hyphens`,
  > `float`) są wypisywane jako „nieobsługiwane w podglądzie" i **nie** wpływają na obraz.
  > Docelowy czytnik może renderować inaczej — traktuj podgląd jako orientacyjny.
- **Walidacja** — dodaj pliki EPUB, kliknij **Sprawdź zaznaczony**: EpubForge uruchamia
  EpubCheck i pokazuje raport (poziom, kod, plik:linia, komunikat) z paskiem podsumowania
  i filtrami błędy/ostrzeżenia/informacje. **Dwuklik** błędu z lokalizacją otwiera plik
  w zakładce Edytor na właściwej linii. **Eksport…** zapisuje raport jako JSON lub HTML.
  Gdy brak Javy/`epubcheck.jar`, zakładka pokazuje instrukcję i przycisk **Wskaż epubcheck.jar…**.
- **Spis treści** — wskaż EPUB, a EpubForge wczyta jego spis (nav.xhtml lub toc.ncx).
  **Generuj** buduje spis z nagłówków `h1..hN` (poziom ustawia **Poziom:**), **Napraw**
  usuwa martwe wpisy (z potwierdzeniem). Drzewo edytujesz: dwuklik tytułu zmienia tekst,
  przyciski **Dodaj/Usuń/⬆⬇** (rodzeństwo) i **⬅➡** (poziom) oraz **drag&drop** zmieniają
  strukturę. Martwe wpisy są na czerwono z tooltipem. **Zapisz do EPUB** zapisuje nav + ncx
  (kopia `.bak`). Niezapisane zmiany są pilnowane przy zmianie pliku i zamknięciu.

- **Statystyki** — wskaż EPUB i kliknij **Oblicz**: liczba słów, szac. stron, czas
  czytania, język i najczęstsze słowa oraz tabela rozdziałów. **Eksport HTML…**
  zapisuje samowystarczalny raport (do druku Ctrl+P → PDF), **Otwórz raport** pokazuje
  go w przeglądarce. Wykrywanie języka wymaga `pip install epubforge[stats]` — bez
  tego język pochodzi z metadanych EPUB-a.

**Motyw:** górny pasek → przełącznik **Automatyczny / Jasny / Ciemny** (auto podąża za
systemem). Na Windows zmienia się też kolor paska tytułu.

> Puste pole „folder wyjściowy" oznacza zapis obok pliku źródłowego.
> Najechanie na dowolną kontrolkę pokazuje podpowiedź (tooltip).

---

## CLI

```bash
# Konwersja do EPUB
epubforge convert book.docx book.epub
epubforge convert input.pdf output.epub --engine calibre

# Walidacja EpubCheck (wymaga Javy + epubcheck.jar)
epubforge check book.epub                          # raport; exit 0=OK, 1=błędy, 2=brak narzędzi
epubforge check book.epub --json report.json --min-severity warning

# Spis treści (podgląd / generowanie / naprawa)
epubforge toc book.epub --show
epubforge toc book.epub --generate --max-level 3 --output out.epub
epubforge toc book.epub --repair --dry-run

# Naprawa EPUB (hyphenacja + CSS)
epubforge fix book.epub --remove-colors --replace-justify
epubforge hyphenate book.epub --lang pl --method soft-hyphen --skip-headers

# Presety CSS — gotowe szablony stylów
epubforge presets list                            # lista dostępnych presetów
epubforge fix book.epub --preset reader-friendly  # dołącz preset do EPUB
epubforge fix book.epub --preset dark-oled --preset-mode replace  # zastąp arkusze

# Metadane (podgląd i edycja, w tym seria/tom)
epubforge meta book.epub
epubforge meta book.epub --title "Krew elfów" --author "Sapkowski, Andrzej" \
    --series "Wiedźmin" --series-index 3

# Statystyki książki (+ raport HTML)
epubforge stats book.epub --report stats.html --top 50

# Eksport Kindle
epubforge kfx book.epub --engine calibre
epubforge mobi book.epub --format azw3 --engine calibre
```

Każda komenda ma `--help` z pełną listą opcji.

---

## Najczęstsze pytania

**Build na Windows nie startuje / błąd zależności.** Projekt wymaga Pythona 3.10+.
`build\build.bat` sam wybiera `py -3.12/3.11/3.10`; jeśli żadnej nie ma — zainstaluj
Python 3.12 z python.org.

**Motyw aplikacji.** Wybierasz go przyciskiem **Motyw** (Automatyczny / Jasny /
Ciemny). W trybie ciemnym okna Otwórz/Zapisz są również ciemne (dialogi Qt); w
trybie jasnym używane są natywne dialogi systemu.

**Soft-hyphen psuje wyszukiwarkę na czytniku.** Tak — to świadomy kompromis. Jeśli to
przeszkadza, użyj metody CSS (`hyphens: auto`), choć jest słabiej wspierana na Kindle.
