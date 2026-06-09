# Changelog

Wszystkie istotne zmiany w projekcie dokumentowane są w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

### Added
- Struktura projektu i konfiguracja narzędzi developerskich (pyproject.toml, ruff, mypy, pytest)
- CI/CD przez GitHub Actions (testy na Linux/Windows/macOS × Python 3.10-3.12)
- Pre-commit hooks (ruff, mypy, podstawowe sprawdzenia)
- Dokumentacja: README, ROADMAP, CLAUDE.md, PROMPTS, FEATURES

### Decyzje techniczne (na podstawie analiz)
- CSS: `tinycss2` zamiast `cssutils` (nowocześniejszy, nie psuje CSS3)
- Zapis EPUB: kopiowanie strumieniowe ze źródła zamiast ładowania całości do RAM
- Hyphenacja: dwie metody (soft-hyphen / CSS) z ostrzeżeniem o kompromisie Kindle
- PyInstaller: jawny hook dla natywnych binariów tkdnd (drag&drop)
- PDF → EPUB: oznaczone jako eksperymentalne, za potwierdzeniem w GUI

### Planowane (zgodnie z ROADMAP.md)
- Etap 1: Klasa `Epub` (odczyt/zapis z poprawną obsługą mimetype)
- Etap 2: Metadane Dublin Core
- Etap 3: Wykrywanie narzędzi zewnętrznych
- Etap 4: Konwersja → EPUB (Pandoc/Calibre)
- Etap 5: Hyphenacja (pyphen)
- Etap 6: CSS Fixer
- Etap 7: Konwersja → KFX
- Etap 8-12: GUI (tkinter)
- Etap 13: Build pipeline (PyInstaller)
- Etap 14: Dokumentacja v1.0

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

[Unreleased]: https://github.com/chodzkos/epubforge/commits/main
