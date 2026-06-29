# 💬 EpubForge — Prompty dla Claude Code

Gotowe do wklejenia prompty dla każdego etapu z `ROADMAP.md`. Skopiuj cały blok dla danego etapu, wklej do Claude Code, czekaj na wykonanie.

---

## 🎯 Etap 0 — Foundation

```
Pracujemy nad projektem EpubForge. Przeczytaj proszę CLAUDE.md, ROADMAP.md i pyproject.toml żeby się zorientować.

ZADANIE: Realizujemy Etap 0 z ROADMAP.md - "Foundation".

Wykonaj kolejno:

1. Utwórz nową gałąź: feature/stage-0-foundation
2. Sprawdź czy struktura katalogów odpowiada wymaganiom z ROADMAP.md - jeśli brakuje czegoś, dodaj puste pliki __init__.py
3. Uzupełnij pyproject.toml o sekcje [project.optional-dependencies] dla "dev" (pytest, pytest-cov, ruff, mypy)
4. Sprawdź czy plik .github/workflows/test.yml jest poprawny - dodaj uruchamianie testów, ruff i mypy
5. Utwórz tests/test_sanity.py z prostym testem importu:
   def test_package_imports():
       import epubforge
       assert epubforge.__version__
6. Utwórz src/epubforge/__init__.py z __version__ = "0.1.0-dev"
7. Uruchom pytest, ruff check, mypy. Napraw wszystkie problemy.
8. Zacommituj zmiany z wiadomością: "chore(stage-0): project foundation with CI/CD"
9. Zaproponuj komendę push i utworzenie PR

PRZYPOMNIENIE: Wszystkie komentarze w kodzie po polsku. Conventional commits.
NIE pushuj automatycznie - poczekaj na moje zatwierdzenie.
```

---

## 📦 Etap 1 — Core: klasa Epub

```
Realizujemy Etap 1 z ROADMAP.md - "Core: klasa Epub".

Przeczytaj sekcję Etap 1 w ROADMAP.md - tam jest pełne API klasy.

Wykonaj:

1. Sprawdź że jesteś na main i pull. Utwórz gałąź: feature/stage-1-core-epub
2. Utwórz src/epubforge/core/exceptions.py z klasami wyjątków:
   - EpubError (bazowa)
   - InvalidEpubError
   - EpubNotOpenError
   - OpfNotFoundError
3. Utwórz src/epubforge/core/epub.py z klasą Epub zgodnie z API w ROADMAP.md.
   Implementacja:
   - Używa stdlib: zipfile, xml.etree.ElementTree (lub lxml jeśli dostępne)
   - opf_path odczytywany z META-INF/container.xml (NIE zgadywany!)
   - Lazy loading - manifest/spine wczytywane tylko gdy potrzebne
   - Context manager (__enter__/__exit__)
   - read_file/write_file operują na ścieżkach względnych wewnątrz EPUB
   - save() z opcjonalnym output_path - jeśli None, nadpisuje oryginał z backupem
   - backup() tworzy plik .bak obok oryginału

   ⚠️ KRYTYCZNE - zasady zapisu ZIP (przeczytaj sekcję "bezpieczny zapis" w ROADMAP.md Etap 1):
   - Plik "mimetype" MUSI być PIERWSZY w archiwum
   - Plik "mimetype" MUSI być zapisany BEZ kompresji (zipfile.ZIP_STORED)
   - Zawartość mimetype: dokładnie "application/epub+zip" (bez newline)
   - Pozostałe pliki z kompresją (ZIP_DEFLATED)
   - Zapis atomowy: plik .tmp, potem os.replace()
4. Utwórz tests/fixtures/sample.epub - prosty EPUB testowy (możesz wygenerować skryptem)
5. Utwórz tests/test_epub.py z testami pokrywającymi:
   - Otwarcie EPUB i odczyt opf_path z container.xml
   - Listowanie plików
   - Odczyt zawartości pliku wewnętrznego
   - Modyfikacja i zapis (przez context manager)
   - SPRAWDŹ że mimetype jest pierwszy i nieskompresowany:
     with zipfile.ZipFile(output) as zf:
         assert zf.namelist()[0] == "mimetype"
         assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
   - Backup
   - Obsługa błędów (plik nie istnieje, uszkodzony ZIP, brak container.xml)
6. Uruchom testy, lint, mypy. Cel: coverage > 80% dla epub.py.
7. Zacommituj: "feat(core): Epub class for reading and writing EPUB archives"
8. Zaproponuj push i PR.

NIE pushuj automatycznie.
```

