# 📚 EpubForge

> Modern, modular toolkit for EPUB files — validate, fix, convert, hyphenate.

[![Tests](https://github.com/chodzkos/epubforge/actions/workflows/test.yml/badge.svg)](https://github.com/chodzkos/epubforge/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## ✨ Funkcje

- **📖 Library API** — czysty interfejs Python do pracy z plikami EPUB
- **⌨️ CLI** — `epubforge convert/fix/meta/kfx ...` z linii poleceń
- **🖥️ GUI** — desktopowa aplikacja z motywem jasnym i ciemnym
- **🔄 Konwersja** TXT / DOCX / HTML / MD / ODT / RTF / PDF → EPUB
- **📚 KFX** — EPUB → KFX przez Calibre (zalecane) lub Kindle Previewer 3
- **✂️ Hyphenation** — dzielenie wyrazów dla 50+ języków
- **🎨 CSS Fixer** — czyszczenie kolorów, fontów, justify
- **🏷️ Metadata** — pełna edycja Dublin Core
- **🔍 Auto-detekcja** — Pandoc, Calibre, Sigil, Kindle Previewer

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

### Skompilowany .exe (Windows)
Pobierz z [Releases](https://github.com/chodzkos/epubforge/releases) — bez instalacji Pythona.

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

---

## 📋 Wymagania

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
