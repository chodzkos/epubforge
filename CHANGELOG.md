# Changelog

Wszystkie istotne zmiany w projekcie dokumentowane są w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

### Added
- **Taksonomia tagów PL + tagowanie AI** (Etap 29 roadmapy v3) — maks. 10 tagów po
  polsku z kaskady trzech źródeł, AI **opt-in** (domyślnie lokalna Ollama).
  - `src/epubforge/data/taxonomy_pl.toml` — ~45 kanonicznych tagów w czterech
    kategoriach (`gatunek`/`epoka`/`miejsce`/`tematy`) + synonimy + mapowania
    deskryptorów BN i kategorii LC/GB; plik użytkownika w katalogu configu ma
    pierwszeństwo nad wbudowanym.
  - `bookmeta/taxonomy.py` — `load_taxonomy`, `map_subjects` (surowe tematy →
    kanoniczne tagi, dedup po synonimach, propozycje „poza taksonomią"), limit 10
    z priorytetem gatunek → epoka/miejsce → tematy.
  - `bookmeta/ai.py` — klient zgodny z **OpenAI Chat Completions** (stdlib `urllib`,
    `temperature=0`); presety `ollama` (domyślny), `openai`, `anthropic`, `gemini`,
    `deepseek`, `glm` (base_url/model edytowalne). Klucz API **wyłącznie ze zmiennej
    środowiskowej** (w configu tylko jej nazwa). `http` dozwolone tylko dla
    loopback/RFC1918; hosty publiczne wyłącznie `https`. Klasyfikacja gatunku/epoki/
    miejsca/tematów **tylko z listy zamkniętej** taksonomii (walidacja + 1 retry),
    postacie/organizacje otwarte.
  - `bookmeta/tagging.py` — kaskada: (1) mapowanie taksonomii, (2) AI na opisie+TOC
    gdy tagów < 3, (3) AI na próbce treści gdy brak opisu; polityki scalania
    `keep`/`append` (domyślna)/`replace`, dedup z istniejącymi `dc:subject`.
  - GUI: sekcja **Tagi** w zakładce Metadane — „Zaproponuj tagi" → lista propozycji
    z checkboxami i źródłem (taksonomia/AI); ustawienia AI w osobnym dialogu.
    Brak/awaria endpointu AI → czytelny komunikat, kaskada (1) działa bez AI.
- **Provider LubimyCzytac + dopasowanie bez ISBN** (Etap 28 roadmapy v3) —
  rozszerzenie podpakietu `epubforge.bookmeta` o źródło z lubimyczytac.pl
  (scraper pisany **od zera**, bez nowych zależności) oraz wyszukiwanie po
  tytule/autorze dla plików bez ISBN.
  - `bookmeta/providers/lubimyczytac.py`: parsowanie strony książki **JSON-LD
    first** (`schema.org/Book`) + **HTML fallback** (`html.parser`) dla pól spoza
    JSON-LD (opis, wydawca, kategorie); wyszukiwarka → `list[Candidate]`. Każde
    pole opcjonalne — zmiana layoutu → `None`, nigdy wyjątek („best effort").
    LC dołączony do łańcucha **po BN** (daje opisy i cykle).
  - `bookmeta/match.py`: `normalize()` (diakrytyki przez `unicodedata`, odcięcie
    podtytułu po „:", interpunkcja) + scoring `difflib.SequenceMatcher`, próg
    pewności 0.85; `rank_candidates()` sortuje kandydatów wg dopasowania.
  - `bookmeta/isbn.extract_isbn_from_epub()`: wydobycie ISBN ze strony redakcyjnej
    (regex po pierwszych dokumentach spine) — dla plików bez ISBN w metadanych.
  - `bookmeta/cache.py`: cache SQLite w katalogu configu (TTL 30 dni, wersjonowany
    schemat) + rate limiter (min. 2 s między żądaniami, bez równoległości) —
    grzecznościowy scraping z User-Agent identyfikującym EpubForge.
  - GUI: w dialogu „Pobierz metadane…" nowe pola **tytuł/autor** i przycisk
    „Szukaj wg tytułu" → lista kandydatów (tytuł/autor/rok/% dopasowania); dwuklik
    pobiera pełny rekord. Poniżej progu nic nie jest wybierane automatycznie.
- **Metadane z ISBN** (Etap 26 roadmapy v3) — nowy, samodzielny podpakiet
  `epubforge.bookmeta` (zero zależności poza stdlib; **pierwszy kod sieciowy
  w projekcie**) pobierający metadane książki po ISBN. Publiczne API:
  `fetch_by_isbn(isbn)`, `validate_isbn(text)`, dataclass `BookRecord`.
  - Łańcuch providerów **Biblioteka Narodowa → Open Library → Google Books**
    ze scalaniem per pole (puste pola dopełniane z kolejnych źródeł). BN parsuje
    rekord MARC 21 (tytuł, autorzy, wydawca, rok, liczba stron z pola 300 oraz
    **deskryptory przedmiotowe BN** z pól 6XX `$2=DBN`).
  - Twarde zasady bezpieczeństwa dla ruchu sieciowego (wspólny `_http`): wyłącznie
    `https`, twardy timeout, limit rozmiaru odpowiedzi (1 MB), każdy błąd → `None`
    (nigdy wyjątek do UI). Walidacja ISBN (sumy kontrolne 10/13) **przed** zapytaniem.
  - GUI: przycisk **Pobierz metadane…** w zakładce Metadane — pobranie w wątku
    roboczym (nie blokuje UI), podgląd z checkboxami per pole (domyślnie zaznaczone
    tylko puste pola formularza; deskryptory BN osobno, domyślnie odznaczone),
    nigdy ciche nadpisanie. Liczba stron → `<meta property="schema:numberOfPages">`
    w OPF (tylko EPUB 3; EPUB 2 pomijany z notą w statusie) przez nowy
    `epubforge.core.set_number_of_pages`.
- **Subsetting fontów** (Etap 24 roadmapy v3) — nowy fixer
  `epubforge.fixers.subset_fonts` (`FontSubsetOptions`, `FontReport`) przycinający
  fonty do znaków użytych w treści (zwykle −70…−90% rozmiaru fontu). Zbiór znaków =
  wszystkie dokumenty spine + literały CSS + stały zestaw bezpieczeństwa (ASCII,
  polskie znaki, interpunkcja typograficzna oraz `U+00AD`/`U+00A0` — efekty
  hyphenacji i typografii muszą się renderować). Format zachowany (ttf/otf/woff/
  woff2), zapis tylko gdy wynik mniejszy. `@font-face` z `unicode-range` jest
  pomijany (bezpieczniej), a pliki WOFF2 bez `brotli` — pomijane z ostrzeżeniem
  (nie wyjątkiem). Wykrywanie fontów współdzielone z `css_fixer` (`_fontutil`).
  - `fonttools`/`brotli` w nowym extra `[fonts]` (import leniwy z czytelnym błędem).
  - CLI `epubforge fix --subset-fonts` (`--dry-run` pokazuje delty rozmiarów) + krok
    `subset_fonts` w recepturach.
  - GUI: opcja **Przytnij fonty do użytych znaków** w sekcji CSS zakładki **Fixer**
    z ostrzeżeniem o licencjach fontów.

## [2.3.0] - 2026-07-10

Brama wydaniowa **v2.3** roadmapy v3 (Etapy 22–23): integracja pdf2md jako
zalecanego silnika PDF → EPUB oraz modernizacja pakietu EPUB 2 → EPUB 3.

### Added
- **Upgrade EPUB 2 → EPUB 3** (Etap 23 roadmapy v3) — nowy moduł
  `epubforge.converters.upgrade` (`upgrade_to_epub3`, `UpgradeReport`) modernizujący
  pakiet: `package version` → 3.0, `nav.xhtml` (properties="nav") ze spisu NCX,
  `guide` → landmarks (mapa typów → `epub:type`; nieznane pomijane z notą),
  `dcterms:modified` (`CCYY-MM-DDThh:mm:ssZ`), naprawa `unique-identifier` oraz
  `dc:date` (usunięcie `opf:event`, jedna data publikacji). NCX domyślnie zostaje
  (kompatybilność), `--drop-ncx` usuwa plik + wpis manifestu + `spine@toc`.
  Dokumentów treści nie rusza; na wejściu EPUB 3 → no-op. Wynik przechodzi
  EpubCheck jako EPUB 3 bez błędów.
  - CLI `epubforge upgrade book.epub [--drop-ncx] [--dry-run] [-o OUT]`.
  - GUI: sekcja **Uaktualnij do EPUB 3** w zakładce **Fixer** (przycisk z
    potwierdzeniem, raport transformacji w logu).
- **Integracja pdf2md** (Etap 22 roadmapy v3) — nowy silnik konwersji PDF → EPUB
  przez [pdf2md](https://github.com/chodzkos/pdf2md): PDF → Markdown (z wyciąganiem
  obrazów) → Pandoc EPUB (z `--resource-path`, obrazy osadzone w książce). Cały
  materiał pośredni żyje w katalogu tymczasowym (`epubforge.converters.pdf2md`).
  - `engine="pdf2md"` w `to_epub`/`to_epub_streaming` (tylko PDF) oraz w CLI
    `epubforge convert --engine pdf2md`. Tryb `auto` dla PDF wybiera pdf2md, gdy
    jest wykryty, a w przeciwnym razie **bez zmian** wraca do Calibre.
  - Detekcja `pdf2md` (CLI) i `pdf2md-gui` (handoff) w `core.detection`
    (`Tools.pdf2md`, `Tools.pdf2md_gui`), z wersją z `pdf2md --version`; status
    „pdf2md" na pasku narzędzi.
  - GUI Konwerter: przy dodaniu PDF (gdy wykryto pdf2md) dialog wyboru silnika
    „pdf2md (zalecane)" / „Calibre (eksperymentalne)" z zapamiętaniem wyboru
    (`config["pdf_engine"]`); radio **pdf2md** oraz przycisk **Otwórz w pdf2md**
    (handoff do `pdf2md-gui`) aktywne, gdy na liście jest PDF.

## [2.2.0] - 2026-07-09

Brama wydaniowa v2.2 (Etapy 19–21 roadmapy v3): anulowanie i postęp długich
operacji, optymalizacja obrazów oraz szukaj/zamień w całym EPUB. Zawiera też
wcześniejsze funkcje z [Unreleased] (typografia PL, batch/dry-run, receptury TOML).

### Added
- **Szukaj i zamień w całym EPUB** (Etap 21 roadmapy v3) — nowy moduł
  `epubforge.core.search` (`search_epub`, `replace_in_epub`, `SearchHit`,
  `ReplaceReport`) oraz panel **Szukaj/Zamień** w zakładce **Edytor**
  (skrót **Ctrl+Shift+F**). Przeszukuje pliki tekstowe (XHTML/HTML/XML/OPF/NCX/SVG/
  CSS/TXT) z opcjami: regex, wielkość liter, całe słowa (`\b` z `re.UNICODE` —
  działa dla polskich znaków) oraz zakres (bieżący plik / cały EPUB). Wyniki
  zgrupowane po pliku, dwuklik otwiera plik w edytorze na trafieniu. „Zamień
  wszystkie" pisze **wyłącznie do bufora** (utrwala „Zapisz EPUB"), a przed
  zamianą synchronizuje niezapisane zmiany bieżącego pliku. Pliki ze znakami
  nie-UTF-8 (`�`) są pomijane przy zamianie (zwracane w `report.skipped`);
  błędny/pusty/zbyt długi wzorzec → czytelny `SearchPatternError`. Wyszukiwanie
  całego EPUB biegnie w wątku roboczym z anulowaniem (Etap 19).
  - Czyste helpery tekstowe (`decode_text`, `offset_to_line_col`,
    `line_col_to_offset`, `resolve_internal_path`) przeniesione do
    `epubforge.core.textutil`; `gui.editor_files` je re-eksportuje (bez zmian API).
- **Optymalizacja obrazów** (Etap 20 roadmapy v3) — nowy fixer
  `epubforge.fixers.optimize_images` (`ImageFixOptions`, `ImageReport`) odchudzający
  EPUB-y pod czytniki e-ink: skalowanie do zadanego dłuższego boku, rekompresja
  JPEG/PNG, opcjonalna skala szarości i usuwanie EXIF/ICC. Format pliku nigdy się
  nie zmienia (jpg→jpg, png→png), zapis następuje tylko gdy wynik jest mniejszy
  (idempotentność), okładka jest rozpoznawana (EPUB 3 `properties="cover-image"` /
  EPUB 2 `<meta name="cover">`) i domyślnie pomijana, PNG z alfą zachowuje
  przezroczystość, paleta zostaje paletą, a SVG jest pomijane. Pillow importowane
  leniwie przez nowy extra `[images]` — brak biblioteki daje czytelny komunikat.
  - CLI: `epubforge fix --optimize-images [--max-px N] [--jpeg-quality Q] [--grayscale]`
    (działa z batch `--jobs` i `--dry-run` — pliki binarne pokazują deltę rozmiaru).
  - GUI: sekcja **Obrazy** w zakładce **Fixer** z podsumowaniem „zaoszczędzono X MB (-Y%)".
  - Receptury: nowy krok `optimize_images` w rejestrze operacji.
- **Anulowanie i postęp długich operacji** (Etap 19 roadmapy v3) — zakładki
  **Konwerter**, **Eksport Kindle** i **Walidacja** dostały przycisk **Anuluj**
  oraz pasek postępu. Konwersje Calibre pokazują realny procent (parsowanie linii
  „NN%"), a anulowanie kończy proces silnika (`terminate` → 3 s karencji → `kill`)
  i zostawia wpis „Anulowano" w logu. Walidacja EpubCheck pokazuje pasek
  nieokreślony i również daje się przerwać (ubija proces Javy).
  - Nowy, czysty moduł `epubforge.core.streaming` — `run_subprocess_streaming(...)
    -> ProcessResult` (kooperacyjne anulowanie sprawdzane także „w ciszy", twardy
    `timeout`, parser postępu Calibre). `gui.workers` re-eksportuje te symbole, więc
    konwertery korzystają z nich bez łamania zasady zależności (`core` nie importuje
    `gui`).
  - `Worker` (GUI) zyskał `cancel()`, `is_cancelled` i sygnał `cancelled` (anulowanie
    NIE jest raportowane jako `failed`; **nigdy** nie wołamy `QThread.terminate()`).
    Trzeci hook `should_cancel` jest przekazywany callable'owi opcjonalnie —
    wykrywany przez introspekcję sygnatury, więc dotychczasowe workery przyjmujące
    dwa hooki działają bez zmian.
  - Strumieniowe warianty konwerterów: `to_epub_streaming`, `to_mobi_streaming`,
    `to_kfx_streaming` (log na żywo, postęp, anulowanie); `ConversionResult` zyskał
    pole `cancelled`. `run_epubcheck(..., should_cancel=...)` ma wariant przerywalny.
    Faza zapisu EPUB (`Epub.save`: tmp → `os.replace`) pozostaje nieprzerywalna.
- **Receptury TOML (pipeline)** — nowy moduł `epubforge.recipes` z jawnym
  rejestrem kroków (`fix_css`, `typography`, `hyphenate`, `apply_preset`,
  `to_mobi`, `to_kfx`), walidacją nieznanych operacji/opcji i wbudowanymi
  recepturami `kindle-pl` oraz `czytnik-epub`. Kroki fixerów działają na jednym
  otwartym EPUB-ie i zapisują plik raz; kroki eksportu pracują na zapisanym pliku
  bez mutowania wejścia. CLI dostało `epubforge run <nazwa|ścieżka.toml> pliki...`
  z `--jobs`, `--out-dir`, `--list` i `--dry-run` (dry-run obejmuje fazę fixerów,
  eksport jest pomijany z adnotacją). GUI dostało dialog **„Uruchom recepturę…”**
  w zakładce Fixer: dropdown receptur, FileList i log Workera.
- **Batch i dry-run w CLI fixerów** — `fix`, `hyphenate` i `typo` przyjmują teraz
  wiele plików naraz, deduplikują wejście z zachowaniem kolejności i obsługują
  `--jobs N` przez `ProcessPoolExecutor` z tabelą wyników per plik. Dodano
  `--dry-run` z unified diffem zmian tekstowych (limit 40 linii na plik,
  `--diff-full` pokazuje całość) oraz deltą rozmiaru dla wpisów binarnych.
  Presety CSS pozostają aplikowane przez `fix --preset`, więc korzystają z tego
  samego batcha i dry-runu.
- **Fixer typografii polskiej** (`epubforge.fixers.typography` — `fix_typography`, `TypographyOptions`, `TypographyReport`) — poprawa mikrotypografii tekstu w EPUB, funkcja-wyróżnik (Etap 16 roadmapy v3). Reguły (każda za osobną flagą): cudzysłowy typograficzne dobierane językiem (pl `„…"`, en `"…"`, de `„…"`), pauzy w dialogach i wtrąceniach (łączniki wewnątrz słów jak *biało-czerwony* bez zmian), wielokropek `...` → `…`, twarde spacje po polskich sierotach (a/i/o/u/w/z) oraz opcjonalnie między liczbą a jednostką (`10 km` — domyślnie OFF). Parsowanie utwardzonym parserem (ochrona XXE), serializacja zachowuje DOCTYPE i deklarację XML; `code`/`pre`, atrybuty i komentarze nietknięte; parowanie cudzysłowów niesione przez granice tagów inline (`<em>`); reguły idempotentne (drugi przebieg = 0 podmian). `TypographyReport` podaje liczbę podmian per reguła, per plik i sumarycznie.
- **CLI `epubforge typo`** — `epubforge typo book.epub --lang pl` z flagami `--no-quotes/--no-dashes/--no-ellipsis/--no-nbsp-letters` oraz `--nbsp-numbers`; raport podmian per reguła.
- **Sekcja „Typografia" w zakładce Fixer** (GUI) — checkboxy reguł + dropdown języka (pl/en/de), uruchamiana przez `Worker` jak pozostałe fixery, liczby podmian trafiają do logu.
- Rozszerzenie utwardzonego parsera XML (`core/_xml_safe`): `parse_untrusted_document()` (tryb recover dla „brudnych" dokumentów EPUB, bez osłabiania ochrony XXE) oraz `serialize_document()` (zachowuje DOCTYPE) — używane przez fixer typografii.
- **Okno pomocy offline** (kitowy `HelpWindow` z `chodzkos-gui-kit`, pin `v0.5.0`) — dostęp przyciskiem **„Pomoc"** w panelu **O programie** (zastąpił link „Pomoc (README)"; „GitHub" zostaje linkiem online). Zakładki per funkcja, odwzorowujące zakładki GUI: Metadane (Dublin Core), Konwerter (formaty wejściowe, silnik Auto/Pandoc/Calibre), Fixer (hyphenacja pyphen + CSS Fixer), Eksport Kindle (KFX/MOBI/AZW3, silniki), Edytor, Walidacja (EpubCheck 5.x + wymóg Javy ≥ 11), Spis treści, Statystyki oraz przegląd narzędzi zewnętrznych. Treść opisuje stan STABILNY; stan zmienny (czy Java/EpubCheck/Calibre wykryte) delegowany do dolnego paska statusu narzędzi. Kolory przez `palette(...)` (czytelne w obu motywach, re-render przy zmianie motywu robi kit dla wszystkich zakładek).

### Changed
- **Wspólne widgety GUI pochodzą teraz z chodzkos-gui-kit** (`qt/widgets`, pin `v0.4.3`) — lokalne `gui/widgets/{path_entry,file_list,log_view}.py` usunięte, re-eksport z `epubforge.gui.widgets` (importy w zakładkach bez zmian):
  - **`PathEntry`**: zachowanie bez zmian (tryby dir/file/save, `remember_key`, `path_changed`, `get()/set()`); polskie etykiety przez `path_entry_texts()` (`PathEntryTexts` z `_()`).
  - **`FileList`**: zachowanie bez zmian (toolbar, D&D z rekursją folderów, sygnały, `confirm`, `extensions`); polskie etykiety przez `file_list_texts()` i licznik z formami mnogimi przez `file_list_count_label` (`ngettext`).
  - **`LogView`**: `append_line(text, level)`/`set_theme`/`clear` identyczne. **Zyskuje** re-render historii przy zmianie motywu — `set_theme()` przemalowuje teraz CAŁY log (wcześniej tylko nowe linie), więc po przełączeniu motywu w locie wcześniejsze wpisy też dostają kolory nowej palety.

### Fixed
- **Zakładki GUI nie nakładają sekcji przy małym oknie** — pionowe zakładki
  (`Fixer`, `Metadane`, `Konwerter`, `Eksport Kindle`, `Walidacja`, `Spis treści`,
  `Statystyki`) używają teraz bezramkowego `QScrollArea` z pionowym przewijaniem.
  Minimalny rozmiar głównego okna zostaje `760×520`; przepełnienie rozwiązuje
  scroll, nie sztuczne powiększanie okna.

## [2.0.0] - 2026-06-22

### Fixed
- **Pasek tytułu jaśniał przy zmianie rozmiaru okna** po przełączeniu na ciemny
  motyw: Windows resetuje atrybut DWM przy przerysowaniu ramki podczas resize, a
  `_sync_titlebar` był wołany tylko na show/aktywacji/zmianie motywu. Dodano
  `resizeEvent` z debounce'owanym `QTimer` (~120 ms, restartowany przy każdej
  klatce, sync po ustaniu ciągnięcia) — re-synchronizuje belkę samego głównego
  okna.
- **Dolny pasek ze statusem narzędzi znikał po zmianie motywu** (i po każdej
  interakcji z menu): status był jednorazowym `statusBar().showMessage()` —
  tymczasowy komunikat nadpisywany przez statusTipy menu (Motyw/Język) i nie
  przywracany. Zamieniono na TRWAŁY widget (`addPermanentWidget(QLabel)`); treść
  liczona raz z `self.tools` (motyw tylko przemalowuje etykietę).

### Changed
- **Podbicie `chodzkos-gui-kit` → v0.3.4**: wchodzi fix **repaintu item-views**
  w `_repolish` — po zmianie motywu `QAbstractItemView` (widoki walidacji/TOC)
  dostają świeżą paletę zamiast trzymać stary `Base` po `dark→light`. Plus
  `save_file(initial_name=…)` (prefill nazwy, na razie nieużywany w EpubForge).
  API kompatybilne, zero zmian w kodzie.
- **Podbicie `chodzkos-gui-kit` → v0.3.2**: wchodzi m.in. fix marshalingu **DWM
  HWND** (`wintypes.HWND` + `argtypes`) naprawiający truncację 64-bit uchwytów na
  Win64 — poprawia ciemny/jasny pasek tytułu EpubForge na niektórych oknach.
  API kompatybilne (bez zmian w kodzie EpubForge); kit po drodze dorobił tor
  tkinter (v0.2.0, nieużywany tu), IconProvider (v0.3.0) i `set_current_palette`
  (v0.3.1).
- **Podbicie `chodzkos-gui-kit` → v0.1.1** (marker `py.typed`): zdjęto mypy
  override `ignore_missing_imports` dla `chodzkos_gui_kit.*` oraz obejścia
  `str()/Path()` na granicy kitu. Przywrócone typowanie wychwyciło 3 utajone
  niezgodności `palette.name: str` → `ThemeName` — naprawione przez
  `chodzkos_gui_kit.qt.theme.mode_of()`.
- **Motyw, dialogi plików, pasek tytułu i config przeniesione do
  `chodzkos-gui-kit` v0.1.0** — wspólne komponenty GUI (ekstrakcja P1) zamiast
  lokalnych kopii. Usunięto `gui/theme.py`, `gui/window_theme.py`,
  `gui/file_dialogs.py`; `core/config.py` to teraz cienki adapter nad
  `chodzkos_gui_kit.config` (zostaje tylko glue EpubForge: nazwa aplikacji
  `epubforge` + jednorazowa migracja configu spod `.exe`). Widgety i zakładki
  importują motyw/dialogi z kitu (`chodzkos_gui_kit.qt.{theme,titlebar,dialogs}`,
  `chodzkos_gui_kit.palette`); rola koloru dawnego `Theme.link` → własność
  `Palette.accent_text`. Raport HTML statystyk czyta jasną paletę z kitu
  (`chodzkos_gui_kit.palette.LIGHT`) zamiast zduplikowanych hexów. Testy logiki
  motywu/dialogów/configu żyją w kicie; w EpubForge zostają testy integracyjne
  „aplikacja używa kitu poprawnie" + migracja configu. Zależność: nowy pakiet
  bazowy `chodzkos-gui-kit` (warstwa 0, czysty Python) w `dependencies`, tor Qt
  przez extra `[qt]` w `gui`.

### Removed
- **Usunięto nieużywany `uv.lock`** — projekt jest pip-owy (CI: `pip install -e`),
  nie ma sekcji `[tool.uv]`, a osierocony lock był nieaktualny i nie zawierał nawet
  `chodzkos-gui-kit`. Dodany do `.gitignore`, by nie wrócił przypadkiem, dopóki
  EpubForge nie przejdzie świadomie na uv.

### Added
- **Statystyki książki (F8)** — moduł `stats.py`: liczba słów/znaków, szac. stron
  (250 słów/stronę), czas czytania (200 słów/min), wykryty język (opcjonalny
  `langdetect` z extra `[stats]`, fallback do metadanych) i top-słowa (stop-listy
  pl/en/de). Samowystarczalny **raport HTML** (inline CSS jasnej palety, inline SVG
  wykresu — zero zasobów sieciowych, `html.escape` na wszystkim z książki): karty
  liczb, chmurka top-słów (skala log), tabela rozdziałów, wykres słupkowy. CLI
  `epubforge stats book.epub [--report out.html] [--top] [--words-per-page] [--wpm]`
  oraz zakładka GUI „Statystyki" (karty, top-słowa, rozdziały, eksport/otwarcie
  raportu). Stop-listy pakowane do wheel/.exe.
- **Konwersja formatów Kindle → EPUB (F7)** — MOBI/AZW3/AZW/PRC jako wejście
  konwersji (silnik **wyłącznie Calibre**; Pandoc jawnie odrzuca formaty Kindle
  czytelnym błędem). Lekki detektor `converters/kindle_drm.py` (czysty `struct`
  na nagłówku PalmDB/MOBI) wykrywa DRM (typ szyfrowania 1/2) i **przed** Calibre
  zgłasza przyjazny `ConversionError`; dodatkowo „DRM" w stderr Calibre jest
  mapowane na ten sam komunikat. EpubForge nie usuwa zabezpieczeń (KindleUnpack
  pominięty — GPL). GUI: pliki Kindle wymuszają silnik Calibre (etykieta), a pliki
  z DRM są odrzucane ostrzeżeniem zamiast śladu w logu. CLI `convert` działa od ręki.
- **Przybliżony podgląd XHTML w edytorze (F-P)** — dla plików HTML/XHTML prawy
  panel edytora ma przełącznik **Kod ⇄ Podgląd** (domyślnie Kod). Podgląd renderuje
  silnik `QTextDocument` (jak inspektor CSS) na białej „papierowej" karcie
  niezależnej od motywu; obrazki o względnych `src` są osadzane jako `data:` URI
  z bajtów EPUB (duże > 3 MB → placeholder z nazwą, by dokument nie puchł). Podgląd
  odświeża się z bieżącej (niezapisanej) treści edytora z debounce ~400 ms i jest
  zawsze tylko do odczytu. Pasek nad podglądem niesie adnotację o ograniczeniach
  silnika oraz przyciski **Sigil / Calibre Editor** otwierające pełny podgląd
  (wspólny helper `gui/external_tools.py`, bez duplikowania logiki uruchamiania).
  Inspektor CSS bez zmian.
- **Generator i edytor spisu treści (F10)** — pakiet `toc/` (czysta logika) +
  komenda `epubforge toc` + zakładka „Spis treści". `generate_toc` buduje drzewo
  z nagłówków `h1..h{max_level}` w kolejności spine (lxml recover), podciąga
  osierocone nagłówki, wstrzykuje brakujące `id="efh-NNNN"` (idempotentnie,
  z zachowaniem deklaracji XML i DOCTYPE), pierwszy nagłówek pliku linkuje bez
  fragmentu, pliki bez nagłówków pomija. `write_toc` zapisuje nav.xhtml (podmienia
  tylko `<nav epub:type="toc">` lub tworzy dokument + `properties="nav"`, spine
  nietknięty) i pełny toc.ncx (playOrder DFS, `spine@toc`); href względne liczone
  `posixpath.relpath` (różne bazy). `read_toc` czyta nav z fallbackiem do ncx.
  `validate_toc`/`repair_toc` wykrywają i usuwają martwe wpisy (dzieci podciągane).
  GUI: drzewo Tytuł|Cel z edycją tytułu, drag&drop (`InternalMove` + synchronizacja
  modelu przez `move_entry`), przyciski Generuj/Napraw/Dodaj/Usuń/⬆⬇⬅➡ i zapis;
  martwe wpisy kolorem `red` z tooltipem. CLI `--show`/`--generate`/`--repair`.

- **Walidacja EPUB przez EpubCheck 5.x (F2)** — nowa zakładka „Walidacja" oraz
  komenda `epubforge check`. Detekcja `java` (Temurin JRE 17+, wersja z `java -version`
  na STDERR, wymagane ≥ 11) i `epubcheck.jar` (override `tools.epubcheck_jar` → glob
  ProgramFiles/`~` → `<config>/epubcheck/epubcheck.jar` → obok exe; wersja z
  `META-INF/MANIFEST.MF` bez uruchamiania Javy). Moduł `validators/epubcheck.py`:
  `run_epubcheck` uruchamia `java -jar … --json` (tempfile, timeout, CREATE_NO_WINDOW),
  exit≠0 z poprawnym JSON to raport `valid=False`, brak/zepsuty JSON lub timeout to
  `ValidationError`; parser defensywny z normalizacją ścieżek do wewnętrznych. CLI
  zwraca kody 0 (poprawny) / 1 (błędy) / 2 (brak narzędzi), opcje `--json`,
  `--min-severity`. GUI: FileList + Worker, podsumowanie z formami mnogimi, filtry
  severity, `QTreeWidget` z kolorami z motywu — **dwuklik błędu skacze do linii w
  edytorze** (`open_in_editor`), eksport raportu do JSON/HTML, panel pomocy i
  „Wskaż epubcheck.jar…" gdy brak narzędzi.
- **Inspektor reguł CSS z podglądem na żywo (F3+)** — w edytorze, przy otwartym
  `.css`, panel z listą reguł arkusza; dla wybranej reguły podgląd przykładowego
  tekstu sformatowanego zgodnie z nią (silnik rich text Qt, biała „papierowa"
  karta niezależna od motywu). Edycja reguły aktualizuje podgląd na żywo;
  „Zastosuj do arkusza" wpisuje zmianę jedną operacją kursora (undo cofa całość).
  Logika w `fixers/css_rules.py` (parsowanie po offsetach, podmiana po spanie bez
  re-serializacji). Podgląd obsługuje podzbiór CSS — nieobsługiwane właściwości są
  wypisywane. Synergia z presetami: przycisk „Podgląd…" w zakładce Fixer.
- **Edytor wewnętrzny EPUB (F3, część 1)** — zakładka „Edytor": drzewo plików
  pogrupowane wg media-type (Tekst/Style/Obrazy/Fonty/Inne), edytor z numeracją
  linii, podświetlaniem składni XML/CSS (kolory z motywu), wyszukiwarką (Ctrl+F,
  F3/Shift+F3, licznik trafień) i statusem wiersz:kolumna. Podgląd obrazów,
  panel info dla binariów. Start w trybie tylko-do-odczytu (przełącznik „Tryb
  edycji"); zapis pliku (Ctrl+S, walidacja XML), „Zapisz EPUB" z backupem `.bak`;
  pliki nie-UTF-8 są tylko do odczytu. Kontrakt `MainWindow.open_in_editor(...)`
  dla kolejnych funkcji.
- **Biblioteka presetów CSS (F11)** — gotowe szablony stylów dołączane do EPUB-a:
  `reader-friendly`, `print-like`, `dark-oled`, `manga-rtl` oraz import własnych
  arkuszy (walidacja tinycss2, katalog `config_dir()/presets`). API
  (`list_presets`/`get_preset`/`apply_preset`/`import_user_preset`), CLI
  (`epubforge presets list`, `fix --preset ID [--preset-mode replace]`) i sekcja
  „Preset CSS" w zakładce Fixer. Tryb `append` dopina arkusz idempotentnie
  (`<item>` w manifeście + `<link>` jako ostatnie dziecko `<head>`), `replace`
  najpierw usuwa istniejące arkusze.
- **Internacjonalizacja GUI i CLI przez gettext** — wspólne katalogi PL/EN/DE
  (`msgid` po polsku), kompilowane `.mo` w repo i przełącznik **Język** w górnym
  pasku GUI (zmiana działa po restarcie). Build kompiluje locale przed PyInstallerem
  i sprawdza obecność plików `.mo`.

### Fixed
- **Detekcja Javy dla Temurin 25 (LTS) i innych bez wpisu w PATH** — instalatory
  Temurin rejestrują `java.exe` przez App Paths w rejestrze, ale nie dodają
  katalogu do `PATH`, więc `Tools.java()` nie znajdowało Javy mimo działającego
  `java -version`. Detekcja przeszukuje teraz kolejno: override `tools.java_path`
  → `PATH` → App Paths (HKLM/HKCU) → rejestr Eclipse Adoptium (JRE/JDK → MSI/Path)
  → typowe katalogi `Program Files\Eclipse Adoptium\*\bin` → `JAVA_HOME`. Parser
  wersji obejmuje krótki format (np. `25.0.3` → 25). Dodano override
  `tools.java_path` (pełna ścieżka do java) z re-utrwalaniem w cache i przycisk
  „Wskaż java.exe…"
  w panelu pomocy walidacji; po wskazaniu ścieżki detekcja jest wymuszana, więc
  stare „brak Javy" z cache nie blokuje.
- **Pasek tytułu zamrożony po sekwencji jasny→ciemny→jasny** — atrybut DWM jest
  stanowy, więc `sync_titlebar` ustawia go teraz BEZWARUNKOWO na motyw aplikacji
  (bez pomijania „przy zgodzie z systemem"), na KAŻDYM oknie top-level przy każdym
  `apply()` oraz w `changeEvent`/aktywacji. Wcześniej końcowy jasny zostawiał
  czarną belkę.
- **Puste przyciski toolbara nienatywnego `QFileDialog`** — dialog przypina
  przyciski do ~22 px, a app-owy QSS `QToolButton { padding: 4px 12px }` przycinał
  w nich ikonę do zera (zostawał sam tooltip). Per-widget QSS zdejmuje teraz to
  przycięcie z każdego przycisku toolbara, a przyciskom nawigacji (back/forward/
  toParent/newFolder) dokładana jest standardowa ikona, gdy własna jest pusta.
- **Tooltipy po zmianie motywu w locie** — `QToolTip` dostaje jawnie świeżą
  paletę po każdym `apply()`, a QSS jest ponownie generowany i ustawiany dla
  bieżących kolorów.
- **Dopieszczony fallbackowy dialog Qt** (gdy motyw aplikacji ≠ motyw systemu):
  pasek boczny (Pulpit / Dokumenty / Pobrane / dyski / ostatni katalog), widok
  szczegółowy (`Detail`) i zapamiętywany rozmiar okna (~900×550 domyślnie, zapis
  w configu z debounce). Wcześniej dialog Qt startował goły i bez skrótów.
- **Symetryczna reguła dialogów plików i paska tytułu** — natywny dialog/pasek
  tylko gdy motyw aplikacji == motyw systemu; przy KAŻDYM rozjeździe (ciemny↔jasny
  w obie strony) używany jest dialog Qt z paskiem zgodnym z aplikacją. Wcześniej
  wymuszany był tylko kierunek „ciemny", więc app-jasny + system-ciemny dawał
  niespójny ciemny dialog. Motyw systemu czytany jest w momencie otwierania dialogu.
- **Odświeżanie przy zmianie motywu systemu w tle** (tryb auto) — po `unpolish`/
  `polish` wołamy `update()` na wszystkich widgetach i oknach top-level, co usuwa
  opóźnione przemalowanie częściowo widocznych okien.

### Changed
- **Wyraźniejsza sygnalizacja trybu edycji w edytorze EPUB** — przełącznik pokazuje
  aktualny stan tekstem („Tryb: tylko podgląd" / „Tryb: edycja"), nad obszarem
  edytora jest status trybu w kolorze motywu (akcent + „● Edycja" w edycji, `fg2`
  w podglądzie), a obszar edytora ma obwódkę w kolorze akcentu tylko gdy edycja jest
  aktywna (karetka widoczna w edycji, ukryta w podglądzie). Tryb jest pamiętany per
  sesja; pliki nie-UTF-8 pozostają tylko do odczytu (bez akcentu) mimo włączonego
  trybu edycji.
- **Własny silnik motywu zamiast `qdarktheme`** (GUI standard v2.0) — `theme.py`
  buduje motyw sam: styl Fusion + `QPalette` (baza kolorów) + QSS wyłącznie na
  akcenty, z akcentem marki `#5DCAA5` i pełną tabelą stanów (hover/pressed/focus/
  disabled/selection). Zniknęła zależność `pyqtdarktheme-fork`.
- **Konfiguracja przez `platformdirs`** z zapisem debounce'owanym (~1 s) i atomowym
  (`ConfigStore.mark_dirty`/`flush`); wariant portable wykrywany markerem
  `portable.flag` obok exe (naprawia zapis configu w `Program Files` dla instalacji).
- **Pasek tytułu i dialogi plików (Windows, Qt 6.5+)** — DWM/`DontUseNativeDialog`
  wymuszane tylko przy rozjeździe motyw aplikacji ≠ motyw systemu; przy zgodzie
  prowadzi je Qt.
- **Build**: `upx=False` w obu spec-ach (UPX uszkadza DLL-e Qt); instalator (onedir)
  rekomendowany, portable z notą o wolniejszym starcie i false-positives AV.
- **GUI przepisane z tkinter na PySide6 (Qt)** — pełna parzystość funkcji z v1.0
  (zakładki Metadane / Konwerter / Fixer / Eksport Kindle, górny pasek z motywem
  i oknem „O programie", tooltipy, drag&drop, zapamiętany katalog wyjścia).
- **Zależności GUI**: `tkinterdnd2` i `darkdetect` zastąpione przez `PySide6`;
  drag&drop jest teraz natywny w Qt (bez binariów `tkdnd`).
- **Testy GUI** przeniesione na `pytest-qt` (platforma `offscreen`); CI bez `xvfb`.

## [1.0.0] - 2026-06-11

Pierwsze stabilne wydanie — komplet funkcji biblioteki, CLI i GUI.

### Added
- **Core `Epub`** — odczyt/edycja/bezpieczny zapis EPUB (mimetype pierwszy i
  nieskompresowany, zapis atomowy, kopiowanie strumieniowe niezmienionych wpisów,
  backup `.bak`, `opf_path` z `container.xml`, leniwy manifest/spine).
- **Metadane Dublin Core** — `Metadata` (tytuł, autorzy, język, identyfikator,
  wydawca, data, opis, tematy) z `from_opf`/`to_opf` zachowującym resztę OPF.
- **Seria/cykl** — `series` + `series_index` w formacie Calibre (EPUB 2) i EPUB 3
  (`belongs-to-collection`).
- **Wykrywanie narzędzi** — Pandoc, Calibre (ebook-convert/viewer/editor), Sigil,
  Kindle Previewer 3, kindlegen, wtyczka KFX; cache w `config.json` z re-detekcją.
- **Konwersja → EPUB** — TXT/MD/DOCX/HTML/ODT/RTF/PDF przez Pandoc lub Calibre.
- **Eksport Kindle** — EPUB → KFX (Calibre + wtyczka KFX / KP3 eksperymentalny)
  oraz MOBI/AZW3 (Calibre / kindlegen wycofany).
- **Hyphenacja** — `pyphen`, metody soft-hyphen i CSS (z ostrzeżeniem o kompromisie).
- **CSS Fixer** — `tinycss2`: usuwanie kolorów/fontów, reset, justify→left, marginesy.
- **CLI** — `convert`, `fix`, `hyphenate`, `meta`, `kfx`, `mobi`.
- **GUI (tkinter)** — zakładki Metadane / Konwerter / Fixer / Eksport Kindle,
  górny pasek z przełącznikiem motywu i oknem „O programie", tooltipy na wszystkich
  kontrolkach, motyw jasny/ciemny/auto (`darkdetect`) z ciemnym paskiem tytułu na
  Windows, domyślny katalog wyjścia = katalog pliku źródłowego.
- **Build** — PyInstaller (portable `epubforge.exe` + onedir), instalator Inno Setup
  (`epubforge-setup.exe`), generator placeholderowej ikony, build na tag `v*` w CI.
- **CI/CD** — testy na Linux/Windows/macOS × Python 3.10–3.12, ruff, `mypy --strict`
  (linux/darwin/win32), pre-commit hooks.

### Decyzje techniczne
- CSS: `tinycss2` zamiast `cssutils` (nie psuje CSS3).
- Zapis EPUB: kopiowanie strumieniowe ze źródła zamiast ładowania całości do RAM.
- Hyphenacja: dwie metody (soft-hyphen / CSS) — wybór należy do użytkownika.
- PyInstaller: jawny hook dla natywnych binariów `tkdnd` (drag&drop w `.exe`).
- PDF → EPUB: eksperymentalne, za jawnym potwierdzeniem w GUI.
- Dialogi plików: pozostają natywne (jasne) — ograniczenie tkinter (udokumentowane).

---

<!--
Szablon wpisu dla nowej wersji:

## [X.Y.Z] - YYYY-MM-DD

### Added
- nowe funkcje

### Changed
- zmiany w istniejących funkcjach

### Deprecated
- funkcje do usunięcia w przyszłości

### Removed
- usunięte funkcje

### Fixed
- naprawione błędy

### Security
- poprawki bezpieczeństwa
-->

[Unreleased]: https://github.com/chodzkos/epubforge/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/chodzkos/epubforge/releases/tag/v1.0.0