---

## 🏷️ Etap 2 — Core: Metadane

```
Realizujemy Etap 2 z ROADMAP.md - "Metadane Dublin Core".

Wykonaj:

1. Gałąź: feature/stage-2-metadata (z main, po pull)
2. Utwórz src/epubforge/core/metadata.py:
   - dataclass Metadata zgodny z API w ROADMAP.md
   - from_opf(opf_xml: bytes) -> Metadata - parsuje OPF
   - to_opf(existing_opf: bytes) -> bytes - aktualizuje istniejący OPF zachowując inne elementy
   - Używaj lxml jeśli dostępne, fallback na xml.etree
   - Obsługa wielu autorów (<dc:creator> × N)
   - Pełne wsparcie UTF-8 (polskie znaki!)
3. Rozszerz klasę Epub o property .metadata:
   - Getter: parsuje OPF i zwraca Metadata
   - Setter: przyjmuje Metadata, aktualizuje OPF, zapisuje
4. Utwórz tests/test_metadata.py:
   - Test odczytu z fixture
   - Test edycji + zapisu
   - Test polskich znaków (Ąęłżźć)
   - Test wielu autorów
   - Test że inne elementy OPF (manifest, spine) NIE są modyfikowane przy zmianie metadanych
5. Dodaj lxml do pyproject.toml jako dependency (nie optional)
6. Uruchom testy, lint, mypy.
7. Commit: "feat(core): Dublin Core metadata read/write"
8. PR, ale nie merguj jeszcze - po tym etapie chcę zrobić tag v0.1.0-alpha lokalnie żeby sprawdzić że biblioteka jest użyteczna.

Po Twoim raporcie wykonam ręcznie:
git tag v0.1.0-alpha
git push origin v0.1.0-alpha
```

---

## 🔍 Etap 3 — Detection i Config

```
Realizujemy Etap 3 z ROADMAP.md - "Wykrywanie narzędzi".

Wykonaj:

1. Gałąź: feature/stage-3-detection
2. Utwórz src/epubforge/core/detection.py zgodnie z API w ROADMAP.md:
   - dataclass Tool (frozen)
   - Klasa Tools z metodami static dla każdego narzędzia
   - Detekcja na Windows: typowe ścieżki Program Files, AppData, PATH
   - Detekcja na Linux: which, /usr/bin, /opt
   - Detekcja Calibre KFX plugin: szukaj KFX_Output.zip lub KFX Output.* w katalogu wtyczek Calibre
   - Wykrywanie wersji przez subprocess --version (z timeout!)
3. Utwórz src/epubforge/core/config.py:
   - load_config(path: Path) -> dict
   - save_config(path: Path, config: dict) -> None
   - default_config_path() - zwraca lokalizację config.json (obok exe lub w ~/.config/epubforge/)
   - Atomic write (najpierw temp, potem rename)
4. Utwórz tests/test_detection.py z mockami (monkeypatch shutil.which, Path.exists)
5. Utwórz tests/test_config.py - test roundtrip zapisu/odczytu
6. Uruchom testy, lint, mypy.
7. Commit: "feat(core): tool detection and config persistence"

WAŻNE: Implementuj funkcje detekcji idempotentnie - można je wywołać wielokrotnie bez efektów ubocznych.
Cache wyników w config.json, ale z flagą "last_detected" timestamp - re-detekcja po 7 dniach.
```

---

## 🔄 Etap 4 — Konwerter → EPUB

