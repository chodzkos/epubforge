# API reference — biblioteka EpubForge

Przykłady użycia EpubForge jako biblioteki Python. Pełna, generowana dokumentacja
API (pdoc) publikowana jest na GitHub Pages.

---

## `Epub` — odczyt, edycja, zapis

```python
from epubforge import Epub

with Epub("book.epub") as ebook:
    print(ebook.opf_path)  # ścieżka OPF z META-INF/container.xml
    print(ebook.spine)  # kolejność czytania (idref-y)
    print([item.id for item in ebook.manifest])
    print(ebook.list_files())

    html = ebook.read_file("OEBPS/text/chapter1.xhtml")
    ebook.write_file("OEBPS/text/chapter1.xhtml", html.replace(b"foo", b"bar"))
    ebook.save()  # nadpisuje oryginał + tworzy rotowany .bak
```

`save(output_path)` zapisuje kopię pod wskazaną ścieżką (bez ruszania oryginału);
`output_path` wskazujący na samo źródło jest traktowany jak nadpisanie oryginału.
Zapis zawsze trzyma `mimetype` jako pierwszy, nieskompresowany wpis i jest
**atomowy z fsync**: nowa treść idzie do unikalnego tempa w katalogu docelowym,
jest fsyncowana (na POSIX też katalog) i podmieniana przez `os.replace`. Przy
dowolnym błędzie oryginał zostaje nietknięty. Nadpisanie poprzedza **rotowany
backup** (`.bak`, `.bak.1`, …) z konfigurowalną retencją (`save(backup_retention=…)`).

---

## `Metadata` — Dublin Core + seria

```python
from epubforge import Epub, Metadata

with Epub("book.epub") as ebook:
    meta = ebook.metadata  # odczyt
    meta.title = "Krew elfów"
    meta.creators = ["Andrzej Sapkowski"]
    meta.language = "pl"
    meta.series = "Wiedźmin"  # zapis w formacie Calibre + EPUB 3
    meta.series_index = 3  # float (bywa 1.5)
    ebook.metadata = meta  # aktualizuje bufor w pamięci
    ebook.save()  # jawnie utrwala zmianę i tworzy backup

# Bez Epub — bezpośrednio na bajtach OPF:
meta = Metadata.from_opf(opf_bytes)
new_opf = meta.to_opf(opf_bytes)  # zachowuje manifest/spine i resztę
```

Przypisanie do `ebook.metadata` nie modyfikuje pliku źródłowego. Użyj
`ebook.save()` do nadpisania źródła albo `ebook.save(output_path)` do zapisania
kopii. Wyjście z context managera bez `save()` porzuca niezapisane zmiany.

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
    engine="auto",  # "pandoc" | "calibre" | "auto"
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
    fix_css(
        ebook,
        CssFixOptions(
            remove_colors=True,
            replace_justify="left",
            inject_book_margin_px=20,
            skip_hyphenation_headers=True,
        ),
    )
    ebook.save()
```

---

## Szukaj i zamień

```python
from epubforge import Epub
from epubforge.core.search import search_epub, replace_in_epub, SearchPatternError

with Epub("book.epub") as ebook:
    # Szukanie (literal/regex, wielkość liter, całe słowa, zakres plików)
    hits = search_epub(
        ebook,
        "kot",
        regex=False,
        case_sensitive=False,
        whole_words=True,
        paths=None,  # None = wszystkie pliki tekstowe
    )
    for hit in hits[:3]:
        print(hit.internal_path, hit.line, hit.column, hit.preview)

    # Zamiana — pisze do BUFORA; utrwalasz przez ebook.save()
    report = replace_in_epub(ebook, "kot", "pies")
    print(report.total, report.changed_files)
    print(report.skipped)  # [(ścieżka, powód)] dla plików nie-UTF-8

    ebook.save()
```

Wzorzec błędny/pusty/zbyt długi zgłasza `SearchPatternError`. ``whole_words`` używa
``\b`` z ``re.UNICODE`` (poprawne dla polskich znaków). Pliki ze znakami zastępczymi
``�`` są pomijane przy zamianie (nie przy szukaniu).

---

## Fixer — optymalizacja obrazów

```python
from epubforge import Epub
from epubforge.fixers import ImageFixOptions, optimize_images  # wymaga epubforge[images]

with Epub("book.epub") as ebook:
    report = optimize_images(
        ebook,
        ImageFixOptions(
            max_px=1200,  # dłuższy bok; None = bez skalowania
            jpeg_quality=75,
            grayscale=False,  # pod e-ink
            strip_metadata=True,  # EXIF/ICC out
            skip_cover=True,  # okładkę zostaw w pełnej jakości
        ),
    )
    ebook.save()

print(report.saved_bytes, report.saved_percent)  # np. 1048576, 63.2
print(report.changed_files)  # ścieżki zmniejszonych obrazów
```

Format pliku nigdy się nie zmienia (jpg→jpg, png→png), a zapis następuje tylko gdy
wynik jest mniejszy — drugi przebieg nie wprowadza zmian. Brak Pillow zgłasza
`ImageOptimizationError` z instrukcją instalacji.

---

## Fixer — typografia

```python
from epubforge import Epub
from epubforge.fixers import TypographyOptions, fix_typography

with Epub("book.epub") as ebook:
    report = fix_typography(
        ebook,
        TypographyOptions(
            language="pl",  # pl / en / de — dobiera znaki cudzysłowów
            fix_quotes=True,  # proste " ' → pary typograficzne wg języka
            fix_dashes=True,  # pauza w dialogach/wtrąceniach (łączniki w słowach bez zmian)
            fix_ellipsis=True,  # ... → …
            nbsp_single_letters=True,  # pl: twarda spacja po sierotach a/i/o/u/w/z
            nbsp_numbers_units=False,  # 10 km, XX w. → twarda spacja (domyślnie OFF)
        ),
    )
    ebook.save()

# TypographyReport: liczba podmian per reguła, per plik i sumarycznie
print(report.total_changes)  # łączna liczba podmian
print(report.changed_files)  # lista ścieżek zmienionych plików
print(report.totals())  # {"fix_quotes": 12, "fix_dashes": 4, ...}
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

tools = detect_with_cache()  # cache w config.json, re-detekcja po 7 dniach
print({name: t.available for name, t in tools.items()})
```

**Lokalizacja Javy** (warstwa kompozycji EpubForge nad `chodzkos-detection`) idzie
w kolejności: override → `PATH` (`shutil.which`) → App Paths (rejestr Windows) →
rejestr Eclipse Adoptium → fallback typowych katalogów instalacji.

**Świeżość cache** (`last_detected` w `config.json`) jest zapisywana **zawsze w
UTC** (aware, z offsetem). Odczyt jest odporny: timestamp bez strefy jest
interpretowany jako UTC, a każdy przypadek wątpliwy (niepoprawny ISO 8601, zła
strefa, data z przyszłości po cofnięciu zegara) uznaje cache za **nieświeży** i
wymusza ponowną detekcję — zamiast wywracać start aplikacji.

---

## Wyjątki

Wszystkie dziedziczą po `EpubError` (`epubforge.core.exceptions`):

- `InvalidEpubError` — plik nie istnieje lub nie jest poprawnym ZIP/EPUB
- `OpfNotFoundError` — brak/niepoprawny `container.xml`
- `EpubNotOpenError` — operacja na nieotwartym `Epub`
- `ConverterNotFoundError`, `ConversionError` — konwersje
