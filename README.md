# 📚 EpubForge

> Modern, modular toolkit for EPUB files — validate, fix, convert, hyphenate.

[![Tests](https://github.com/chodzkos/epubforge/actions/workflows/test.yml/badge.svg)](https://github.com/chodzkos/epubforge/actions/workflows/test.yml)
[![Build](https://github.com/chodzkos/epubforge/actions/workflows/build.yml/badge.svg)](https://github.com/chodzkos/epubforge/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/chodzkos/epubforge?sort=semver)](https://github.com/chodzkos/epubforge/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## ✅ Status projektu

> **Wersja 1.0 — wszystkie funkcje z [ROADMAP.md](ROADMAP.md) ukończone.**

| Funkcja | Status |
|---|---|
| Klasa `Epub` (odczyt/zapis) | ✅ |
| Metadane Dublin Core (+ seria/tom) | ✅ |
| Wykrywanie narzędzi | ✅ |
| Konwersja → EPUB | ✅ |
| Hyphenacja | ✅ |
| CSS Fixer | ✅ |
| KFX / MOBI / AZW3 | ✅ |
| GUI (motyw jasny/ciemny) | ✅ |
| Build: portable `.exe` + instalator | ✅ |

*Pełna historia zmian: [CHANGELOG.md](CHANGELOG.md).*

---

## ✨ Funkcje

- **📖 Library API** — czysty interfejs Python do pracy z plikami EPUB
- **⌨️ CLI** — `epubforge convert/fix/meta/kfx ...` z linii poleceń
- **🖥️ GUI** — desktopowa aplikacja z motywem jasnym i ciemnym
- **🔄 Konwersja** TXT / DOCX / HTML / MD / ODT / RTF / PDF → EPUB
- **📚 Eksport Kindle** — EPUB → KFX / MOBI / AZW3 (Calibre zalecane; KP3/kindlegen opcjonalnie)
- **✂️ Hyphenation** — dzielenie wyrazów dla 50+ języków
- **🎨 CSS Fixer** — czyszczenie kolorów, fontów, justify, marginesy
- **🏷️ Metadata** — pełna edycja Dublin Core + seria/tom (Calibre i EPUB 3)
- **🔍 Auto-detekcja** — Pandoc, Calibre, Sigil, Kindle Previewer, kindlegen

---

## 🚀 Quick Start

### Z PyPI (po wydaniu v1.0)
```bash
pip install epubforge
```

### Ze źródeł
```bash
git clone https://github.com/chodzkos/epubforge
cd epubforge
pip install -e ".[dev]"
```

### Windows (bez instalacji Pythona)
Pobierz z [Releases](https://github.com/chodzkos/epubforge/releases) jeden z dwóch wariantów:

- **`epubforge.exe`** — wersja **portable**: jeden plik, uruchamiasz bez instalacji.
- **`epubforge-setup.exe`** — **instalator** (Inno Setup): skrót w menu Start, opcjonalnie
  na pulpicie, odinstalowanie przez „Dodaj/usuń programy".

Build lokalny (Windows): `build\build.bat` — wybiera Pythona 3.10+ przez launcher
`py`, przygotowuje zależności, sprawdza środowisko i tworzy pliki w `build\dist\`.
Instalator powstaje tylko wtedy, gdy zainstalowany jest
[Inno Setup](https://jrsoftware.org/isinfo.php) (`ISCC.exe` w `PATH` albo
standardowy katalog `Program Files`).

---

## 📖 Użycie

### CLI

```bash
# Konwersja
epubforge convert book.docx book.epub
epubforge convert input.pdf output.epub --engine calibre

# Naprawa EPUB
epubforge fix book.epub --remove-colors --replace-justify

# Hyphenacja
epubforge hyphenate book.epub --lang pl --skip-headers

# Edycja metadanych
epubforge meta book.epub --title "Nowy tytuł" --author "Jan Kowalski"

# Konwersja do KFX
epubforge kfx book.epub --engine calibre
```

### Python API

```python
from epubforge import Epub
from epubforge.fixers import fix_css, hyphenate, CssFixOptions, HyphenationOptions

with Epub("book.epub") as ebook:
    # Edycja metadanych
    meta = ebook.metadata
    meta.title = "Nowy tytuł"
    meta.creators = ["Jan Kowalski", "Anna Nowak"]
    ebook.metadata = meta
    
    # Naprawa CSS
    fix_css(ebook, CssFixOptions(
        remove_colors=True,
        replace_justify="left",
        inject_book_margin_px=20
    ))
    
    # Hyphenacja
    hyphenate(ebook, HyphenationOptions(language="pl"))
    
    ebook.save()  # zapisuje + tworzy backup
```

### GUI
```bash
epubforge-gui
```

Motyw: przycisk **Motyw** w górnym pasku (Automatyczny / Jasny / Ciemny).
„Automatyczny" podąża za ustawieniem systemu. Na Windows pasek tytułu również
zmienia kolor. W trybie ciemnym używane są spójne ciemne okna **Otwórz/Zapisz**
(dialogi Qt); w trybie jasnym — natywne dialogi systemu.

---

## 📸 Zrzuty ekranu

<!-- TODO: dodać zrzuty ekranu GUI (motyw jasny i ciemny). -->
> _Zrzuty ekranu zostaną dodane._

| Motyw jasny | Motyw ciemny |
|---|---|
| _(placeholder)_ | _(placeholder)_ |

---

## 📚 Dokumentacja

- [Przewodnik użytkownika](docs/user-guide.md) — instalacja, GUI, CLI krok po kroku
- [API reference](docs/api-reference.md) — użycie biblioteki w kodzie Python
- [CHANGELOG](CHANGELOG.md) — historia zmian

---

## 📋 Wymagania

### Obsługiwane formaty wejściowe (konwersja → EPUB)

| Format | Silnik | Jakość | Uwagi |
|---|---|---|---|
| TXT | Pandoc | dobra | prosty tekst |
| Markdown | Pandoc | bardzo dobra | natywne wsparcie |
| DOCX | Pandoc | dobra | zachowuje style |
| HTML | Pandoc | bardzo dobra | |
| ODT | Pandoc | dobra | |
| RTF | Pandoc | średnia | |
| **PDF** | Calibre | **eksperymentalna** | tylko PDF tekstowe; skany wymagają OCR (planowane) |
| FB2 / LIT | Calibre | dobra | |

> ⚠️ **PDF → EPUB jest eksperymentalne.** Najlepsze wyniki dla PDF z tekstem (nie skanów).
> PDF wielokolumnowe, naukowe i skany dają słabą jakość. OCR planowany w przyszłych wersjach.

### Konwersja EPUB → KFX

| Silnik | Status | Uwagi |
|---|---|---|
| **Calibre + wtyczka KFX Output** | zalecany | sprawdzony, mniej wrażliwy na formatowanie |
| Kindle Previewer 3 | eksperymentalny | wrażliwy na nieidealne formatowanie EPUB |

### Do uruchomienia
- Python 3.10+ (jeśli nie używasz .exe)
- Opcjonalnie do pełnej funkcjonalności:
  - [Pandoc](https://pandoc.org/installing.html) — konwersja → EPUB
  - [Calibre](https://calibre-ebook.com) — fallback + KFX
  - [Sigil](https://sigil-ebook.com) — edytor EPUB
  - [Kindle Previewer 3](https://www.amazon.com/gp/feature.html?ie=UTF8&docId=1000765261) — KFX (experimental)

### Do developmentu
- Python 3.10+
- `pip install -e ".[dev]"`

---

## 🛠️ Development

```bash
# Setup
git clone https://github.com/chodzkos/epubforge
cd epubforge
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]"

# Testy
pytest

# Lint
ruff check .

# Type check
mypy src/

# Wszystko naraz
pre-commit run --all-files
```

Zobacz `ROADMAP.md` i `CLAUDE.md` po więcej szczegółów technicznych.

---

## 📜 Licencja

MIT © 2026 chodzkos

---

## 🙏 Podziękowania

Projekt powstał jako kontynuacja prac nad [epubQTools](https://github.com/quiris11/epubQTools) (Robert Błaut) — z czystym przepisaniem od zera i nowoczesną architekturą.