```
Realizujemy Etap 4 z ROADMAP.md - "Konwerter → EPUB".

Wykonaj:

1. Gałąź: feature/stage-4-converter
2. Utwórz src/epubforge/converters/__init__.py i src/epubforge/converters/to_epub.py
3. Zgodnie z API w ROADMAP.md:
   - dataclass ConvertOptions
   - dataclass ConversionResult (success: bool, output_path: Path, log: str, engine: str)
   - funkcja to_epub(source, target, options, engine="auto")
4. Implementacja:
   - engine="auto": jeśli .pdf → Calibre, w przeciwnym razie Pandoc (lub Calibre jeśli Pandoc niedostępny)
   - Pandoc subprocess z proper encoding, capture_output
   - Calibre ebook-convert subprocess
   - Metadane przekazywane jako argumenty CLI (--metadata title=... dla Pandoc, --title ... dla Calibre)
   - Cover image: --epub-cover-image (Pandoc), --cover (Calibre)
   - Logi z procesu zapisywane w ConversionResult.log
5. Obsługa błędów:
   - Brak narzędzia → ConverterNotFoundError z czytelnym komunikatem
   - Konwersja zwraca non-zero → ConversionError z fragmentem logu
6. Utwórz tests/test_converter.py:
   - Mock subprocess (subprocess.run)
   - Testy budowania komend dla różnych formatów
   - Test fallback: PDF → Calibre nawet gdy Pandoc dostępny
7. Dodaj CLI command: epubforge convert SOURCE TARGET [--engine pandoc|calibre|auto]
   - W src/epubforge/cli/convert.py
   - Integracja z głównym entry point w __main__.py (argparse subcommand)
8. Commit: "feat(converters): EPUB conversion via Pandoc/Calibre"

NIE rób testów integracyjnych z prawdziwym Pandoc/Calibre w CI - tylko mocki.
```

---

## ✂️ Etap 5 — Hyphenation

```
Realizujemy Etap 5 z ROADMAP.md - "Dzielenie wyrazów".

Wykonaj:

1. Gałąź: feature/stage-5-hyphenation
2. Dodaj do pyproject.toml: pyphen >= 0.15
3. Utwórz src/epubforge/fixers/__init__.py i src/epubforge/fixers/hyphenator.py
4. API: zgodnie z ROADMAP.md - UWAGA: HyphenationOptions ma pole method: Literal["soft-hyphen", "css"]
5. Implementacja DWÓCH metod (przeczytaj sekcję "kompromis metod" w ROADMAP.md Etap 5):
   - method="soft-hyphen": wstawia \u00ad w słowach przez pyphen
     * Iteruj po plikach HTML/XHTML (przez Epub.manifest)
     * Pomijaj tagi: code, pre, kbd, samp, var, tt
     * Pomijaj h1-h3 jeśli skip_headers=True
     * Słowa krótsze niż min_word_length pomijane
     * Idempotentność: pomijaj słowa już zawierające \u00ad
   - method="css": wstrzykuje regułę CSS hyphens: auto do arkusza (NIE modyfikuje tekstu)
6. WAŻNE: docstring HyphenationOptions musi zawierać ostrzeżenie że soft-hyphen psuje
   słownik/wyszukiwarkę na czytnikach Kindle. To świadomy kompromis - użytkownik wybiera.
7. Tests/test_hyphenator.py:
   - Test soft-hyphen: polski tekst hyphenowany
   - Test css: reguła wstrzyknięta, tekst NIE zmieniony
   - Test skip tags i skip headers
   - Test idempotentności
   - Test innych języków: en, de
8. Dodaj CLI: epubforge hyphenate FILE [--lang pl] [--method soft-hyphen|css] [--skip-headers]
9. Commit: "feat(fixers): hyphenation with soft-hyphen and CSS methods"
```

---

## 🎨 Etap 6 — CSS Fixer

