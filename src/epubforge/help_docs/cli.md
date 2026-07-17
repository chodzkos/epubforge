# Wiersz poleceń (CLI)

Te same operacje co w GUI są dostępne z terminala jako `epubforge <komenda>`. Każda
komenda ma `--help` z pełną listą opcji; `epubforge --version` pokazuje wersję.

| Komenda | Do czego |
|---|---|
| `info` | Wersja i wykryte narzędzia |
| `doctor` | Pełna diagnostyka środowiska (wykryte narzędzia na żywo) |
| `check` | Walidacja EPUB przez EpubCheck |
| `a11y` | Audyt dostępności (DAISY Ace) |
| `convert` | Konwersja pliku → EPUB |
| `enrich` | **Masowe** wzbogacanie metadanych (BN/LubimyCzytac/OpenLibrary/GBooks) |
| `meta` | Podgląd i edycja metadanych (w tym seria/tom) |
| `fix` | Normalizacja CSS + obrazy + fonty EPUB |
| `hyphenate` | Dzielenie wyrazów (pyphen) |
| `typo` | Typografia (cudzysłowy, pauzy, wielokropek, twarde spacje) |
| `upgrade` | Modernizacja EPUB 2 → EPUB 3 |
| `toc` | Spis treści: podgląd / generowanie / naprawa |
| `stats` | Statystyki książki (+ raport HTML) |
| `kfx` | Eksport EPUB → KFX |
| `mobi` | Eksport EPUB → MOBI/AZW3 |
| `presets` | Biblioteka presetów CSS (`presets list`) |
| `run` | Uruchom recepturę TOML na plikach EPUB |

## Przykłady

```bash
# Konwersja do EPUB (pdf2md zalecany dla PDF)
epubforge convert book.docx book.epub
epubforge convert input.pdf output.epub --engine pdf2md

# Walidacja i dostępność (wymagają Javy + epubcheck.jar / narzędzia ace)
epubforge check book.epub --json report.json --min-severity warning
epubforge a11y book.epub

# Naprawa, typografia, hyphenacja (batch + równoległość)
epubforge fix a.epub b.epub --remove-colors --replace-justify --jobs 3
epubforge typo book.epub --lang pl
epubforge hyphenate book.epub --lang pl --method soft-hyphen --skip-headers

# Metadane: pojedynczo (meta) lub masowo (enrich)
epubforge meta book.epub --title "Krew elfów" --series "Wiedźmin" --series-index 3
epubforge enrich ./biblioteka --tags --policy fill --dry-run --report plan.csv

# Spis treści, upgrade, statystyki, presety, receptury
epubforge toc book.epub --generate --max-level 3 --output out.epub
epubforge upgrade book.epub --dry-run
epubforge stats book.epub --report stats.html --top 50
epubforge presets list
epubforge run kindle-pl *.epub --out-dir ./out

# Eksport Kindle
epubforge kfx book.epub --engine calibre
epubforge mobi book.epub --format azw3 --engine calibre
```

## Tryb wsadowy i podgląd zmian

`fix`, `hyphenate` i `typo` przyjmują **listę plików** i `--jobs N` (przetwarzanie
równoległe; lista deduplikowana z zachowaniem kolejności, na końcu tabela per plik i
kod wyjścia `1`, gdy choć jeden plik zawiódł).

`--dry-run` nic nie zapisuje — pokazuje unified diff plików tekstowych (`.xhtml`,
`.css`, `.opf`, `.ncx`…; domyślnie do 40 linii na plik) albo deltę rozmiaru pliku
binarnego. `--diff-full` znosi limit diffu.

> Treść pomocy jest zwięzła; pełny opis komend i flag: `docs/user-guide.md` w
> repozytorium oraz `epubforge <komenda> --help`.
