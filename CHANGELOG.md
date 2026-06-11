# Changelog

Wszystkie istotne zmiany w projekcie dokumentowane są w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

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