```
Realizujemy Etap 6 z ROADMAP.md - "CSS Fixer".

Wykonaj:

1. Gałąź: feature/stage-6-css-fixer
2. Dodaj do pyproject.toml: tinycss2 >= 1.3 (NIE cssutils - jest przestarzały i hałasuje przy CSS3)
3. Utwórz src/epubforge/fixers/css_fixer.py
4. API zgodnie z ROADMAP.md
5. Implementacja każdej opcji jako osobnej funkcji, używając tinycss2 do parsowania:
   - _remove_colors(css: str) -> str
   - _remove_fonts(epub: Epub, css: str) -> str  (też usuwa fizyczne pliki fontów!)
   - _inject_reset(css: str) -> str
   - _replace_justify(css: str) -> str
   - _inject_book_margin(css: str, px: int) -> str
   - _skip_hyphenation_headers(css: str) -> str
   WAŻNE: zachowuj nieznane reguły (@supports, calc(), --zmienne) BEZ ZMIAN.
   Modyfikuj tylko to, co jawnie celujesz. tinycss2 operuje na tokenach:
   rules = tinycss2.parse_stylesheet(css, skip_whitespace=True); ...; tinycss2.serialize(rules)
6. Funkcja główna fix_css iteruje po opcjach i aplikuje
7. Tests/test_css_fixer.py - test każdej opcji osobno + kombinacje +
   TEST że nowoczesny CSS3 (--var, @supports, calc()) NIE jest uszkadzany
8. Dodaj CLI: epubforge fix FILE [--remove-colors] [--replace-justify] [--book-margin N] ...
9. Commit: "feat(fixers): CSS normalization via tinycss2"

Po tym etapie zrób stage gate v0.5.0 - lokalnie:
git tag v0.5.0
Sprawdzimy że biblioteka i CLI są kompletne przed dodaniem GUI.
```

---

## 📚 Etap 7 — KFX

```
Realizujemy Etap 7 z ROADMAP.md - "EPUB → KFX".

WAŻNE: Główny silnik to Calibre + wtyczka KFX Output (NIE Kindle Previewer!).
Calibre jest sprawdzony i mniej wrażliwy na formatowanie EPUB.
Kindle Previewer 3 oznaczamy jako EXPERIMENTAL z ostrzeżeniem.

Wykonaj:

1. Gałąź: feature/stage-7-kfx
2. Utwórz src/epubforge/converters/to_kfx.py
3. API zgodnie z ROADMAP.md, ale:
   - engine="auto" -> "calibre" jeśli wtyczka KFX wykryta, inaczej "kindle-previewer"
   - engine="kindle-previewer" -> dodaj warning do ConversionResult.log
4. Implementacja Calibre:
   - subprocess: ebook-convert source.epub target.kfx
   - Wtyczka KFX Output sama wykrywa rozszerzenie
5. Implementacja KP3:
   - subprocess: kindle_previewer.exe -convert source.epub -outdir tempdir
   - Po konwersji: tempdir.rglob("*.kfx") -> przenieś znaleziony plik do target
   - Cleanup tempdir
6. Jeśli fix_epub_first=True:
   - Najpierw fix_css(epub, podstawowe opcje)
   - Dopiero potem konwersja
7. Tests/test_kfx.py - same mocki subprocess
8. CLI: epubforge kfx FILE [--engine calibre|kindle-previewer] [--no-fix]
9. Commit: "feat(converters): EPUB to KFX via Calibre (primary) and Kindle Previewer (experimental)"
```

---

## 🖥️ Etap 8 — GUI Framework

```
Realizujemy Etap 8 z ROADMAP.md - "GUI Framework i widgety".

KONTEKST: Mamy gotową bibliotekę i CLI. Teraz dodajemy GUI.
W poprzednim projekcie GUI było w jednym pliku ~2000 linii - tu rozbijamy na moduły OD POCZĄTKU.

Wykonaj:

1. Gałąź: feature/stage-8-gui-framework
2. Utwórz strukturę src/epubforge/gui/:
   - __init__.py
   - app.py (klasa App)
   - theme.py (DARK/LIGHT dicts + apply_theme)
   - streaming.py (LogStreamer - kolejka thread-safe do tk.Text)
   - widgets/__init__.py
   - widgets/path_entry.py (PathEntry)
   - widgets/file_list.py (FileList z opcjonalnym D&D)
   - widgets/toggle.py (Toggle - styled checkbox)
   - widgets/section.py (Section - ttk.LabelFrame opakowany)
   - widgets/tooltip.py (Tooltip - hover help)
3. Klasa App:
   - Główne okno tkinter
   - ttk.Notebook z jedną zakładką placeholder "Welcome"
   - Pasek statusu u dołu z wykrytymi narzędziami (epubforge.core.detection)
   - Górny pasek: tytuł + przełącznik motywu
   - Wczytuje config.json przy starcie, zapisuje przy zamknięciu
4. theme.py:
   - DARK = {"bg": "#1e2028", "bg2": "#252830", ...}
   - LIGHT = {"bg": "#ffffff", "bg2": "#f5f5f5", ...}
   - apply_theme(root, theme_dict) - rekurencyjnie po wszystkich widgetach
5. Dodaj entry point GUI w pyproject.toml (UWAGA: sekcja [project.gui-scripts], NIE [project.scripts] — gui-scripts ukrywa konsolę na Windows):
   [project.gui-scripts]
   epubforge-gui = "epubforge.gui.app:main"
   (ten wpis prawdopodobnie już istnieje w pyproject.toml - sprawdź i NIE przenoś go do [project.scripts])
6. Tests/gui/test_widgets.py - testuje że widgety tworzą się bez błędów (xvfb-run w CI)
7. Update .github/workflows/test.yml - dodaj xvfb dla testów GUI
8. Commit: "feat(gui): application framework with theme and reusable widgets"

KOD REUSE: Sprawdź REUSABLE_CODE.md sekcja "Widgets" - tam są gotowe szablony klas PathEntry, FileList, Toggle, Tooltip ze starego projektu. Wykorzystaj je jako punkt startowy ale zrefaktoryzuj zgodnie z nową strukturą modułową.
```

