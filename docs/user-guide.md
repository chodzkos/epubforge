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
| **pdf2md** | zalecany silnik PDF → EPUB (PDF → Markdown → Pandoc); handoff „Otwórz w pdf2md" |
| **Calibre** (`ebook-convert`) | konwersja (w tym PDF — fallback), eksport KFX/MOBI/AZW3 |
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
  Przycisk **Pobierz metadane…** dociąga dane po ISBN (Biblioteka Narodowa → LubimyCzytac →
  Open Library → Google Books). Uwaga: e-booki mają **własny ISBN** wydania elektronicznego,
  którego katalog BN (głównie wydania papierowe) często nie ma — wtedy aplikacja
  automatycznie **dopasowuje książkę po tytule** i wyraźnie to zaznacza w komunikacie
  („dopasowanie po tytule — ISBN e-wydania nieobecny w BN"). Uzupełniane są tylko metadane
  bibliograficzne; **ISBN pliku pozostaje niezmieniony**. Zaznacz pola do nadpisania i OK.
- **Konwerter** — dodaj pliki wejściowe, ustaw metadane i okładkę, wybierz silnik
  (Auto / Pandoc / Calibre / pdf2md) i folder wyjściowy, kliknij **Konwertuj**. Przy
  dodaniu **PDF** — gdy wykryto pdf2md — pojawia się wybór silnika: **pdf2md (zalecany)**
  vs **Calibre (eksperymentalny)**; wybór jest zapamiętywany. Bez pdf2md tryb Auto wraca
  do Calibre (konwersja eksperymentalna). Gdy wykryto **pdf2md-gui**, przycisk
  **Otwórz w pdf2md** otwiera wybrany PDF w aplikacji pdf2md. Formaty Kindle
  (MOBI/AZW3/AZW/PRC) wymuszają silnik Calibre; pliki zabezpieczone **DRM** są odrzucane
  ostrzeżeniem — EpubForge nie usuwa zabezpieczeń. Podczas pracy pasek postępu pokazuje
  procent z Calibre, a przycisk **Anuluj** przerywa konwersję (kończy proces silnika).
- **Fixer** — hyphenacja (język, metoda soft-hyphen/CSS), **Typografia**, **Obrazy**
  i normalizacja CSS (usuń kolory/fonty, reset, justify→lewo, margines). Sekcja
  **Typografia** poprawia mikrotypografię tekstu: cudzysłowy typograficzne dobierane
  językiem (dropdown pl/en/de), pauzy w dialogach i wtrąceniach, wielokropek `…` oraz
  twarde spacje po polskich sierotach (a/i/o/u/w/z); opcjonalnie twarde spacje przy
  liczbach z jednostką. Sekcja **Obrazy** odchudza EPUB pod e-ink: skalowanie do
  zadanego dłuższego boku, rekompresja JPEG/PNG, skala szarości i pominięcie okładki;
  w logu pojawia się „zaoszczędzono X MB (-Y%)" (wymaga `pip install epubforge[images]`).
  W sekcji CSS opcja **Przytnij fonty do użytych znaków** wykonuje subsetting fontów
  (zwykle −70…−90% rozmiaru fontu), zachowując polskie znaki, interpunkcję typograficzną
  i efekty hyphenacji; zawsze pomija fonty z `@font-face unicode-range`, a pliki WOFF2
  wymagają `brotli`. **Uwaga:** część licencji fontów zabrania modyfikacji — sprawdź
  licencję (ostrzeżenie pojawia się po zaznaczeniu opcji). Wymaga `pip install epubforge[fonts]`.
  Sekcja **Preset CSS** dołącza gotowy szablon stylów (Dołącz/Zastąp), z możliwością
  **Importuj własny…** (plik `.css` trafia do katalogu presetów). Naprawa działa **w miejscu**.
  Sekcja **Uaktualnij do EPUB 3** (przycisk niezależny od „Napraw", z potwierdzeniem)
  modernizuje pakiet: tworzy `nav.xhtml` ze spisu NCX, przenosi `guide` do landmarks,
  dodaje `dcterms:modified` i porządkuje daty/identyfikator. Dokumentów treści nie rusza;
  NCX domyślnie zostaje (opcja „Usuń NCX"). Raport transformacji trafia do logu.
- **Eksport Kindle** — wybierz format (KFX / MOBI / AZW3) i silnik, opcjonalnie napraw
  EPUB przed konwersją, wskaż folder wyjściowy. Pasek postępu i przycisk **Anuluj**
  działają tak samo jak w Konwerterze (anulowanie kończy proces silnika).
- **Edytor** — otwórz EPUB, przeglądaj pliki w drzewie (Tekst/Style/Obrazy/Fonty/Inne),
  edytuj HTML/CSS z podświetlaniem i wyszukiwarką (Ctrl+F). Edycja jest domyślnie
  wyłączona — włącz **Tryb edycji**. Zapis pliku: Ctrl+S (XHTML/OPF jest walidowany);
  **Zapisz EPUB** utrwala zmiany na dysk (kopia `.bak`). Pliki nie-UTF-8 są tylko do odczytu.
  Przy otwartym `.css` tryb **Inspektor CSS / Arkusz** pokazuje listę reguł i
  podgląd na żywo; „Zastosuj do arkusza" podmienia dokładny span jako jeden krok
  Undo. W dokładnym podglądzie tryb **Element** wyjaśnia kaskadę klikniętego elementu:
  computed style, box model, inline, dziedziczenie, font, aktywne `@media`,
  specyficzność, `!important`, kolejność i źródło reguły.
  Edycja elementu najpierw działa w technicznej warstwie preview. **Zastosuj**
  sprawdza revision; konflikt nie nadpisuje nowszej treści.
  Skrót **Ctrl+Shift+F** otwiera panel **Szukaj/Zamień** (regex, wielkość liter,
  całe słowa; zakres: bieżący plik / cały EPUB). Wyniki są zgrupowane po pliku —
  dwuklik otwiera plik i ustawia kursor na trafieniu. „Zamień wszystkie" zapisuje
  zmiany do bufora (utrwalasz je przyciskiem **Zapisz EPUB**); pliki nie-UTF-8 są
  przy zamianie pomijane. Duże książki przeszukuje wątek roboczy (z **Anuluj**).
  Dla plików HTML/XHTML prawy panel ma przełącznik **Kod ⇄ Podgląd** (domyślnie Kod):
  backend Dokładny renderuje zasoby publikacji przez WebEngine, a Szybki pozostaje
  fallbackiem `QTextDocument`. Oba odświeżają się z niezapisanej treści.
  Dokładny podgląd zawiera neutralne profile **e-ink mały/duży**, **telefon pionowy**
  i **tablet pionowy/poziomy** oraz własny viewport. Dla reflowable można wybrać
  przewijanie albo CSS columns ze wskaźnikiem „strona podglądu”; fixed-layout jest
  wykrywany z metadanych rendition i viewportu, skalowany jako cała strona i nie
  otrzymuje columns ani wymuszonej typografii. Ustawienia czytelnika są osobną,
  odwracalną warstwą: rozmiar i interlinia, marginesy, font/fallback, kolory,
  wyłączenie CSS wydawcy lub fontów osadzonych. Można zestawić dwa profile obok
  siebie, wyeksportować sam viewport i uruchomić diagnostykę overflow, szerokości,
  obrazów, pozycjonowania, fontów, kontrastu, `alt` i hierarchii nagłówków.

  > ⚠️ **Szybki podgląd jest przybliżony.** Renderuje go silnik rich text Qt, który obsługuje
  > tylko podzbiór CSS (m.in. `font-*`, `color`, `text-align`, `margin/padding`,
  > `line-height`). Właściwości spoza tego zakresu (np. `letter-spacing`, `hyphens`,
  > `float`) są wypisywane jako „nieobsługiwane w podglądzie" i **nie** wpływają na obraz.
  > Docelowy czytnik może renderować inaczej — traktuj podgląd jako orientacyjny.
- **Walidacja** — dodaj pliki EPUB, kliknij **Sprawdź zaznaczony**: EpubForge uruchamia
  EpubCheck i pokazuje raport (poziom, kod, plik:linia, komunikat) z paskiem podsumowania
  i filtrami błędy/ostrzeżenia/informacje. **Dwuklik** błędu z lokalizacją otwiera plik
  w zakładce Edytor na właściwej linii. **Eksport…** zapisuje raport jako JSON lub HTML.
  W trakcie walidacji pasek postępu pracuje w trybie nieokreślonym, a przycisk
  **Anuluj** przerywa sprawdzanie (kończy proces Javy).
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
epubforge convert input.pdf output.epub --engine pdf2md   # zalecany silnik PDF
epubforge convert input.pdf output.epub --engine calibre  # fallback

# Walidacja EpubCheck (wymaga Javy + epubcheck.jar)
epubforge check book.epub                          # raport; exit 0=OK, 1=błędy, 2=brak narzędzi
epubforge check book.epub --json report.json --min-severity warning

# Spis treści (podgląd / generowanie / naprawa)
epubforge toc book.epub --show
epubforge toc book.epub --generate --max-level 3 --output out.epub
epubforge toc book.epub --repair --dry-run

# Modernizacja EPUB 2 → EPUB 3 (nav, landmarks, dcterms:modified)
epubforge upgrade book.epub                 # NCX zostaje dla starszych czytników
epubforge upgrade book.epub --dry-run       # plan bez zapisu
epubforge upgrade book.epub --drop-ncx -o out.epub

# Naprawa EPUB (CSS, hyphenacja, typografia)
epubforge fix book.epub --remove-colors --replace-justify
epubforge fix a.epub b.epub c.epub --remove-colors --jobs 3
epubforge hyphenate book.epub --lang pl --method soft-hyphen --skip-headers
epubforge hyphenate *.epub --method css --jobs 4 --dry-run
epubforge typo book.epub --lang pl --dry-run
epubforge fix book.epub --optimize-images --max-px 1200 --jpeg-quality 75  # wymaga [images]
epubforge fix book.epub --subset-fonts             # przytnij fonty do użytych znaków ([fonts])
epubforge fix book.epub --subset-fonts --dry-run   # delty rozmiarów fontów bez zapisu

# Typografia (cudzysłowy, pauzy, wielokropek, twarde spacje)
epubforge typo book.epub --lang pl                 # pełna typografia PL
epubforge typo book.epub --lang de --no-nbsp-letters   # cudzysłowy DE, bez sierot
epubforge typo book.epub --no-dashes --nbsp-numbers    # bez pauz, ale twarde spacje przy liczbach

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

# Eksport Kindle (kfx: --engine auto [domyślnie] | calibre | kindle-previewer)
epubforge kfx book.epub                          # auto: Calibre+KFX Output, potem Kindle Previewer
epubforge kfx book.epub --engine calibre
epubforge mobi book.epub --format azw3 --engine calibre
```

`fix`, `hyphenate` i `typo` obsługują listę plików oraz `--jobs N`, co pozwala
przetwarzać kilka EPUB-ów równolegle. Lista wejściowa jest deduplikowana z
zachowaniem kolejności, a wynik kończy się tabelą per plik i kodem wyjścia `1`,
jeśli choć jeden plik się nie udał.

`--dry-run` w tych trzech komendach nie zapisuje EPUB-a na dysku. Zamiast tego
pokazuje unified diff dla plików tekstowych (`.xhtml`, `.css`, `.opf`, `.ncx`,
`.svg` itd.; domyślnie do 40 linii na plik) albo nazwę pliku binarnego z deltą
rozmiaru. `--diff-full` znosi limit diffu. Presety CSS pozostają częścią
`fix --preset`, więc batch i dry-run działają tam przez komendę `fix`.

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
