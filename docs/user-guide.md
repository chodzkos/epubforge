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
  potwierdzenia (konwersja eksperymentalna).
- **Fixer** — hyphenacja (język, metoda soft-hyphen/CSS) i normalizacja CSS
  (usuń kolory/fonty, reset, justify→lewo, margines). Naprawa działa **w miejscu**.
- **Eksport Kindle** — wybierz format (KFX / MOBI / AZW3) i silnik, opcjonalnie napraw
  EPUB przed konwersją, wskaż folder wyjściowy.

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

# Naprawa EPUB (hyphenacja + CSS)
epubforge fix book.epub --remove-colors --replace-justify
epubforge hyphenate book.epub --lang pl --method soft-hyphen --skip-headers

# Metadane (podgląd i edycja, w tym seria/tom)
epubforge meta book.epub
epubforge meta book.epub --title "Krew elfów" --author "Sapkowski, Andrzej" \
    --series "Wiedźmin" --series-index 3

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