---

## 📑 Etap 9 — GUI: Zakładka Metadane

```
Realizujemy Etap 9 z ROADMAP.md - "GUI: Zakładka Metadane".

⚠️ NAJPIERW przeczytaj aktualny stan modułów core których będziesz używać:
- src/epubforge/core/metadata.py (kształt klasy Metadata - pola, typy)
- src/epubforge/core/epub.py (API klasy Epub)
- src/epubforge/core/detection.py (klasa Tools)
NIE twórz mocków ani duplikatów tych klas - importuj i używaj prawdziwych. Jeśli czegoś brakuje w API core, zgłoś to zanim zaczniesz GUI.

Wykonaj:

1. Gałąź: feature/stage-9-gui-metadata
2. Utwórz src/epubforge/gui/tabs/__init__.py
3. Utwórz src/epubforge/gui/tabs/metadata.py:
   - Klasa MetadataTab(ttk.Frame)
   - Lewa strona: FileList (lista plików EPUB w wybranym folderze)
   - Prawa strona: formularz z polami Dublin Core (tytuł, autorzy, język, wydawca, data, ISBN, opis, tematy)
   - Po wybraniu pliku z listy -> wczytaj metadane przez epubforge.core.Epub.metadata
   - Przycisk "Zapisz" -> wywołaj setter (z automatycznym backupem)
   - Przyciski: "Sigil", "Calibre Editor", "Calibre Viewer" (uruchamiają zewnętrzne programy przez subprocess.Popen)
4. Zintegruj zakładkę w app.py (zamiast placeholder "Welcome")
5. Tests/gui/test_metadata_tab.py - test że tab się tworzy, mocki dla Epub.metadata
6. Commit: "feat(gui): metadata editing tab with file browser"

UWAGA: Przyciski Sigil/Calibre uruchamiają zewnętrzne aplikacje. Ścieżki bierz z epubforge.core.detection.Tools.
Jeśli narzędzie niedostępne -> przycisk wyszarzony z tooltipem "Nie wykryto Sigil" itp.
```

---

## 🔄 Etap 10 — GUI: Konwerter

```
Realizujemy Etap 10 z ROADMAP.md - "GUI: Konwerter".

⚠️ NAJPIERW przeczytaj: src/epubforge/converters/to_epub.py (ConvertOptions, to_epub, obsługiwane formaty) i src/epubforge/core/metadata.py. Używaj prawdziwych klas, nie twórz mocków.

1. Gałąź: feature/stage-10-gui-converter
2. Utwórz src/epubforge/gui/tabs/converter.py:
   - Klasa ConverterTab(ttk.Frame)
   - FileList z plikami wejściowymi (rozszerzenia z epubforge.converters)
   - Pola metadanych (tytuł, autor, język - dropdown)
   - PathEntry dla okładki
   - Wybór silnika: radio "Auto" / "Pandoc" / "Calibre"
   - PathEntry dla folderu wyjściowego
   - Przycisk "Konwertuj" - uruchamia konwersję w wątku, streamuje log
3. PDF za jawnym potwierdzeniem: gdy użytkownik doda plik .pdf, pokaż messagebox.askyesno
   z ostrzeżeniem: "Konwersja PDF → EPUB jest eksperymentalna. Calibre wstawia sztywne
   marginesy i może łamać akapity. Najlepsze wyniki dla prostych PDF tekstowych. Kontynuować?"
   Dopiero po potwierdzeniu dodaj plik do listy.
4. Wykorzystaj LogStreamer z gui/streaming.py
5. Dodaj zakładkę do app.py
6. Commit: "feat(gui): converter tab for format → EPUB"
```

