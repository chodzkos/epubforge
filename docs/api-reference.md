# API reference — biblioteka EpubForge

Przykłady użycia EpubForge jako biblioteki Python. Pełna, generowana dokumentacja
API (pdoc) publikowana jest na GitHub Pages.

---

## `Epub` — odczyt, edycja, zapis

```python
from epubforge import Epub

with Epub("book.epub") as ebook:
    print(ebook.opf_path)            # ścieżka OPF z META-INF/container.xml
    print(ebook.spine)               # kolejność czytania (idref-y)
    print([item.id for item in ebook.manifest])
    print(ebook.list_files())

    html = ebook.read_file("OEBPS/text/chapter1.xhtml")
    ebook.write_file("OEBPS/text/chapter1.xhtml", html.replace(b"foo", b"bar"))
    ebook.save()                     # nadpisuje oryginał + tworzy .bak
```

`save(output_path)` zapisuje kopię pod wskazaną ścieżką (bez ruszania oryginału).
Zapis zawsze trzyma `mimetype` jako pierwszy, nieskompresowany wpis i jest atomowy.

---

## `Metadata` — Dublin Core + seria

```python
from epubforge import Epub, Metadata

with Epub("book.epub") as ebook:
    meta = ebook.metadata               # odczyt
    meta.title = "Krew elfów"
    meta.creators = ["Andrzej Sapkowski"]
    meta.language = "pl"
    meta.series = "Wiedźmin"            # zapis w formacie Calibre + EPUB 3
    meta.series_index = 3              # float (bywa 1.5)
    ebook.metadata = meta               # setter zapisuje + robi backup

# Bez Epub — bezpośrednio na bajtach OPF:
meta = Metadata.from_opf(opf_bytes)
new_opf = meta.to_opf(opf_bytes)        # zachowuje manifest/spine i resztę
```

---

## Konwersja → EPUB

```python
from pathlib import Path
from epubforge import Metadata
from epubforge.converters import ConvertOptions, to_epub

result = to_epub(
    Path("book.docx"),
    Path("out/book.epub"),
    ConvertOptions(metadata=Metadata(title="Tytuł"), cover_image=Path("cover.jpg")),
    engine="auto",                      # "pandoc" | "calibre" | "auto"
)
print(result.success, result.engine, result.output_path)
```

Błędy: `ConverterNotFoundError` (brak narzędzia), `ConversionError` (proces zwrócił błąd).

---

## Eksport Kindle (KFX / MOBI / AZW3)

```python
from pathlib import Path
from epubforge.converters import KfxOptions, MobiOptions, to_kfx, to_mobi

# KFX (folder docelowy — plik dostaje nazwę źródła)
to_kfx(Path("book.epub"), Path("out/"), KfxOptions(engine="auto", fix_epub_first=True))

# MOBI / AZW3 (pełna ścieżka docelowa)
to_mobi(Path("book.epub"), Path("out/book.azw3"), MobiOptions(fmt="azw3", engine="calibre"))
```

---

## Fixery — CSS i hyphenacja

```python
from epubforge import Epub
from epubforge.fixers import CssFixOptions, HyphenationOptions, fix_css, hyphenate

with Epub("book.epub") as ebook:
    hyphenate(ebook, HyphenationOptions(language="pl", method="soft-hyphen", skip_headers=True))
    fix_css(ebook, CssFixOptions(
        remove_colors=True,
        replace_justify="left",
        inject_book_margin_px=20,
        skip_hyphenation_headers=True,
    ))
    ebook.save()
```

---

## Fixer — typografia

```python
from epubforge import Epub
from epubforge.fixers import TypographyOptions, fix_typography

with Epub("book.epub") as ebook:
    report = fix_typography(ebook, TypographyOptions(
        language="pl",              # pl / en / de — dobiera znaki cudzysłowów
        fix_quotes=True,            # proste " ' → pary typograficzne wg języka
        fix_dashes=True,            # pauza w dialogach/wtrąceniach (łączniki w słowach bez zmian)
        fix_ellipsis=True,          # ... → …
        nbsp_single_letters=True,   # pl: twarda spacja po sierotach a/i/o/u/w/z
        nbsp_numbers_units=False,   # 10 km, XX w. → twarda spacja (domyślnie OFF)
    ))
    ebook.save()

# TypographyReport: liczba podmian per reguła, per plik i sumarycznie
print(report.total_changes)          # łączna liczba podmian
print(report.changed_files)          # lista ścieżek zmienionych plików
print(report.totals())               # {"fix_quotes": 12, "fix_dashes": 4, ...}
```

Reguły są idempotentne — drugi przebieg nie wprowadza zmian. Parser jest utwardzony
(ochrona XXE), serializacja zachowuje DOCTYPE i deklarację XML, a `code`/`pre`,
atrybuty i komentarze pozostają nietknięte.

---

## Wykrywanie narzędzi

```python
from epubforge.core import Tools, detect_with_cache

pandoc = Tools.pandoc()
print(pandoc.available, pandoc.path, pandoc.version)

tools = detect_with_cache()             # cache w config.json, re-detekcja po 7 dniach
print({name: t.available for name, t in tools.items()})
```

---

## Wyjątki

Wszystkie dziedziczą po `EpubError` (`epubforge.core.exceptions`):

- `InvalidEpubError` — plik nie istnieje lub nie jest poprawnym ZIP/EPUB
- `OpfNotFoundError` — brak/niepoprawny `container.xml`
- `EpubNotOpenError` — operacja na nieotwartym `Epub`
- `ConverterNotFoundError`, `ConversionError` — konwersje
