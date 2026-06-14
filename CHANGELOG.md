# Changelog

Wszystkie istotne zmiany w projekcie dokumentowane są w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

### Added
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