---

## ✂️ Etap 11 — GUI: Fixer

```
Realizujemy Etap 11 z ROADMAP.md - "GUI: Fixer".

⚠️ NAJPIERW przeczytaj: src/epubforge/fixers/hyphenator.py (HyphenationOptions z polem method!) i src/epubforge/fixers/css_fixer.py (CssFixOptions). Używaj prawdziwych klas.

1. Gałąź: feature/stage-11-gui-fixer
2. Utwórz src/epubforge/gui/tabs/fixer.py:
   - FileList z plikami EPUB
   - Sekcja "Hyphenation": Toggle "Włącz", dropdown języka, radio metoda (soft-hyphen/css), Toggle "Pomiń nagłówki"
   - Przy wyborze soft-hyphen pokaż ostrzeżenie (label) o psuciu słownika na czytniku
   - Sekcja "CSS Fixer": Toggle dla każdej opcji z CssFixOptions (remove-colors, replace-justify itp.)
   - Spinner dla book-margin (px)
   - Przycisk "Napraw" - uruchamia w wątku
   - Po sukcesie - przycisk "Podgląd w Calibre Viewer"
3. Commit: "feat(gui): EPUB fixer tab (hyphenation + CSS)"
```

---

## 📚 Etap 12 — GUI: KFX

```
Realizujemy Etap 12 z ROADMAP.md - "GUI: KFX".

⚠️ NAJPIERW przeczytaj: src/epubforge/converters/to_kfx.py (KfxOptions, to_kfx) i src/epubforge/core/detection.py. Używaj prawdziwych klas.

1. Gałąź: feature/stage-12-gui-kfx
2. Utwórz src/epubforge/gui/tabs/kfx.py:
   - FileList z plikami EPUB
   - Sekcja "Silnik konwersji":
     - Radio "Calibre + wtyczka KFX" (zaznaczone domyślnie, label "ZALECANE")
     - Radio "Kindle Previewer 3" (label "EKSPERYMENTALNE - wrażliwe na formatowanie")
   - Toggle "Napraw EPUB przed konwersją" (domyślnie ON)
   - PathEntry folderu wyjściowego
   - ttk.Progressbar dla batch processing
3. Jeśli wybrano KP3 - pokaż ostrzeżenie w polu tekstowym z poradami nt. formatowania
4. Commit: "feat(gui): KFX conversion tab"
```

---

## 🏗️ Etap 13 — Build pipeline

```
Realizujemy Etap 13 z ROADMAP.md - "Build pipeline".

PAMIĘTAJ O DLL CONFLICT - opisane w CLAUDE.md sekcja "Pułapki".

Wykonaj:

1. Gałąź: feature/stage-13-build
2. Utwórz build/create_icon.py - generator icon.ico z Pillow (gradient + litera "ε" lub stylizowana książka)
3. Utwórz build/epubforge.spec dla PyInstaller:
   - Single-file exe
   - console=False (GUI app)
   - icon=icon.ico
   - Hidden imports: tkinter, lxml, pyphen, tinycss2
   - WAŻNE - tkinterdnd2: dołącz natywne binaria tkdnd, inaczej .exe wywala się z "can't find package tkdnd":
       import tkinterdnd2, os
       tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), 'tkdnd')
       datas += [(tkdnd_dir, 'tkinterdnd2/tkdnd')]
     (alternatywnie flaga --collect-all tkinterdnd2)
   - Excludes: matplotlib, numpy, scipy, PIL.tests (oszczędność miejsca)
   - Datas: src/epubforge/gui/assets/* (jeśli są)
4. Utwórz build/build.bat dla lokalnego buildu Windows
5. Utwórz .github/workflows/build.yml:
   - Trigger: tag v*
   - Job: windows-latest
   - Steps: setup-python, pip install, pyinstaller, upload-artifact, release
6. Test buildu LOKALNIE:
   - Linux: niewykonalny (PyInstaller potrzebuje target OS)
   - Windows: build.bat -> dist/epubforge.exe
7. Commit: "feat(build): PyInstaller config and GitHub Actions release"

DODAJ DO CLAUDE.md sekcję "Build" z pułapkami i workaroundami.
```

