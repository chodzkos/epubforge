# 📚 EpubForge

> Modern, modular toolkit for EPUB files — validate, fix, convert, hyphenate.

[![Tests](https://github.com/chodzkos/epubforge/actions/workflows/test.yml/badge.svg)](https://github.com/chodzkos/epubforge/actions/workflows/test.yml)
[![Build](https://github.com/chodzkos/epubforge/actions/workflows/build.yml/badge.svg)](https://github.com/chodzkos/epubforge/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/chodzkos/epubforge?sort=semver)](https://github.com/chodzkos/epubforge/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## ✅ Status projektu

> **Wersja 2.2.0 — brama v2.2 (Etapy 19–21 roadmapy v3) domknięta.**
> (2.0 = migracja GUI na PySide6 + wydzielenie rdzenia do
> [chodzkos-gui-kit](https://github.com/chodzkos/gui-kit); 2.1–2.2 = typografia PL,
> batch/dry-run, receptury, anulowanie/postęp, optymalizacja obrazów, szukaj/zamień;
> pełna historia w [CHANGELOG.md](CHANGELOG.md)).

| Funkcja | Status |
|---|---|
| Klasa `Epub` (odczyt/zapis) | ✅ |
| Metadane Dublin Core (+ seria/tom) | ✅ |
| Pobieranie metadanych po ISBN (BN / Open Library / Google Books) | ✅ |
| Pobieranie metadanych z LubimyCzytac + wyszukiwanie bez ISBN (tytuł/autor) | ✅ |
| Wykrywanie narzędzi | ✅ |
| Konwersja → EPUB | ✅ |
| Hyphenacja | ✅ |
| Typografia PL (cudzysłowy, pauzy, sieroty) | ✅ |
| CSS Fixer | ✅ |
| Presety CSS (wbudowane + własne) | ✅ |
| Optymalizacja obrazów (skalowanie/rekompresja) | ✅ |
| Edytor wewnętrzny EPUB (podgląd + edycja) | ✅ |
| Szukaj/Zamień w całym EPUB | ✅ |
| Walidacja EpubCheck (klikalne błędy) | ✅ |
| Spis treści (generator + edytor drzewa) | ✅ |
| Statystyki książki (raport HTML) | ✅ |
| KFX / MOBI / AZW3 | ✅ |
| Receptury TOML (pipeline) | ✅ |
| Batch CLI + `--dry-run` | ✅ |
| Anulowanie i postęp długich operacji | ✅ |
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
- **🧩 Receptury TOML** — zapisane pipeline'y `fix_css → typography → hyphenate → export` dla CLI i GUI
- **✂️ Hyphenation** — dzielenie wyrazów dla 50+ języków
- **🇵🇱 Typografia** — cudzysłowy typograficzne (pl/en/de), pauzy w dialogach, wielokropek, twarde spacje po sierotach
- **🖼️ Optymalizacja obrazów** — skalowanie, rekompresja JPEG/PNG i skala szarości pod e-ink (`pip install ".[images]"`)
- **🔤 Subsetting fontów** — przycinanie fontów do użytych znaków (zwykle −70…−90% rozmiaru fontu); zachowuje polskie znaki, interpunkcję i efekty hyphenacji (`pip install ".[fonts]"`)
- **🎨 CSS Fixer** — czyszczenie kolorów, fontów, justify, marginesy
- **🎨 Presety CSS** — wbudowane szablony stylów + import własnych (dołącz / zastąp)
- **📝 Edytor wewnętrzny** — przegląd i szybka edycja plików w EPUB z podświetlaniem XML/CSS, przybliżony podgląd HTML (Kod ⇄ Podgląd) + handoff do Sigil/Calibre
- **🔎 Szukaj/Zamień w całym EPUB** — panel w Edytorze (Ctrl+Shift+F): regex, wielkość liter, całe słowa, zakres plik/EPUB; klikalne wyniki i „Zamień wszystkie"
- **🔎 Inspektor CSS** — lista reguł arkusza z podglądem na żywo i edycją reguły (podgląd przybliżony)
- **✅ Walidacja EpubCheck** — raport błędów/ostrzeżeń EPUB; dwuklik błędu skacze do linii w edytorze (wymaga Javy + epubcheck.jar)
- **♿ Audyt dostępności (DAISY Ace)** — raport naruszeń WCAG/EPUB Accessibility w tej samej tabeli co EpubCheck; dwuklik wpisu skacze do pliku. CLI `epubforge a11y` + przycisk „Sprawdź dostępność (Ace)" w zakładce Walidacja (wymaga `npm install -g @daisy/ace`)
- **⬆️ Upgrade EPUB 2 → 3** — modernizacja pakietu: nav.xhtml ze spisu NCX, landmarks z guide, `dcterms:modified`; NCX zostaje (opcja `--drop-ncx`). Dokumentów treści nie rusza. CLI `epubforge upgrade` + przycisk w zakładce Fixer
- **📑 Spis treści** — generowanie z nagłówków (nav.xhtml + toc.ncx), edytor drzewa z drag&drop, wykrywanie i naprawa martwych wpisów
- **📊 Statystyki** — słowa, szac. strony, czas czytania, język i top-słowa + samowystarczalny raport HTML (wykrywanie języka: `pip install ".[stats]"`)
- **🏷️ Metadata** — pełna edycja Dublin Core + seria/tom (Calibre i EPUB 3); przycisk **Pobierz metadane…** wciąga po ISBN wydawcę, rok, liczbę stron i deskryptory przedmiotowe z Biblioteki Narodowej → LubimyCzytac → Open Library → Google Books (wybór pól do nadpisania, nigdy ciche). Bez ISBN — wyszukiwanie po **tytule/autorze** w LubimyCzytac z listą kandydatów (opisy, cykle, kategorie; cache + rate limiter dla grzecznościowego scrapingu)
- **🔍 Auto-detekcja** — Pandoc, pdf2md, DAISY Ace, Calibre, Sigil, Kindle Previewer, kindlegen

---

## 🚀 Quick Start

> **Uwaga:** EpubForge nie jest jeszcze publikowany na PyPI (zależy m.in. od
> `chodzkos-gui-kit` z gita), więc `pip install epubforge` na razie **nie
> działa**. Instaluj ze źródeł albo pobierz build dla Windows (niżej).

### Ze źródeł
```bash
git clone https://github.com/chodzkos/epubforge
cd epubforge
pip install -e ".[dev]"
```

### Windows (bez instalacji Pythona)
Pobierz z [Releases](https://github.com/chodzkos/epubforge/releases) jeden z dwóch wariantów:

- **`epubforge-setup.exe`** — **instalator** (Inno Setup), **rekomendowany**: rozpakowany
  folder (onedir) startuje szybko, dodaje skrót w menu Start, opcjonalnie na pulpicie,
  i odinstalowanie przez „Dodaj/usuń programy".
- **`epubforge.exe`** — wersja **portable**: jeden plik, bez instalacji. Uwaga: przy każdym
  uruchomieniu rozpakowuje się do katalogu tymczasowego, więc **startuje wolniej** (kilka
  sekund) i bywa **fałszywie zgłaszany przez antywirusy**. Config trzyma obok siebie, gdy
  obok `.exe` leży plik `portable.flag` (dołączany do wariantu portable).

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
epubforge convert input.pdf output.epub --engine pdf2md   # zalecany silnik PDF
epubforge convert input.pdf output.epub --engine calibre  # fallback

# Modernizacja pakietu EPUB 2 → EPUB 3
epubforge upgrade book.epub                 # nav.xhtml + landmarks + dcterms (NCX zostaje)
epubforge upgrade book.epub --dry-run       # pokaż plan bez zapisu
epubforge upgrade book.epub --drop-ncx -o out.epub

# Walidacja EpubCheck (wymaga Javy + epubcheck.jar)
epubforge check book.epub                            # raport + kod wyjścia 0/1/2
epubforge check book.epub --json report.json         # pełny raport do pliku
epubforge check book.epub --min-severity warning     # tylko ostrzeżenia i błędy

# Audyt dostępności DAISY Ace (wymaga: npm install -g @daisy/ace)
epubforge a11y book.epub                              # raport + kod wyjścia 0/1/2
epubforge a11y book.epub --json report.json          # pełny raport do pliku
epubforge a11y book.epub --min-severity warning      # tylko ostrzeżenia i błędy

# Spis treści (generowanie z nagłówków, naprawa martwych wpisów)
epubforge toc book.epub --show
epubforge toc book.epub --generate --max-level 3
epubforge toc book.epub --repair --dry-run

# Naprawa EPUB
epubforge fix book.epub --remove-colors --replace-justify
epubforge fix a.epub b.epub c.epub --remove-colors --jobs 3
epubforge fix book.epub --preset reader-friendly --dry-run

# Optymalizacja obrazów (odchudza EPUB pod e-ink; wymaga ".[images]")
epubforge fix book.epub --optimize-images
epubforge fix book.epub --optimize-images --max-px 1000 --jpeg-quality 70 --grayscale

# Subsetting fontów — przytnij fonty do użytych znaków (wymaga ".[fonts]")
epubforge fix book.epub --subset-fonts
epubforge fix book.epub --subset-fonts --dry-run   # delty rozmiarów bez zapisu

# Typografia
epubforge typo book.epub --lang pl
epubforge typo book.epub --lang pl --dry-run --diff-full

# Typografia (cudzysłowy, pauzy, wielokropek, twarde spacje)
epubforge typo book.epub --lang pl                   # pełna typografia PL
epubforge typo book.epub --lang en --no-nbsp-letters # wariant EN bez sierot
epubforge typo book.epub --nbsp-numbers              # dołóż twarde spacje przy liczbach (10 km)

# Presety CSS (gotowe szablony stylów)
epubforge presets list                              # lista presetów
epubforge fix book.epub --preset reader-friendly    # dołącz preset
epubforge fix book.epub --preset dark-oled --preset-mode replace  # zastąp istniejące arkusze

# Hyphenacja
epubforge hyphenate book.epub --lang pl --skip-headers
epubforge hyphenate *.epub --method css --jobs 4 --dry-run

# Receptury TOML (pipeline fixerów + opcjonalny eksport)
epubforge run --list
epubforge run kindle-pl book.epub --out-dir dist
epubforge run czytnik-epub a.epub b.epub --jobs 2
epubforge run moja-receptura.toml book.epub --dry-run --diff-full

# Edycja metadanych
epubforge meta book.epub --title "Nowy tytuł" --author "Jan Kowalski"

# Statystyki książki (+ raport HTML)
epubforge stats book.epub --report stats.html --top 50

# Konwersja do KFX
epubforge kfx book.epub --engine calibre
```

### Batch i dry-run w CLI

`fix`, `hyphenate` i `typo` przyjmują wiele plików naraz oraz `--jobs N` do pracy
równoległej. `--dry-run` wykonuje fixery w pamięci i pokazuje unified diff dla
plików tekstowych (domyślnie skrócony; `--diff-full` pokazuje całość), a dla
binarnych wpisów tylko deltę rozmiaru. Presety CSS są aplikowane przez
`fix --preset`, więc korzystają z tego samego batcha i dry-runu.

### Receptury TOML

Receptura łączy kilka kroków w jeden pipeline. Kroki fixerów działają na jednym
otwartym EPUB-ie i zapisują plik raz na końcu, a kroki eksportu pracują dopiero
na zapisanym pliku. Wbudowane receptury:

- `kindle-pl` — CSS fixer, typografia PL, hyphenacja PL, eksport do MOBI.
- `czytnik-epub` — CSS fixer, typografia PL i preset `reader-friendly`.

Dostępne kroki fixerów: `fix_css`, `typography`, `hyphenate`, `optimize_images`,
`apply_preset`; kroki eksportu: `to_mobi`, `to_kfx`. Własne receptury trzymaj w
`config_dir()/recipes/*.toml`; receptura użytkownika o tej samej nazwie przykrywa wbudowaną.

```toml
name = "kindle-pl"
description = "Przygotowanie polskiego EPUB-a pod Kindle (MOBI)"

[[steps]]
op = "fix_css"
[steps.options]
remove_colors = true
replace_justify = "left"

[[steps]]
op = "typography"
[steps.options]
language = "pl"

[[steps]]
op = "hyphenate"
[steps.options]
language = "pl"

[[steps]]
op = "to_mobi"
[steps.options]
fmt = "mobi"
fix_epub_first = false
```

### Presety CSS

Gotowe szablony stylów dołączane do EPUB-a. Tryb `append` (domyślny) dodaje arkusz obok
istniejących; `replace` usuwa istniejące arkusze i wstawia tylko preset.

| ID | Opis | Uwagi |
|---|---|---|
| `reader-friendly` | Wygodna interlinia, wcięcia akapitów, wyrównanie do lewej | — |
| `print-like` | Krój szeryfowy, justowanie, wcięcia jak w druku | font własny nie jest dołączany |
| `dark-oled` | Czysta czerń tła pod OLED | e-ink i tryb ciemny czytnika nadpisują kolory |
| `manga-rtl` | Czytanie od prawej do lewej | ograniczone wsparcie czytników |

Własne presety dodasz przez `Importuj własny…` w GUI (zakładka **Fixer**) — trafiają do
`config_dir()/presets/*.css` i pojawiają się na liście obok wbudowanych.

### Python API

```python
from epubforge import Epub
from epubforge.fixers import (
    fix_css, hyphenate, fix_typography, optimize_images,
    CssFixOptions, HyphenationOptions, TypographyOptions, ImageFixOptions,
)

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

    # Typografia (raport: liczba podmian per reguła i plik)
    report = fix_typography(ebook, TypographyOptions(language="pl"))
    print(report.total_changes)

    # Optymalizacja obrazów (wymaga ".[images]"; raport oszczędności)
    images = optimize_images(ebook, ImageFixOptions(max_px=1200, jpeg_quality=75))
    print(images.saved_bytes, images.saved_percent)

    # Preset CSS
    from epubforge.fixers import apply_preset, get_preset
    apply_preset(ebook, get_preset("reader-friendly"), mode="append")

    # Szukaj i zamień (zamiana trafia do bufora — utrwala ebook.save())
    from epubforge.core.search import search_epub, replace_in_epub
    hits = search_epub(ebook, r"kot\w*", regex=True, whole_words=True)
    print(len(hits), hits[0].internal_path, hits[0].line)
    result = replace_in_epub(ebook, "kot", "pies")
    print(result.total, result.changed_files, result.skipped)

    ebook.save()  # zapisuje + tworzy backup
```

### GUI
```bash
epubforge-gui
```

Motyw: przycisk **Motyw** w górnym pasku (Automatyczny / Jasny / Ciemny).
„Automatyczny" podąża za ustawieniem systemu. Motyw realizuje **własny `theme.py`**
(styl Fusion + paleta + akcenty QSS) — bez zewnętrznych bibliotek motywów, z akcentem
marki `#5DCAA5`. Na Windows pasek tytułu zmienia kolor tylko gdy wybrany motyw różni
się od motywu systemu (Qt 6.5+ sam prowadzi pasek przy zgodzie). Przy rozjeździe
app-ciemny + system-jasny używane są spójne ciemne dialogi **Otwórz/Zapisz** (Qt);
w pozostałych przypadkach — natywne dialogi systemu.

### Języki

GUI i CLI używają jednego systemu tłumaczeń `gettext` (nie Qt Linguist), więc te same
katalogi działają w aplikacji desktopowej i w komendzie `epubforge`. Dostępne języki:

- **Polski** — język źródłowy (`msgid`)
- **English**
- **Deutsch**

W GUI język wybierzesz w górnym pasku przez **Język**. Zmiana zapisuje się w configu
i zaczyna działać po ponownym uruchomieniu aplikacji. CLI czyta tę samą wartość
`language` z configu; `auto` próbuje wykryć język systemu.

Dodanie nowego języka:

```bash
# 1. Odśwież szablon
pybabel extract -F babel.cfg -o src/epubforge/locale/epubforge.pot .

# 2. Utwórz katalog języka albo zaktualizuj istniejący
pybabel init -i src/epubforge/locale/epubforge.pot \
  -d src/epubforge/locale -D epubforge -l fr
# albo:
pybabel update -i src/epubforge/locale/epubforge.pot \
  -d src/epubforge/locale -D epubforge

# 3. Uzupełnij .po i skompiluj .mo
python build/compile_locales.py
```

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
| **PDF** | **pdf2md** (zalecany) / Calibre (fallback) | dobra / eksperymentalna | pdf2md → Markdown → EPUB (osadza obrazy); bez pdf2md fallback na Calibre |
| FB2 / LIT | Calibre | dobra | |
| **MOBI / AZW3 / AZW / PRC** | Calibre | dobra | formaty Kindle; pliki z DRM są odrzucane |

> ⚠️ **DRM:** EpubForge **nie usuwa** zabezpieczeń DRM. Pliki Kindle z DRM są
> wykrywane (nagłówek MOBI) i odrzucane z czytelnym komunikatem — nie trafiają do Calibre.

> 📄 **PDF → EPUB:** zalecanym silnikiem jest [**pdf2md**](https://github.com/chodzkos/pdf2md)
> (PDF → Markdown → Pandoc EPUB, z wyciąganiem i osadzaniem obrazów). Tryb `auto` używa
> pdf2md, gdy jest wykryty, a w przeciwnym razie wraca do Calibre. Konwersja przez Calibre
> pozostaje **eksperymentalna** (sztywne marginesy, łamanie akapitów). pdf2md wymaga
> zainstalowanego silnika konwersji (np. `pymupdf4llm`) — zob. jego README.

### Konwersja EPUB → KFX

| Silnik | Status | Uwagi |
|---|---|---|
| **Calibre + wtyczka KFX Output** | zalecany | sprawdzony, mniej wrażliwy na formatowanie |
| Kindle Previewer 3 | eksperymentalny | wrażliwy na nieidealne formatowanie EPUB |

### Do uruchomienia
- Python 3.10+ (jeśli nie używasz .exe)
- Opcjonalnie do pełnej funkcjonalności:
  - [Pandoc](https://pandoc.org/installing.html) — konwersja → EPUB
  - [pdf2md](https://github.com/chodzkos/pdf2md) — zalecany silnik PDF → EPUB (+ handoff „Otwórz w pdf2md")
  - [Calibre](https://calibre-ebook.com) — fallback + KFX
  - [Sigil](https://sigil-ebook.com) — edytor EPUB
  - [Kindle Previewer 3](https://www.amazon.com/gp/feature.html?ie=UTF8&docId=1000765261) — KFX (experimental)
  - [Temurin JRE 17+](https://adoptium.net/) + [EpubCheck 5.x](https://github.com/w3c/epubcheck/releases) — walidacja EPUB (`epubforge check` / zakładka **Walidacja**); rozpakuj `epubcheck.jar` do `<config>/epubcheck/epubcheck.jar` lub wskaż go w GUI
  - [DAISY Ace](https://daisy.github.io/ace/) (`npm install -g @daisy/ace`, wymaga Node.js) — audyt dostępności EPUB (`epubforge a11y` / przycisk w zakładce **Walidacja**)
  - `pip install ".[stats]"` — wykrywanie języka w statystykach (langdetect); bez tego język brany jest z metadanych
  - `pip install ".[fonts]"` — subsetting fontów (fonttools + brotli); bez tego opcja „Przytnij fonty" zgłasza czytelny błąd, a pliki WOFF2 są pomijane

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