---

## 📖 Etap 14 — Docs i Release v1.0

```
Realizujemy Etap 14 z ROADMAP.md - "Dokumentacja i Release v1.0".

Wykonaj:

1. Gałąź: feature/stage-14-docs
2. Zaktualizuj README.md:
   - Sekcja "Features" z aktualną listą funkcji
   - Sekcja "Installation" (pip install epubforge, lub pobranie .exe)
   - Sekcja "Quick Start" - przykład CLI
   - Screenshots GUI (placeholder - dodam ręcznie)
   - Badge: build status, license, version, python versions
3. Utwórz docs/user-guide.md - przewodnik dla użytkownika końcowego
4. Utwórz docs/api-reference.md - przykłady użycia biblioteki w kodzie Python
5. Utwórz CHANGELOG.md zgodnie z Keep a Changelog:
   - [Unreleased]
   - [1.0.0] - YYYY-MM-DD - z listą funkcji
6. Dodaj pdoc do dev dependencies w pyproject.toml
7. Workflow .github/workflows/docs.yml - generuje docs przy push do main, deploy do gh-pages
8. Commit: "docs: comprehensive v1.0 documentation"
9. Po merge PR - zrób ostatnie kroki:
   - git tag v1.0.0
   - git push origin v1.0.0
   - GitHub Actions zbuduje exe i utworzy Release

GRATULACJE z mojej strony :)
```

---

## 🆘 Prompty pomocnicze

### Naprawa testów po Twoich zmianach
```
Testy ostatniego etapu nie przechodzą. Uruchom pytest, zobacz co się dzieje, popraw kod (NIE testy, chyba że są błędne) i potwierdź że wszystko jest zielone.
```

### Refactor pojedynczego modułu
```
Plik src/epubforge/MODUŁ.py rozrasta się. Przeanalizuj go i zaproponuj podział na mniejsze moduły. Pokaż diagram zależności PRZED zmianami w kodzie - chcę zatwierdzić plan.
```

### Aktualizacja zależności
```
Sprawdź czy są nowsze wersje zależności w pyproject.toml. Jeśli tak - zaktualizuj, uruchom testy, zobacz czy nic się nie zepsuło. Utwórz gałąź chore/bump-deps.
```

### Naprawa CI
```
GitHub Actions failuje - sprawdź logi (gh run list, gh run view). Zdiagnozuj i napraw. Pamiętaj że Linux CI nie ma displayu - testy GUI wymagają xvfb-run.
```

### Code review przed merge
```
Przejrzyj zmiany w bieżącej gałęzi (git diff main). Zwróć uwagę na:
- Pokrycie testami nowego kodu
- Brakujące docstringi
- Typy w funkcjach publicznych
- Konwencja nazw (snake_case dla funkcji, PascalCase dla klas)
- Komentarze po polsku
Zgłoś problemy zanim zaproponuję PR.
```

---

## 🎬 Mistrzowski prompt na rozpoczęcie pracy

Jeśli wracasz po przerwie i nie wiesz od czego zacząć:

```
Wracam do pracy nad EpubForge. Przeczytaj:
- ROADMAP.md (gdzie jesteśmy w planie)
- git log --oneline -20 (co już zrobione)
- git status (czy jakieś zmiany lokalne)
- gh pr list (otwarte PR-y)

Podsumuj stan projektu i zaproponuj następny krok zgodny z ROADMAP.md.
Nie rób żadnych zmian dopóki nie potwierdzę.
```
