# 🗺️ EpubForge — Roadmap v3 (rozwój po 2.0.0) + prompty

Kontynuacja `ROADMAP.md` (etapy 0–14, wydane jako v1.0/v2.0). Numeracja etapów ciągnie się od **15**.
Konwencje bez zmian: **każdy etap = osobna gałąź feature** (`feature/stage-N-nazwa`), conventional commits, DoD jak w `ROADMAP.md` (mypy strict, pytest, ruff, coverage ≥ 70% nowego modułu, docstringi, PR + squash + delete branch).

**Decyzje zakresu:**
- ❌ **OCR poza zakresem** — nie dublujemy funkcji `pdf2md`; zamiast tego **integracja z pdf2md** (Etap 22): handoff jak dla Sigila + delegowanie konwersji PDF do CLI `pdf2md`.
- ✅ Etap 15 (naprawy z audytu) jest **bramką** — nic z etapów 16+ nie merguje się przed jego domknięciem (w szczególności REL‑1/SEC‑1/COR‑1).

Odniesienie: szczegóły problemów i gotowe prompty naprawcze → `AUDYT-epubforge.md`.

---

## Mapa wydań

| Wydanie | Etapy | Motyw przewodni |
|---|---|---|
| **v2.1** | 15–18 | fundament wydaniowy + polska typografia + batch/dry‑run + receptury |
| **v2.2** | 19–21 | anulowanie/postęp, optymalizacja obrazów, szukaj i zamień |
| **v2.3** | 22–23 | integracja pdf2md, upgrade EPUB 2→3 |
| **v3.0.0** | 24–26, 28–30 | subsetting fontów, dostępność (Ace), metadane z ISBN + wzbogacanie (LubimyCzytac, taksonomia tagów + AI, batch/calibredb) — Etapy 28–30 domknięte razem z bramą v3.0 zamiast osobnego v3.1 |
| _odłożone_ | 27 | dystrybucja PyPI/Linux/macOS/winget — do przyszłego wydania |

---

✅ zrobiony ## 🧱 Etap 15 — Fundament wydaniowy (naprawy z audytu)

**Gałąź:** `fix/stage-15-audit-hardening` (może być kilka mniejszych PR)
**Czas:** ~4 h
**Cel:** zamknąć ustalenia z `AUDYT-epubforge.md`, które blokują dalszy rozwój i publikację.

### Zakres (w kolejności)
1. **REL‑1** — droga na PyPI: publikacja `chodzkos-gui-kit` na PyPI **lub** korekta README (bez obietnicy `pip install epubforge`); docelowo zamiana `git+https…` na zależność wersyjną.
2. **SEC‑1** — wspólny utwardzony parser XML (`resolve_entities=False`, `no_network=True`) dla `metadata.py`, `epub.py`, `css_fixer.py`.
3. **COR‑1** — `to_mobi`/`to_kfx`: fix na **kopii** źródła (koniec cichej mutacji wejścia).
4. **REL‑2** — spójna wersja/status (README 2.x, classifier ≥ Beta).
5. **REL‑3** — lock zależności + użycie w `build.yml`.
6. Mniejsze: SEC‑2 (temp raportu), SEC‑3 (pin akcji do SHA), SEC‑4 (Dependabot/CodeQL/SECURITY.md), COR‑2 (i18n locale), TEST‑1 (coverage GUI), QUAL‑1 (ZipInfo).

### Kryteria akceptacji
- [ ] Wszystkie prompty z `AUDYT-epubforge.md` zrealizowane albo świadomie odrzucone (decyzja zapisana w CHANGELOG/PR)
- [ ] `python -m build` daje wheel bez direct references **albo** README nie obiecuje PyPI
- [ ] Test regresji XXE zielony; test „konwersja nie zmienia bajtów źródła" zielony
- [ ] CI zielone na całej macierzy

### Stage gate
✋ **Tag:** `v2.0.1` (same naprawy, bez nowych funkcji) — dopiero po nim start etapów 16+.

---

✅ zrobiony ## 🇵🇱 Etap 16 — Fixer typografii polskiej ⭐

**Gałąź:** `feature/stage-16-typography`
**Czas:** ~4 h
**Cel:** poprawa typografii tekstu w EPUB — funkcja‑wyróżnik, której nie robi dobrze Calibre ani Sigil.

### Co powstanie
- `src/epubforge/fixers/typography.py` — czysta logika (bez Qt), wzorzec jak `hyphenator.py`
- `src/epubforge/cli/typo.py` — subkomenda `epubforge typo`
- Sekcja **Typografia** w zakładce **Fixer** (checkboxy + dropdown języka)
- `tests/test_typography.py`

### API
```python
@dataclass
class TypographyOptions:
    language: str = "pl"                     # pl / en / de — dobiera cudzysłowy i reguły
    fix_quotes: bool = True                  # "..." → „…” (pl), “…” (en), „…“ (de)
    fix_dashes: bool = True                  # " - " → " — " (pl: pauza w dialogach/wtrąceniach)
    fix_ellipsis: bool = True                # "..." → "…"
    nbsp_single_letters: bool = True         # pl: spacja po a/i/o/u/w/z → U+00A0 („sieroty”)
    nbsp_numbers_units: bool = False         # "10 km", "XX w." → twarda spacja (ostrożnie)
    skip_tags: set[str] = field(default_factory=lambda: {"code", "pre", "kbd", "samp", "var", "tt"})

def fix_typography(epub: Epub, options: TypographyOptions) -> TypographyReport: ...
    # Report: ile podmian per reguła per plik — do logu GUI i --dry-run
```

### ⚠️ Pułapki
- **Parowanie cudzysłowów jest stanowe** — otwierający vs zamykający rozpoznawaj heurystyką: cudzysłów po białym znaku / początku węzła / `(«[` = otwierający, inaczej zamykający. Stan trzeba nieść **przez granice tagów** w obrębie akapitu (tekst dzielony przez `<em>` itd. — para może zaczynać się w `element.text`, a kończyć w `child.tail`). Pilnuj tego samego wzorca `text`/`tail`, co w `_hyphenate_element`.
- **Nie ruszaj atrybutów, komentarzy, PI** — tylko węzły tekstowe; iteruj z guardem `isinstance(child.tag, str)` (pułapka komentarzy lxml).
- **Miękkie łączniki** — tekst po hyphenacji zawiera `U+00AD` wewnątrz słów; regexy słów muszą je tolerować (wzór: `_WORD_RE` z hyphenator.py).
- **Idempotentność** — drugi przebieg nie zmienia nic (test round‑trip).
- **Serializacja** — użyj utwardzonego parsera z Etapu 15 i zachowaj DOCTYPE/deklarację XML (wzorzec `toc/_xml.serialize_xml`, nie kopiuj obecnego `_serialize_xml` z hyphenatora, który gubi doctype).
- Dialogi PL zaczynające się od `-` na początku akapitu → pauza `—` tylko gdy `fix_dashes` i początek bloku (`<p>`); nie zamieniaj łączników wewnątrz słów (`biało-czerwony`).

### Kryteria akceptacji
- [ ] Każda reguła działa niezależnie i w kombinacji; raport podaje liczby podmian
- [ ] Cudzysłowy parowane poprawnie także przez granice `<em>/<i>` (test dedykowany)
- [ ] `code`/`pre` nietknięte; atrybuty nietknięte
- [ ] Idempotentność (drugi przebieg = 0 podmian)
- [ ] Warianty en/de dają właściwe znaki cudzysłowów
- [ ] CLI `epubforge typo book.epub --lang pl` działa; `--dry-run` po Etapie 17 pokazuje diff

---

## 📚 Etap 17 — Batch w CLI + `--dry-run`/diff wszędzie

**Gałąź:** `feature/stage-17-batch-dryrun`
**Czas:** ~3 h
**Cel:** operacje na wielu plikach naraz + podgląd zmian przed zapisem.

### Co powstanie
- Rozszerzenie `Epub` o introspekcję bufora: `pending_changes() -> PendingChanges` (`modified: dict[str, bytes]`, `deleted: set[str]`)
- `src/epubforge/cli/_batch.py` — wspólny runner wielu plików (`nargs="+"` + `--jobs N`)
- `--dry-run` (z diffem unified) w: `fix`, `hyphenate`, `typo`, `presets`/`fix --preset`
- `tests/test_cli_batch.py`, rozszerzenia testów istniejących komend

### Zachowanie
- `epubforge fix a.epub b.epub c.epub --remove-colors --jobs 3` — pula procesów (`concurrent.futures.ProcessPoolExecutor`), wynik per plik (`rich` tabela: OK/FAIL + czas), kod wyjścia ≠ 0 jeśli cokolwiek padło.
- `--dry-run`: wykonaj fixery na otwartym `Epub`, **nie wołaj `save()`**; dla każdego zmienionego pliku wewnętrznego wypisz skrócony `difflib.unified_diff` (limit np. 40 linii/plik, `--diff-full` bez limitu); pliki binarne — tylko nazwa + delta rozmiaru.

### ⚠️ Pułapki
- **PyInstaller + multiprocessing na Windows** — w `cli/main.py` (i wejściu GUI) `multiprocessing.freeze_support()` na początku `main()`; workery per‑proces muszą być importowalne (funkcja top‑level, nie lambda).
- Diff rób na **dekodowanym utf‑8 z `errors="replace"`** tylko dla plików tekstowych (reuse `editor_files.is_editable`/`decode_text`).
- `--jobs` > 1 + ten sam plik podany dwa razy → dedup listy wejść przed startem.

### Kryteria akceptacji
- [ ] Batch: N plików, raport per plik, poprawny kod wyjścia zbiorczy
- [ ] `--dry-run` nie zmienia ŻADNEGO bajtu na dysku (test: hash pliku przed/po)
- [ ] Diff czytelny dla zmiany CSS i XHTML; binaria bez wywału
- [ ] Działa w zamrożonym `.exe` (test manualny w kryteriach builda)

---

## 🧪 Etap 18 — Receptury (pipeline)

**Gałąź:** `feature/stage-18-recipes`
**Czas:** ~3 h
**Cel:** jedna komenda wykonująca typową sekwencję: fix → typografia → hyphenacja → preset → eksport Kindle.

### Co powstanie
- `src/epubforge/recipes.py` — model + loader + executor (czysta logika)
- `src/epubforge/cli/run.py` — `epubforge run <receptura> pliki...`
- Wbudowane receptury: `kindle-pl` (fix + typo pl + hyphenate pl + mobi), `czytnik-epub` (fix + typo + preset reader-friendly)
- Własne: `config_dir()/recipes/*.toml`
- GUI: przycisk **„Uruchom recepturę…"** (dialog: wybór receptury + lista plików) — reuse `FileList` i `Worker`
- `tests/test_recipes.py`

### Format receptury (TOML)
```toml
name = "kindle-pl"
description = "Przygotowanie polskiego EPUB-a pod Kindle (MOBI)"

[[steps]]
op = "fix_css"          # klucz z rejestru kroków
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
op = "to_mobi"          # kroki eksportu zawsze NA KOŃCU; wynik do --out-dir
[steps.options]
fmt = "mobi"
```

### ⚠️ Pułapki
- **Rejestr kroków** = jawny dict `op → (fn, OptionsClass)`; opcje waliduj przez konstrukcję dataclass (nieznany klucz → czytelny błąd z nazwą receptury i kroku). Bez dynamicznych importów po stringu.
- Kroki fixerów pracują na **jednym otwartym `Epub`** (jeden `save()` na końcu fazy fixów — spójne z buforem), kroki konwersji dostają ścieżkę już zapisanego pliku.
- Respektuj Etap 15/COR‑1: eksport nie mutuje wejścia; `--dry-run` z Etapu 17 ma działać dla fazy fixów receptury.
- `tomllib` (stdlib 3.11+) — dla 3.10 dodaj zależność warunkową `tomli; python_version<'3.11'`.

### Kryteria akceptacji
- [ ] `epubforge run kindle-pl book.epub --out-dir out/` wykonuje pełną sekwencję
- [ ] Błędna receptura (literówka w op/opcji) → czytelny błąd, kod ≠ 0, nic nie zapisane
- [ ] Własna receptura z `config_dir()` widoczna w `epubforge run --list`
- [ ] GUI: receptura odpala się w `Worker` z logiem na żywo

---

## 🏷️ Stage gate v2.1
**Tag:** `git tag v2.1.0` — typografia PL, batch, dry‑run, receptury. Aktualizacja README (sekcja funkcji + przykłady CLI) i CHANGELOG.

---

## ⏹️ Etap 19 — Anulowanie i postęp długich operacji

**Gałąź:** `feature/stage-19-cancel-progress`
**Czas:** ~3 h
**Cel:** możliwość przerwania konwersji/walidacji z GUI + realny pasek postępu.

### Co powstanie
- `gui/workers.py`: `Worker` dostaje `cancel()` (ustawia `threading.Event`), callable dostaje trzeci hook `should_cancel: Callable[[], bool]`
- `run_subprocess_streaming(..., should_cancel=None)` — sprawdzanie między liniami; anulowanie = `proc.terminate()` → grace 3 s → `proc.kill()`
- Konwertery (`to_epub`/`to_mobi`/`to_kfx`): wariant strumieniowy z parsowaniem postępu Calibre (linie z `NN%`) → `emit_progress`
- GUI: przycisk **Anuluj** + `QProgressBar` w zakładkach Konwerter/Kindle/Walidacja
- `tests/gui/test_workers_cancel.py` (subprocess = `python -c "sleep"`)

### ⚠️ Pułapki
- **NIGDY `QThread.terminate()`** — anulowanie wyłącznie kooperacyjne (event) + ubicie procesu potomnego; wątek kończy się sam po wyjściu z pętli czytania stdout.
- Po `terminate()` na Windows strumień może rzucić — domknij pętlę czytania w `try/finally`, `proc.wait()` zawsze.
- Anulowanie w trakcie **fazy fixów** (bufor w pamięci, przed `save()`) = bezpieczne porzucenie; w trakcie zapisu — nie przerywaj między `tmp` a `os.replace` (sekcja nieprzerywalna).
- Sygnał `failed` vs anulowanie: dodaj osobny sygnał `cancelled` (nie raportuj anulowania jako błędu).

### Kryteria akceptacji
- [ ] Anulowanie konwersji Calibre ubija proces w ≤ 3 s, GUI wraca do stanu spoczynku
- [ ] Postęp Calibre widoczny w pasku (parsowanie `NN%`)
- [ ] Anulowanie nie zostawia plików `.tmp` ani uszkodzonego celu
- [ ] Brak zmian API dla istniejących wywołań (parametr opcjonalny)

---

## 🖼️ Etap 20 — Optymalizacja obrazów

**Gałąź:** `feature/stage-20-images`
**Czas:** ~4 h
**Cel:** odchudzanie EPUB-ów (typowo −50…−80 %) pod czytniki e‑ink.

### Co powstanie
- `src/epubforge/fixers/images.py` (Pillow — **nowe extra** `[images]`, importowane leniwie)
- CLI: `epubforge fix --optimize-images [--max-px 1200] [--jpeg-quality 75] [--grayscale]`
- Sekcja **Obrazy** w zakładce Fixer + wynik „zaoszczędzono X MB" w logu
- Krok `optimize_images` w rejestrze receptur
- `tests/test_images.py` (fixtures generowane Pillow w teście)

### API
```python
@dataclass
class ImageFixOptions:
    max_px: int | None = 1200          # dłuższy bok; None = bez skalowania
    jpeg_quality: int = 75
    grayscale: bool = False            # pod e-ink
    strip_metadata: bool = True        # EXIF/ICC out
    skip_cover: bool = True            # okładkę zostaw w pełnej jakości
    formats: set[str] = field(default_factory=lambda: {".jpg", ".jpeg", ".png"})

def optimize_images(epub: Epub, options: ImageFixOptions) -> ImageReport: ...
```

### ⚠️ Pułapki
- **Nie zamieniaj formatu pliku** (jpg zostaje jpg, png zostaje png) — zmiana rozszerzenia/media‑type wymagałaby przepisania manifestu i wszystkich `src` w XHTML; nie w tym etapie.
- **Zapisuj tylko gdy mniejsze** — jeśli po rekompresji rozmiar ≥ oryginału, zostaw oryginał (częste dla już zoptymalizowanych plików).
- **Okładka** — wykrycie: manifest `properties="cover-image"` (EPUB 3) lub `<meta name="cover" content="id">` (EPUB 2); przy `skip_cover=True` pomiń.
- PNG z paletą/przezroczystością: konwersja trybów przez `Image.convert` ostrożnie (P→RGB gubi przezroczystość — zachowaj RGBA dla PNG z alfą).
- SVG poza zakresem (to tekst — pomiń).
- Brak Pillow → czytelny błąd „zainstaluj epubforge[images]" (wzorzec jak langdetect w stats).

### Kryteria akceptacji
- [ ] Raport per plik: rozmiar przed/po, suma oszczędności
- [ ] Plik po optymalizacji renderuje się (Pillow round‑trip w teście)
- [ ] Okładka nietknięta przy `skip_cover=True`; EXIF usunięty przy `strip_metadata`
- [ ] Wynikowy EPUB przechodzi EpubCheck (test integracyjny, jeśli dostępny)
- [ ] Idempotentność praktyczna: drugi przebieg ~0 oszczędności

---

## 🔎 Etap 21 — Szukaj i zamień w całym EPUB

**Gałąź:** `feature/stage-21-search-replace`
**Czas:** ~4 h
**Cel:** najczęściej brakująca funkcja vs Sigil — przeszukiwanie/podmiana we wszystkich plikach tekstowych.

### Co powstanie
- `src/epubforge/core/search.py` — czysta logika (bez Qt)
- Panel **Szukaj/Zamień** w zakładce **Edytor** (Ctrl+Shift+F): pole szukaj/zamień, opcje (regex, wielkość liter, całe słowa, zakres: bieżący plik / cały EPUB), drzewo wyników, „Zamień", „Zamień wszystkie"
- `tests/test_search.py`, `tests/gui/test_search_panel.py`

### API
```python
@dataclass(frozen=True)
class SearchHit:
    internal_path: str
    line: int            # 1-based (reuse offset_to_line_col z editor_files)
    column: int
    preview: str         # linia z trafieniem, przycięta

def search_epub(epub: Epub, query: str, *, regex: bool = False,
                case_sensitive: bool = False, whole_words: bool = False,
                paths: Iterable[str] | None = None) -> list[SearchHit]: ...

def replace_in_epub(epub: Epub, query: str, replacement: str, *, ...) -> ReplaceReport: ...
    # zapisuje do BUFORA epub.write_file — utrwalenie robi użytkownik („Zapisz EPUB”)
```

### ⚠️ Pułapki
- Przeszukuj tylko pliki edytowalne (`editor_files.is_editable` + CSS/OPF/NCX); dekodowanie `decode_text` (utf‑8 replace) — **zamiana w pliku ze znakami zastępczymi `�` wymaga potwierdzenia** (ryzyko utrwalenia uszkodzenia).
- Regex użytkownika: `re.error` → czytelny komunikat, nie traceback; timeout nie istnieje w `re` — ogranicz długość wzorca i dokumentuj (katastroficzny backtracking to ryzyko świadome).
- **Zamiana a otwarty plik w edytorze**: jeśli bieżący plik ma niezapisane zmiany w `CodeEditor`, zamiana działa na wersji z edytora (nie z bufora Epub) — zsynchronizuj przez istniejący mechanizm `_dirty`.
- Wyniki klikalne: dwuklik → otwórz plik w edytorze i skocz do linii (reuse mechanizmu skoku z zakładki Walidacja).
- `whole_words` w regexie: `\b` zawodzi przy polskich znakach w starych trybach — używaj `re.UNICODE` (domyślne w py3) i testu z „żółć".

### Kryteria akceptacji
- [ ] Szukanie literal/regex/całe słowa/wielkość liter — testy czystej logiki
- [ ] „Zamień wszystkie" raportuje liczbę podmian per plik; trafia do bufora, nie na dysk
- [ ] Dwuklik wyniku otwiera plik i ustawia kursor na trafieniu
- [ ] Undo w edytorze cofa zamianę w bieżącym pliku

---

## 🏷️ Stage gate v2.2
**Tag:** `git tag v2.2.0`. Zrzuty ekranu nowych funkcji do README.

---

## 🔗 Etap 22 — Integracja pdf2md

**Gałąź:** `feature/stage-22-pdf2md`
**Czas:** ~3 h
**Cel:** PDF → EPUB o wyższej jakości przez delegację do `pdf2md` (bez dublowania jego funkcji w EpubForge). OCR pozostaje w pdf2md.

### Co powstanie
- Detekcja: `Tools.pdf2md()` w `core/detection.py` (PATH + typowe katalogi instalacji; wpis w `detect_all`, cache, override — jak inne narzędzia)
- `converters/to_epub.py`: nowy silnik `engine="pdf2md"` dla wejść `.pdf` — łańcuch: `pdf2md <in.pdf> → <tmp>/book.md (+ obrazy)` → istniejąca ścieżka Pandoc `md → epub`
- GUI Konwerter: obecny dialog ostrzeżenia PDF dostaje wybór: **„Konwertuj przez pdf2md (zalecane)"** (gdy wykryty) / „Calibre (obecne zachowanie)"
- GUI: przycisk handoff **pdf2md** obok Sigil/Calibre (reuse `external_tools.launch_tool`) — otwarcie PDF-a w GUI pdf2md
- Pasek statusu narzędzi: pdf2md w liście wykrywanych
- `tests/test_pdf2md.py` (mock subprocess — wzorzec z `test_converter.py`)

### ⚠️ Pułapki
- **NAJPIERW zweryfikuj realne CLI pdf2md** (repo `chodzkos/pdf2md`: nazwa binarki/entry pointu, flagi wyjścia, czy zapisuje obrazy do katalogu, kody wyjścia). Ten etap NIE zgaduje interfejsu — jeśli pdf2md nie ma jeszcze stabilnego CLI, pierwszym krokiem jest issue/PR w pdf2md definiujący minimalny kontrakt: `pdf2md convert <in.pdf> -o <out.md> [--images-dir DIR]`, kod 0/≠0, log na stderr.
- Katalog tymczasowy na `.md` + obrazy (`tempfile.TemporaryDirectory`); Pandoc musi widzieć obrazy — uruchamiaj z `cwd` tego katalogu albo przekaż `--resource-path`.
- `engine="auto"` dla `.pdf`: preferencja `pdf2md` → fallback Calibre (dotychczasowe zachowanie zachowane, zero regresu gdy pdf2md nie zainstalowany).
- Wersjonowanie kontraktu: `pdf2md --version` do pola `Tool.version`; przy niekompatybilnej wersji czytelny błąd, nie krzak.
- DRM/hasło w PDF: jeśli pdf2md zwróci błąd — pokaż jego log (wzorzec `_log_fragment`).

### Kryteria akceptacji
- [ ] `epubforge convert scan.pdf out.epub --engine pdf2md` działa przy zainstalowanym pdf2md (test z mockiem subprocess + test integracyjny za markerem `integration`)
- [ ] `--engine auto` z .pdf wybiera pdf2md gdy dostępny, inaczej Calibre
- [ ] GUI: dialog PDF oferuje wybór silnika; handoff otwiera pdf2md
- [ ] Brak pdf2md = zachowanie identyczne jak przed etapem (testy regresji przechodzą)

---

## ⬆️ Etap 23 — Upgrade EPUB 2 → 3

**Gałąź:** `feature/stage-23-epub-upgrade`
**Czas:** ~4 h
**Cel:** jedna komenda modernizująca pakiet: `epubforge upgrade book.epub`.

### Co powstanie
- `src/epubforge/converters/upgrade.py` (czysta logika na `Epub`, reuse modułu `toc`)
- CLI `epubforge upgrade` (`--dry-run` z Etapu 17, `--keep-ncx/--drop-ncx`, domyślnie keep)
- Przycisk w zakładce Metadane lub Fixer („Uaktualnij do EPUB 3")
- `tests/test_upgrade.py` + fixture EPUB 2 (rozszerzyć `make_sample_epub.py`)

### Zakres transformacji
1. `<package version="2.0">` → `version="3.0"`
2. **nav.xhtml** z NCX (generator TOC już istnieje — `toc/generator`/`writer`); wpis do manifestu z `properties="nav"`
3. `<guide>` → `landmarks` w nav.xhtml (mapowanie typów: cover/toc/text → `epub:type`)
4. `<meta property="dcterms:modified">` (wymagane w EPUB 3; format `CCYY-MM-DDThh:mm:ssZ`)
5. `dc:identifier` ↔ `unique-identifier` — upewnij się, że atrybut wskazuje istniejący id (dodaj id gdy brak)
6. `dc:date` z `opf:event` → czysty `dc:date` (atrybut `opf:event` nie istnieje w 3.x)
7. NCX zostaje domyślnie (kompatybilność wsteczna czytników) — `--drop-ncx` usuwa plik + wpis manifestu + atrybut `toc` ze spine

### ⚠️ Pułapki
- **To edycja w miejscu struktur OPF** — wszystkie operacje przez utwardzony parser (Etap 15) i z zachowaniem nieznanych elementów (wzorzec `Metadata.to_opf`: nie ruszaj tego, czego nie celujesz).
- DOCTYPE XHTML 1.1 w dokumentach treści jest legalny w EPUB 3 — **nie przepisuj dokumentów treści**, tylko pakiet+nav (minimalny zakres = mniejsze ryzyko).
- Walidacja końcowa: jeśli EpubCheck dostępny, uruchom go po upgrade w teście integracyjnym; cel = **0 błędów** (warningi dopuszczalne).
- Idempotentność: upgrade na EPUB 3 = no-op z komunikatem.

### Kryteria akceptacji
- [ ] Fixture EPUB 2 po upgrade przechodzi EpubCheck jako EPUB 3 (integracyjnie)
- [ ] nav.xhtml odzwierciedla NCX (kolejność + zagnieżdżenie); landmarks z guide
- [ ] `dcterms:modified` obecne i w poprawnym formacie
- [ ] `--dry-run` pokazuje pełny plan zmian; `--drop-ncx` czyści spójnie
- [ ] Upgrade na EPUB 3 = no-op

---

## 🏷️ Stage gate v2.3
**Tag:** `git tag v2.3.0`.

---

✅ zrobiony ## 🔤 Etap 24 — Subsetting fontów

**Gałąź:** `feature/stage-24-font-subset`
**Czas:** ~4 h
**Cel:** zamiast tylko usuwać fonty (obecny fixer) — przycinać je do faktycznie użytych znaków (typowo −70…−90 % rozmiaru fontu).

### Co powstanie
- `src/epubforge/fixers/fonts.py` — `subset_fonts(epub, options) -> FontReport` (fonttools — **extra** `[fonts]`, leniwie)
- CLI: `epubforge fix --subset-fonts`; opcja w GUI Fixer obok „usuń fonty"; krok receptur
- `tests/test_fonts.py` (mały font testowy w fixtures — np. wygenerowany fontTools albo dołączony font OFL)

### ⚠️ Pułapki
- **Zbiór znaków**: przejdź WSZYSTKIE dokumenty spine + wartości `content` w CSS; dodaj zawsze podstawowy zakres (ASCII + polskie znaki + interpunkcja typograficzna „”—…­ oraz `U+00AD`!) — po hyphenacji/typografii znaki te muszą być w foncie.
- **WOFF2 wymaga brotli** — dodaj do extra `[fonts]`; brak → pomiń pliki .woff2 z ostrzeżeniem zamiast wywału.
- **Licencje fontów** — część EULA zabrania modyfikacji. Pokaż ostrzeżenie w GUI/CLI (jak przy soft-hyphen) i odnotuj w raporcie; nie próbuj czytać licencji automatycznie.
- Zapisuj tylko gdy mniejszy (jak w Etapie 20); zachowaj format (ttf→ttf, otf→otf, woff→woff).
- Font używany przez `@font-face` z `unicode-range` — jeżeli obecny, nie zawężaj poniżej deklarowanego zakresu (bezpieczniej: pomiń taki font z notą w raporcie).

### Kryteria akceptacji
- [x] Po subsetcie wszystkie glify użyte w treści renderują się (test: cmap fontu zawiera każdy codepoint z treści)
- [x] `U+00AD`, „”, —, … zawsze zachowane
- [x] Raport: rozmiar przed/po per font
- [x] .woff2 bez brotli → ostrzeżenie, nie błąd; EpubCheck zielony po operacji

---

✅ zrobiony ## ♿ Etap 25 — Audyt dostępności (DAISY Ace)

**Gałąź:** `feature/stage-25-a11y`
**Czas:** ~3 h
**Cel:** raport dostępności (European Accessibility Act obowiązuje e-booki od 2025) — wzorzec integracji identyczny jak EpubCheck.

### Co powstanie
- Detekcja `Tools.ace()` (npm global: `ace` w PATH) — opcjonalne narzędzie
- `src/epubforge/validators/ace.py`: `run_ace(epub_path, ace, *, timeout)` → parsowanie `report.json` (defensywnie, wzorzec `epubcheck.py`)
- CLI `epubforge a11y book.epub [--json out.json]`
- Zakładka Walidacja: przełącznik EpubCheck / Ace (albo druga sekcja wyników)
- Fixtures: 2–3 przykładowe raporty JSON Ace w `tests/fixtures/ace/`

### ⚠️ Pułapki
- Ace pisze raport do **katalogu** (`--outdir`) — temp dir jak w `run_epubcheck`; JSON to `report.json` w środku.
- Format raportu Ace (osie `assertions`/`earl:result`) bywa zmienny między wersjami — każde pole przez `.get`, mapowanie severity (`critical/serious/moderate/minor` → istniejące `Severity`).
- Node/npm w PATH to warunek — komunikat o instalacji z linkiem (jak dla Javy przy EpubCheck).
- Wyniki wskazują pliki wewnętrzne → reuse mechanizmu klikalnych błędów z zakładki Walidacja.

### Kryteria akceptacji
- [x] Raport Ace sparsowany do wspólnych struktur (`ValidationMessage`-podobnych) na fixtures
- [x] Brak ace = funkcja wyszarzona z instrukcją instalacji (bez błędu)
- [x] Dwuklik wyniku skacze do pliku/linii w Edytorze (gdzie dotyczy)

---

✅ zrobiony ## 🌐 Etap 26 — Metadane z ISBN i Biblioteki Narodowej (opt‑in)

**Gałąź:** `feature/stage-26-isbn`
**Czas:** ~3 h
**Cel:** przycisk „Pobierz metadane…" w zakładce Metadane + warstwa providerów pod Etapy 28–30. **Pierwszy kod sieciowy w projekcie** — świadomie odizolowany.

### Co powstanie
- `src/epubforge/bookmeta/` — nowy, samodzielny podpakiet (zero importów z `gui/`; kandydat do późniejszej ekstrakcji jako `chodzkos-bookmeta`, wzorzec gui-kit):
  - `model.py`: dataclass `BookRecord` (title, creators, publisher, date, description, language, isbn, page_count, subjects, series, source) — superset dzisiejszej `Metadata`,
  - `isbn.py`: `validate_isbn(text) -> str | None` — normalizacja (myślniki/spacje), sumy kontrolne ISBN‑10/13; niepoprawny → zero zapytań,
  - `providers/base.py`: `Provider` (Protocol) z `fetch_by_isbn(isbn, *, timeout=5)`,
  - `providers/bn.py`: **Biblioteka Narodowa** — oficjalne API `data.bn.org.pl` (JSON, bez limitów, bez klucza); najlepsze źródło dla polskich książek: wydawca, rok, liczba stron i **deskryptory przedmiotowe BN** (gotowe tagi: epoki, miejsca, postacie, organizacje),
  - `providers/openlibrary.py`, `providers/googlebooks.py`: fallback dla wydań obcojęzycznych (zakres jak w pierwotnej wersji etapu),
  - `chain.py`: `fetch_by_isbn(isbn)` — kolejność BN → Open Library → Google Books; scalanie per pole (puste pola dopełniane z kolejnych źródeł — BN nie ma opisów marketingowych, opis może dojść z GB).
- GUI: dialog z podglądem pobranych pól i checkboxami „które nadpisać" (nigdy ciche nadpisanie); deskryptory BN jako osobna lista propozycji tagów → zapis do `dc:subject` (mapowanie na taksonomię dopiero w Etapie 29).
- Liczba stron wydania papierowego → `<meta property="schema:numberOfPages">` w OPF (tylko EPUB 3; EPUB 2 → pomiń z notą) — obok istniejącego wyliczania stron w EpubForge.
- `tests/test_bookmeta_providers.py` (mock urlopen — wzorzec z chodzkos-detection).

### ⚠️ Pułapki
- **Tylko `https`**, twardy timeout, limit rozmiaru odpowiedzi `resp.read(MAX_BYTES)` (lekcja D2 z audytu chodzkos-detection); walidacja ISBN przed zapytaniem.
- Wywołanie sieciowe wyłącznie z akcji użytkownika (guzik), nigdy automatycznie przy otwarciu pliku; w `Worker` (nie blokuj UI). Brak wyniku/HTTP błąd → `None` + status w GUI; bez wyjątków w warstwie UI.
- Nie dodawaj zależności `requests` — stdlib `urllib` wystarcza i trzyma zero nowych deps.
- Endpoint i format odpowiedzi BN **zweryfikuj w dokumentacji** (`data.bn.org.pl/docs`) — nie zgaduj pól; liczba stron w BN to tekst z MARC 300 („320 s.") — parsuj defensywnie, brak → `None`.
- Deskryptory BN bywają liczne — checkboxy per deskryptor, domyślnie **odznaczone**.

### Kryteria akceptacji
- [x] Polski ISBN → rekord z BN (wydawca, rok, liczba stron, deskryptory); obcy ISBN → OL/GB
- [x] Zły ISBN (suma kontrolna) → walidacja lokalna, zero zapytań
- [x] Zatwierdzenie nadpisuje TYLKO zaznaczone pola; timeout/offline → czytelny status, GUI żyje
- [x] Testy bez sieci (mock), + 1 test integracyjny za markerem `integration`

---

⏸️ odłożony ## 📦 Etap 27 — Dystrybucja: PyPI, Linux/macOS, winget

> **Status: odłożony.** Nie wchodził w skład wydania v3.0.0 — brama v3.0 została zamknięta z kompletem funkcji (Etapy 24–26, 28–30), ale bez pełnej dystrybucji. Release `v3.0.0` dostarcza wyłącznie binaria Windows (`epubforge.exe`, `epubforge-setup.exe`); PyPI, artefakty Linux/macOS i manifest winget przeniesione do przyszłego wydania. Kryteria akceptacji pozostają niezaznaczone celowo.

**Gałąź:** `feature/stage-27-distribution`
**Czas:** ~4 h
**Cel:** zasięg — instalacja jedną komendą na każdej platformie.

### Zakres
1. **PyPI** (wymaga domkniętego REL‑1 z Etapu 15): workflow `publish.yml` (trusted publishing OIDC, environment `pypi`, uruchamiany na tag `v*` po zielonych testach); `pipx install epubforge` w README.
2. **Linux**: job w `build.yml` na `ubuntu-latest` — PyInstaller onedir → `epubforge-linux-x86_64.tar.gz`; sanity: start `--version` na runnerze.
3. **macOS**: job na `macos-latest` — onedir → `.zip` (bez podpisu/notaryzacji na start; udokumentuj Gatekeeper w README).
4. **winget**: manifest do `microsoft/winget-pkgs` (instalator Inno już jest; potrzebny stabilny URL z Release + `ProductCode`).
5. README: macierz instalacji per platforma.

### ⚠️ Pułapki
- PyInstaller spec ma ścieżki windowsowe? Sprawdź `datas` (locale/presets/stopwords idą przez `force-include` wheela, ale spec dokleja je osobno) — na Linux/macOS separatory i brak `icon.ico`.
- Qt na Linux w bundlu: doinstaluj w job `libegl1 libxkbcommon0` tylko do testu startu; do paczki PySide6 wystarcza samo (xcb wymaga bibliotek systemowych — udokumentuj `sudo apt install libxcb-cursor0` dla użytkowników).
- winget wymaga **niezmiennego** URL instalatora i wersjonowanego `PackageVersion` — automatyzuj bump manifestu w release workflow (albo świadomie ręcznie na start).
- Trusted publishing: konfiguracja na PyPI (project → publisher: repo+workflow) zanim pierwszy run.

### Kryteria akceptacji
- [ ] `pipx install epubforge` działa (po publikacji)
- [ ] Artefakty Release: `epubforge.exe`, `epubforge-setup.exe`, `epubforge-linux-x86_64.tar.gz`, `epubforge-macos.zip`
- [ ] Każdy artefakt odpala `epubforge --version` na swoim runnerze (smoke w CI)
- [ ] Manifest winget zaakceptowany (lub PR otwarty)

---

## 🏷️ Stage gate v3.0 — ✅ zamknięta (tag `v3.0.0`)
**Tag:** `git tag v3.0.0` — komplet funkcji v3 (Etapy 24–26, 28–30). Zrzuty ekranu, wpis CHANGELOG, aktualizacja `FEATURES.md` — zrobione. **Etap 27 (pełna dystrybucja PyPI/Linux/macOS/winget) odłożony** — v3.0.0 dostarcza tylko binaria Windows; Etapy 28–30 domknięto razem z tą bramą zamiast osobnego wydania v3.1.

---

✅ zrobiony ## 📖 Etap 28 — Provider LubimyCzytac + dopasowanie bez ISBN

**Gałąź:** `feature/stage-28-lubimyczytac`
**Czas:** ~4 h
**Cel:** opisy, cykle, oceny i liczba stron z lubimyczytac.pl (scraper pisany **od zera** — nie portujemy kodu GPL z calibre-web ani pluginów Calibre) + dopasowanie po tytule/autorze dla plików bez ISBN.

### Co powstanie
- `bookmeta/providers/lubimyczytac.py`: wyszukiwanie po ISBN oraz tytuł+autor → `list[Candidate]`; parsowanie strony książki: opis, liczba stron, cykl/saga, kategorie (surowe stringi do `subjects`).
- `bookmeta/match.py`: normalizacja (diakrytyki, wielkość liter, interpunkcja, podtytuł po „:") + scoring `difflib.SequenceMatcher` (zero nowych deps); próg pewności w stałej.
- Ekstrakcja ISBN z treści: gdy metadane go nie mają — regex po pierwszych dokumentach spine (strona redakcyjna); częsty przypadek konwertowanych EPUB‑ów.
- `bookmeta/cache.py`: cache SQLite w katalogu configu (klucz provider+zapytanie, TTL) + rate limiter (min. odstęp między żądaniami, bez równoległości) + User‑Agent identyfikujący EpubForge.
- GUI: wiele kandydatów → dialog wyboru (tytuł/autor/rok/score).

### ⚠️ Pułapki
- **KROK 0 obowiązkowy**: zbadaj realną strukturę strony LC — jeśli strona książki ma `application/ld+json` (schema.org `Book`), parsuj JSON‑LD zamiast selektorów HTML (dużo stabilniejsze); HTML tylko dla pól, których w JSON‑LD nie ma.
- Parsowanie HTML bez nowych zależności: `html.parser` ze stdlib, defensywnie — **każde pole opcjonalne**, zmiana layoutu → `None`, nigdy wyjątek; testy wyłącznie na zapisanych fixtures HTML.
- Scraping grzecznościowy: jeden request na raz, cache obowiązkowy, szanuj robots.txt; provider oznaczony w kodzie/README jako „best effort" (może przestać działać po redesignie serwisu).
- Fuzzy match: poniżej progu **nigdy** auto‑zapis — zawsze wybór użytkownika.

### Kryteria akceptacji
- [x] Książka obecna w LC (po ISBN) → opis/strony/cykl w podglądzie
- [x] Plik bez ISBN → kandydaci po tytule/autorze, wybór ręczny, poprawny zapis
- [x] Drugi fetch tej samej książki → 0 żądań HTTP (cache)
- [x] Testy bez sieci (fixtures); zepsuty layout → provider zwraca `None`, reszta łańcucha działa

---

✅ zrobiony ## 🏷️ Etap 29 — Taksonomia tagów + tagowanie AI (opt‑in)

**Gałąź:** `feature/stage-29-tags`
**Czas:** ~4 h
**Cel:** maks. **10 tagów po polsku** z kaskady trzech źródeł: (1) deskryptory BN / kategorie LC+GB → mapowanie na taksonomię (zero AI, deterministyczne), (2) AI na opisie + spisie treści, (3) AI na próbce treści tylko gdy nigdzie nie ma opisu. Domyślnie **Ollama lokalnie**; chmura (Claude, OpenAI, Gemini, DeepSeek, GLM) jako opcja.

### Co powstanie
- `src/epubforge/data/taxonomy_pl.toml` (TOML jak receptury; użytkownik może podłożyć własny plik w katalogu configu): kategorie `[gatunek]` `[epoka]` `[miejsce]` `[tematy]` — tag kanoniczny PL + synonimy (sci fi = SF = science fiction → jeden kanon) + mapowania deskryptorów BN i kategorii LC/GB; startowy zestaw wg wymagań: historyczna, naukowa, powieść, beletrystyka, fantastyka, science fiction, kryminał, poradnik…; II wojna światowa, średniowiecze, starożytność…; space opera, saga, cyberpunk, utopia, śledztwo…; marynistyka, Arktyka, technika wojskowa….
- `bookmeta/taxonomy.py`: `load_taxonomy()` (tomllib), `map_subjects(raw) -> MappedTags` (kanoniczne + niezmapowane jako propozycje „poza taksonomią"), deduplikacja po synonimach, limit 10 z priorytetem gatunek → epoka/miejsce → tematy.
- `bookmeta/ai.py`: klient endpointu **zgodnego z OpenAI chat completions** (stdlib urllib, temperature 0) — jeden protokół obsługuje wszystko: presety `ollama` (**domyślny**, `http://localhost:11434/v1`), `anthropic`, `openai`, `gemini`, `deepseek`, `glm`; base_url/model edytowalne; klucz API **wyłącznie ze zmiennej środowiskowej** (w configu tylko jej nazwa).
- Klasyfikacja: gatunek/epoka/miejsce/tematy **tylko z listy zamkniętej** taksonomii (lista wklejona do promptu; walidacja odpowiedzi, 1 retry); postacie/organizacje (Piłsudski, III Rzesza, Armia Czerwona…) — ekstrakcja otwarta z normalizacją.
- Polityka scalania: *zachowaj istniejące* / *dopisz brakujące* (domyślna) / *zastąp*; zapis do `dc:subject` (Calibre importuje je jako tagi).
- GUI: sekcja „Tagi" w zakładce Metadane — „Zaproponuj tagi" → lista propozycji z checkboxami i źródłem (BN/LC/AI); ustawienia AI w konfiguracji GUI.

### ⚠️ Pułapki
- AI zawsze **opt‑in**, nigdy automatycznie; brak Ollamy/endpointu → czytelny komunikat z instrukcją, kaskada (1) działa bez AI.
- Wyjątek od zasady https: `http` dozwolone **tylko** dla loopback/adresów prywatnych RFC 1918 (Ollama/LiteLLM w LAN); hosty publiczne wyłącznie https; limit rozmiaru odpowiedzi jak w D2.
- Presety base_url chmur **zweryfikuj na dzień implementacji** (Anthropic i Gemini mają osobne ścieżki zgodności z OpenAI API).
- Model potrafi zwrócić śmieci mimo próśb o JSON — walidacja przeciw taksonomii, tag spoza listy → odrzuć; testy z mockiem klienta, zero realnych wywołań.
- Prompt klasyfikacyjny po polsku; wejście przycięte (opis + TOC; próbka treści maks. ~5 tys. słów z początku spine).

### Kryteria akceptacji
- [x] Książka z deskryptorami BN → tagi PL bez żadnego wywołania AI
- [x] Opis bez deskryptorów → AI (mock) → tagi wyłącznie z taksonomii + ewentualne postacie/organizacje
- [x] Maks. 10 tagów, kanon PL, synonimy scalone; polityka „dopisz" nie duplikuje istniejących
- [x] Zapis do `dc:subject`; import w Calibre pokazuje je jako tagi

---

✅ zrobiony ## 📦 Etap 30 — Wzbogacanie hurtowe + calibredb

**Gałąź:** `feature/stage-30-enrich-batch`
**Czas:** ~3 h
**Cel:** `epubforge enrich` dla plików i katalogów (batch z Etapu 17) oraz hurtowe wzbogacenie biblioteki **Calibre przez `calibredb`** — zamiast pisania i utrzymywania pluginu Calibre.

### Co powstanie
- CLI `epubforge enrich <pliki/katalog> [--fields …] [--tags] [--policy fill|append|overwrite] [--dry-run] [--report out.csv|json]` — reuse batch/dry‑run (Etap 17), postęp i anulowanie (Etap 19).
- Raport per książka: dopasowanie (isbn/fuzzy/brak), źródło, pola zmienione/pominięte, błędy; podsumowanie (znalezione/nieznalezione/z cache).
- `--calibre-library PATH`: odczyt `calibredb list --for-machine` → wzbogacenie przez bookmeta → zapis `calibredb set_metadata`; detekcja `calibredb` przez `Tools` (obok istniejącej detekcji Calibre).
- GUI: akcja hurtowa w istniejącym mechanizmie batch.

### ⚠️ Pułapki
- `calibredb` wymaga **zamkniętego GUI Calibre** (blokada bazy) — preflight z czytelnym komunikatem zamiast tajemniczego błędu; **nigdy** nie modyfikuj plików biblioteki Calibre bezpośrednio na dysku.
- Rate limiting współdzielony (jedna instancja limitera na proces) — hurt nie omija odstępów między żądaniami LC; cache z Etapu 28 robi retry tanim.
- Domyślne polityki w hurcie: `fill` dla pól, `append` dla tagów — nic nie znika bez jawnej decyzji (`overwrite` tylko wprost).
- `--dry-run` obowiązkowo pokazuje pełny plan zmian per książka przed jakimkolwiek zapisem.

### Kryteria akceptacji
- [x] Katalog ~50 EPUB‑ów → raport znalezione/nieznalezione/z cache; anulowanie działa
- [x] `--dry-run` → 0 zapisów, pełny plan; polityki fill/append/overwrite zgodne z opisem
- [x] Biblioteka Calibre: opis/strony/tagi uzupełnione przez calibredb; przy `fill` istniejące wartości nietknięte
- [x] Otwarty Calibre GUI → czytelny komunikat, zero zmian

---

## 🏷️ Stage gate v3.1 — ✅ złożona w `v3.0.0` (bez osobnego taga)
**Tag:** ~~`git tag v3.1.0`~~ — wzbogacanie metadanych i tagi (Etapy 28–30). Zamiast osobnego wydania Etapy 28–30 domknięto razem z bramą v3.0 pod tagiem **`v3.0.0`** (nie było wcześniejszego taga 3.0). Zrzuty ekranu, wpis CHANGELOG i aktualizacja `FEATURES.md` — zrobione w ramach v3.0.0.

---

## 📊 Podsumowanie czasowe

| Etap | Temat | Czas | Wydanie |
|---|---|---|---|
| 15 | Naprawy z audytu | 4 h | v2.0.1 |
| 16 | Typografia PL | 4 h | v2.1 |
| 17 | Batch + dry‑run | 3 h | v2.1 |
| 18 | Receptury | 3 h | v2.1 |
| 19 | Anulowanie/postęp | 3 h | v2.2 |
| 20 | Optymalizacja obrazów | 4 h | v2.2 |
| 21 | Szukaj/zamień | 4 h | v2.2 |
| 22 | Integracja pdf2md | 3 h | v2.3 |
| 23 | Upgrade EPUB 2→3 | 4 h | v2.3 |
| 24 | Subsetting fontów | 4 h | v3.0.0 |
| 25 | Ace (a11y) | 3 h | v3.0.0 |
| 26 | Metadane ISBN/BN | 3 h | v3.0.0 |
| 27 | Dystrybucja | 4 h | _odłożone_ |
| 28 | LubimyCzytac + fuzzy match | 4 h | v3.0.0 |
| 29 | Taksonomia + tagi AI | 4 h | v3.0.0 |
| 30 | Enrich hurtowo + calibredb | 3 h | v3.0.0 |

**~57 h** — realistycznie 3–4 miesiące popołudniami. Etapy 20/21/24/25/26 są od siebie niezależne — kolejność wewnątrz wydania dowolna. Etapy 28–30 budują na Etapie 26 (kolejność: 26 → 28 → 29/30; Etap 29 nie wymaga 28, ale korzysta z jego kategorii LC).

---
---

# 💬 Prompty dla Claude Code

Gotowe do wklejenia. Konwencja jak w `PROMPTS.md`: przeczytaj kontekst → gałąź → implementacja → testy/lint/mypy → commit → propozycja PR. **Nie pushować automatycznie.** Komentarze w kodzie po polsku.

---

✅ zrobiony ## 🧱 Etap 15 — Fundament wydaniowy

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP-epubforge-v3.md (Etap 15)
oraz AUDYT-epubforge.md (pełna lista ustaleń z gotowymi promptami).

ZADANIE: Realizujemy Etap 15 — naprawy z audytu, jako SERIA małych PR-ów
(jeden temat = jedna gałąź fix/..., zgodnie z konwencją repo).

Kolejność:
1. SEC-1 (wspólny utwardzony parser XML) — wykonaj prompt "SEC-1" z AUDYT-epubforge.md.
2. COR-1 (fix na kopii w to_mobi/to_kfx) — prompt "COR-1" z audytu.
3. REL-2 (spójna wersja/status) — prompt "REL-2".
4. REL-3 (lock zależności) — prompt "REL-3"; przedstaw wybór uv vs pip-tools PRZED zmianą.
5. SEC-2, SEC-3, SEC-4, COR-2, TEST-1, QUAL-1 — odpowiednie prompty z audytu,
   można łączyć drobne w jeden PR "chore(hardening)".
6. REL-1 (PyPI) — NA KOŃCU i tylko po mojej decyzji: najpierw wypisz, czy
   chodzkos-gui-kit jest już na PyPI; jeśli nie — wykonaj wyłącznie wariant
   README (bez zmiany zależności) i zanotuj blokadę w CHANGELOG.

Po każdym temacie: pytest + ruff + mypy (wszystkie 3 platformy jak w CI),
conventional commit, propozycja PR. Po zmergowaniu całości zaproponuj tag v2.0.1.
NIE zaczynaj żadnego etapu 16+ przed domknięciem tego etapu.
```

---

✅ zrobiony ## 🇵🇱 Etap 16 — Typografia polska

```
Realizujemy Etap 16 z ROADMAP-epubforge-v3.md — "Fixer typografii polskiej".
Przeczytaj sekcję Etapu 16 (API, pułapki) oraz src/epubforge/fixers/hyphenator.py
(wzorzec przejścia po drzewie text/tail) i src/epubforge/toc/_xml.py (wzorzec
serializacji zachowującej DOCTYPE).

Wykonaj:
1. main + pull, gałąź: feature/stage-16-typography
2. Utwórz src/epubforge/fixers/typography.py:
   - TypographyOptions i fix_typography(epub, options) -> TypographyReport
     zgodnie z API z roadmapy (języki pl/en/de dobierają znaki cudzysłowów),
   - PARSOWANIE wyłącznie utwardzonym parserem z Etapu 15,
   - SERIALIZACJA zachowuje DOCTYPE i deklarację XML (wzorzec toc/_xml.serialize_xml
     — NIE kopiuj _serialize_xml z hyphenatora, on gubi doctype),
   - stan parowania cudzysłowów niesiony przez granice tagów w obrębie akapitu,
   - guard isinstance(child.tag, str) przy rekurencji (komentarze lxml!),
   - regexy słów tolerują U+00AD wewnątrz słów,
   - skip_tags jak w hyphenatorze; nie ruszaj atrybutów.
3. Reguły (każda za osobną flagą):
   - fix_quotes: proste " i ' → pary typograficzne wg języka (pl „…”, en “…”, de „…“),
   - fix_dashes: " - " między słowami → " — " (pl); "-" na początku <p> (dialog) → "— ",
     NIE ruszaj łączników wewnątrz słów (biało-czerwony),
   - fix_ellipsis: "..." → "…",
   - nbsp_single_letters (pl): po samotnych a/i/o/u/w/z/A/I/O/U/W/Z spacja → U+00A0,
   - nbsp_numbers_units (domyślnie OFF): "10 km", "XX w." → twarda spacja.
4. TypographyReport: dict reguła → liczba podmian, per plik i sumarycznie.
5. CLI: src/epubforge/cli/typo.py — `epubforge typo book.epub --lang pl`
   (+ rejestracja w cli/main.py; wzorzec: cli/hyphenate.py). Teksty przez _() (i18n).
6. GUI: w zakładce Fixer sekcja "Typografia" (checkboxy + dropdown języka),
   uruchamiana przez Worker jak pozostałe fixery; wynik (liczby podmian) do LogView.
7. tests/test_typography.py: każda reguła osobno, kombinacje, parowanie cudzysłowów
   przez <em>, idempotentność (2. przebieg = 0 podmian), code/pre nietknięte,
   DOCTYPE zachowany po round-tripie, warianty en/de.
8. pybabel extract + update katalogów pl/en/de dla nowych stringów; skompiluj .mo.
9. pytest, ruff, mypy (3 platformy). Commit: "feat(fixers): polish typography fixer (quotes, dashes, nbsp)"
10. Zaproponuj PR.

PRZYPOMNIENIE: komentarze po polsku, nie pushuj bez zatwierdzenia.
```

---

## 📚 Etap 17 — Batch + dry-run

```
Realizujemy Etap 17 z ROADMAP-epubforge-v3.md — "Batch w CLI + --dry-run/diff".
Przeczytaj sekcję Etapu 17 oraz src/epubforge/core/epub.py (bufor _modified/_deleted)
i src/epubforge/gui/editor_files.py (is_editable, decode_text).

Wykonaj:
1. main + pull, gałąź: feature/stage-17-batch-dryrun
2. Epub: dodaj publiczne pending_changes() -> PendingChanges
   (frozen dataclass: modified: dict[str, bytes], deleted: frozenset[str]) —
   kopia stanu bufora, bez ujawniania wewnętrznych struktur.
3. src/epubforge/cli/_batch.py — wspólny runner:
   - wejście: lista plików (nargs="+"), dedup z zachowaniem kolejności,
   - --jobs N (domyślnie 1): ProcessPoolExecutor; funkcja robocza TOP-LEVEL
     (picklowalna), zwraca (path, ok, message, seconds),
   - raport tabelą rich (plik / status / czas), kod wyjścia 1 gdy cokolwiek padło.
4. Podłącz batch do komend: fix, hyphenate, typo (presets zostawiamy 1-plikowe,
   bo dzielą flagi z fix — sprawdź i zdecyduj, opisz w PR).
5. --dry-run w fix / hyphenate / typo:
   - wykonaj fixery na otwartym Epub, NIE wołaj save(),
   - dla plików tekstowych (editor_files.is_editable) unified diff
     (difflib.unified_diff na decode_text, limit 40 linii/plik; --diff-full znosi limit),
   - dla binarnych: nazwa + delta rozmiaru,
   - wypisz podsumowanie "N plików zmienionych, M usuniętych; nic nie zapisano".
6. multiprocessing.freeze_support() na początku cli/main.py:main() —
   pułapka PyInstaller/Windows (zostaw komentarz dlaczego).
7. tests/test_cli_batch.py: batch happy-path, jeden plik uszkodzony → exit 1 +
   pozostałe przetworzone; test --dry-run: hash pliku na dysku identyczny przed/po.
8. pytest, ruff, mypy. Commit: "feat(cli): batch processing (--jobs) and --dry-run diffs"
9. Zaproponuj PR.
```

---

## 🧪 Etap 18 — Receptury

```
Realizujemy Etap 18 z ROADMAP-epubforge-v3.md — "Receptury (pipeline)".
Przeczytaj sekcję Etapu 18 (format TOML, pułapki), fixers/__init__.py,
converters/to_mobi.py i cli/_batch.py (z Etapu 17).

Wykonaj:
1. main + pull, gałąź: feature/stage-18-recipes
2. src/epubforge/recipes.py:
   - Recipe / RecipeStep (dataclasses) + load_recipe(path) (tomllib;
     dla py3.10 dodaj do dependencies "tomli; python_version<'3.11'"),
   - REJESTR kroków: jawny dict op -> (callable, OptionsClass); kroki fixerów:
     fix_css, typography, hyphenate, apply_preset; kroki eksportu: to_mobi, to_kfx,
     to_epub NIE (wejściem receptury jest już EPUB),
   - walidacja: nieznany op / nieznana opcja → RecipeError z nazwą receptury,
     numerem kroku i listą dozwolonych wartości,
   - run_recipe(recipe, epub_path, out_dir, emit_line, should_cancel=None):
     faza 1 — wszystkie kroki fixerów na JEDNYM otwartym Epub + jeden save();
     faza 2 — kroki eksportu na zapisanym pliku (pamiętaj: eksport nie mutuje
     wejścia — gwarancja z Etapu 15/COR-1),
   - wbudowane receptury jako pliki TOML w src/epubforge/recipes_builtin/
     (kindle-pl, czytnik-epub — treść z roadmapy) + force-include w pyproject,
   - discover_recipes(): wbudowane + config_dir()/recipes/*.toml (własne
     przykrywają wbudowane po name).
3. CLI: src/epubforge/cli/run.py — `epubforge run <nazwa|ścieżka.toml> pliki...
   [--out-dir DIR] [--list] [--dry-run]`; batch przez _batch; --dry-run obejmuje
   tylko fazę fixerów (eksport pomijany z adnotacją).
4. GUI: przycisk "Uruchom recepturę…" (zdecyduj: pasek górny czy zakładka Fixer —
   uzasadnij w PR): dialog z dropdownem receptur, FileList (z gui-kit) i logiem;
   wykonanie w Worker.
5. tests/test_recipes.py: load poprawnej/błędnej receptury, rejestr waliduje opcje,
   run_recipe z mockami eksportu, własna receptura przykrywa wbudowaną.
6. pybabel extract/update dla nowych stringów.
7. pytest, ruff, mypy. Commit: "feat(recipes): TOML pipelines (epubforge run)"
8. Zaproponuj PR. Po merge zaproponuj tag v2.1.0 (stage gate — sprawdź czy
   Etapy 16-18 są zmergowane; zaktualizuj README/CHANGELOG/FEATURES.md).
```

---

## ⏹️ Etap 19 — Anulowanie i postęp

```
Realizujemy Etap 19 z ROADMAP-epubforge-v3.md — "Anulowanie i postęp".
Przeczytaj sekcję Etapu 19, src/epubforge/gui/workers.py i konwertery.

Wykonaj:
1. main + pull, gałąź: feature/stage-19-cancel-progress
2. workers.py:
   - Worker: pole _cancel_event (threading.Event), metoda cancel(), property
     is_cancelled; callable dostaje TRZECI hook should_cancel: Callable[[], bool]
     (zachowaj zgodność: dotychczasowe callable przyjmujące 2 hooki mają dalej
     działać — zdecyduj: introspekcja sygnatury czy nowy parametr konstruktora;
     uzasadnij w PR),
   - nowy sygnał cancelled (bez argumentów); anulowanie NIE emituje failed,
   - ŻADNEGO QThread.terminate() — wyłącznie kooperacyjnie.
3. run_subprocess_streaming(cmd, on_line, cwd=None, should_cancel=None):
   - między liniami sprawdzaj should_cancel(); przy anulowaniu proc.terminate(),
     po 3 s proc.kill(); pętla czytania w try/finally z proc.wait(),
   - zwróć też informację "anulowano" (zmień zwrot na małą dataclass ProcessResult
     zamiast gołego int — zaktualizuj wywołania).
4. Konwertery: dodaj strumieniowe warianty wykonania z parsowaniem postępu
   Calibre (linie zawierające "NN%") → emit_progress(current=NN, total=100).
   Zakładki Konwerter/Kindle przechodzą na wariant strumieniowy.
5. GUI: przycisk Anuluj + QProgressBar w zakładkach Konwerter, Kindle (kfx),
   Walidacja; stan przycisków spójny (Anuluj aktywny tylko podczas pracy);
   po anulowaniu wpis "Anulowano" (poziom warn) w LogView.
6. Nieprzerywalność zapisu: w miejscach z _write_epub/os.replace nie sprawdzaj
   should_cancel między utworzeniem .tmp a replace (komentarz w kodzie).
7. tests/gui/test_workers_cancel.py: subprocess-atrapa
   [sys.executable, "-c", "import time; time.sleep(60)"] — cancel ubija w < 5 s,
   emitowany sygnał cancelled, brak failed; test braku regresji dla starych callable.
8. pytest (offscreen), ruff, mypy. Commit: "feat(gui): cancellable workers with progress"
9. Zaproponuj PR.
```

---

## 🖼️ Etap 20 — Optymalizacja obrazów

```
Realizujemy Etap 20 z ROADMAP-epubforge-v3.md — "Optymalizacja obrazów".
Przeczytaj sekcję Etapu 20 (API, pułapki) i fixers/css_fixer.py (wzorzec fixera).

Wykonaj:
1. main + pull, gałąź: feature/stage-20-images
2. pyproject.toml: extra images = ["Pillow>=10.0"]; import Pillow leniwie
   w funkcji z czytelnym błędem "pip install epubforge[images]" (wzorzec langdetect
   w stats.py).
3. src/epubforge/fixers/images.py: ImageFixOptions + optimize_images(epub, options)
   -> ImageReport, zgodnie z API z roadmapy. Kluczowe zasady:
   - format pliku NIGDY się nie zmienia (jpg→jpg, png→png),
   - zapis do bufora epub.write_file TYLKO gdy wynik mniejszy od oryginału,
   - okładka: wykryj properties="cover-image" (EPUB3) i <meta name="cover"> (EPUB2);
     przy skip_cover=True pomiń,
   - PNG z alfą: zachowaj RGBA; palety (tryb P) konwertuj bezpiecznie,
   - grayscale: convert("L") tylko na jawne żądanie,
   - strip_metadata: zapisuj bez exif/icc_profile,
   - SVG pomijaj (to tekst).
4. CLI: rozszerz `epubforge fix` o --optimize-images, --max-px, --jpeg-quality,
   --grayscale (działa z --dry-run z Etapu 17: binaria → delta rozmiaru).
5. Rejestr receptur: krok optimize_images.
6. GUI: sekcja "Obrazy" w zakładce Fixer; podsumowanie "zaoszczędzono X MB (−Y%)"
   do LogView.
7. tests/test_images.py: fixtures generowane Pillow w teście (JPEG, PNG-alfa,
   PNG-paleta, mały plik już-optymalny → nietknięty), okładka pomijana,
   EXIF usuwany, raport liczy poprawnie. Testy oznacz skipif przy braku Pillow.
8. pytest, ruff, mypy. Commit: "feat(fixers): image optimization (resize, recompress, grayscale)"
9. Zaproponuj PR.
```

---

## 🔎 Etap 21 — Szukaj i zamień

```
Realizujemy Etap 21 z ROADMAP-epubforge-v3.md — "Szukaj i zamień w całym EPUB".
Przeczytaj sekcję Etapu 21, gui/editor_files.py (is_editable, decode_text,
offset_to_line_col), gui/tabs/editor.py (mechanizm _dirty i skoku do linii —
zobacz też jak robi to zakładka Walidacja).

Wykonaj:
1. main + pull, gałąź: feature/stage-21-search-replace
2. src/epubforge/core/search.py (czysta logika, bez Qt):
   - SearchHit (frozen dataclass) i search_epub(...) zgodnie z API z roadmapy,
   - replace_in_epub(...) -> ReplaceReport (podmiany per plik); zapis WYŁĄCZNIE
     do bufora epub.write_file — utrwalenie należy do użytkownika,
   - regex: re.compile w try/except re.error → SearchPatternError z komunikatem,
   - whole_words: \b + re.UNICODE (test z "żółć"),
   - pliki: editor_files.is_editable + .css/.opf/.ncx; dekodowanie decode_text;
     plik ze znakami zastępczymi � wykluczony z REPLACE (zwróć go w report.skipped
     z powodem) — szukanie dozwolone.
3. GUI: panel Szukaj/Zamień w zakładce Edytor (skrót Ctrl+Shift+F):
   - pola szukaj/zamień, checkboxy (regex, Aa, całe słowa), zakres
     (bieżący plik / cały EPUB),
   - drzewo wyników zgrupowane po pliku (ścieżka → trafienia "linia: podgląd"),
   - dwuklik → otwarcie pliku w edytorze + kursor na trafieniu (reuse skoku
     z Walidacji),
   - "Zamień wszystkie": jeśli bieżący plik ma niezapisane zmiany w CodeEditor,
     najpierw zsynchronizuj przez istniejący mechanizm _dirty (nie zgub edycji!);
     po zamianie odśwież widok bieżącego pliku i znaczniki drzewa,
   - wyszukiwanie całego EPUB w Worker (duże książki), z możliwością anulowania
     (Etap 19).
4. tests/test_search.py: literal/regex/case/whole-words, wyniki linia/kolumna,
   replace do bufora (dysk nietknięty), plik z � pomijany przy replace,
   zły regex → SearchPatternError.
5. tests/gui/test_search_panel.py: podstawowy przepływ (offscreen).
6. pybabel extract/update.
7. pytest, ruff, mypy. Commit: "feat(editor): search & replace across EPUB"
8. Zaproponuj PR. Po merge zaproponuj tag v2.2.0 (gate: Etapy 19-21; README/CHANGELOG).
```

---

## 🔗 Etap 22 — Integracja pdf2md

```
Realizujemy Etap 22 z ROADMAP-epubforge-v3.md — "Integracja pdf2md".
Przeczytaj sekcję Etapu 22, core/detection.py, converters/to_epub.py,
gui/external_tools.py oraz gui/tabs/converter.py (dialog ostrzeżenia PDF).

KROK 0 (OBOWIĄZKOWY, przed jakimkolwiek kodem):
Zbadaj realny interfejs pdf2md — sklonuj/przejrzyj https://github.com/chodzkos/pdf2md
(README, pyproject [project.scripts], moduł cli). Ustal: nazwę binarki, składnię
konwersji, format wyjścia (plik .md? katalog z obrazami?), kody wyjścia, flagę
--version. WYPISZ ustalony kontrakt i czekaj na moje potwierdzenie.
Jeśli pdf2md nie ma stabilnego CLI — zamiast implementacji przygotuj treść issue
do repo pdf2md z propozycją minimalnego kontraktu
(pdf2md convert <in.pdf> -o <out.md> [--images-dir DIR], exit 0/!=0) i ZATRZYMAJ SIĘ.

Po potwierdzeniu kontraktu:
1. main + pull, gałąź: feature/stage-22-pdf2md
2. core/detection.py: Tools.pdf2md() (wzorzec _make_tool: PATH + typowe katalogi;
   detect_version wg ustaleń z kroku 0); dodaj do detect_all i _NO_ARG_DETECTORS;
   pasek statusu narzędzi w GUI pokazuje pdf2md.
3. converters/to_epub.py: engine "pdf2md" (rozszerz Engine Literal):
   - tylko dla .pdf (inne rozszerzenie → ConversionError z komunikatem),
   - TemporaryDirectory: pdf2md → md (+ obrazy); potem istniejąca ścieżka Pandoc
     md → epub z cwd/resource-path wskazującym tempdir (obrazy muszą się osadzić),
   - engine="auto" dla .pdf: pdf2md jeśli wykryty → fallback Calibre (obecne
     zachowanie bez pdf2md ma zostać BITOWO identyczne — testy regresji),
   - błędy pdf2md raportuj przez _log_fragment jak dla innych silników.
4. GUI Konwerter: dialog ostrzeżenia PDF rozszerz o wybór silnika:
   "pdf2md (zalecane)" gdy wykryty / "Calibre (eksperymentalne)"; zapamiętaj
   wybór w configu (klucz pdf_engine).
5. GUI handoff: przycisk "pdf2md" obok Sigil/Calibre (external_tools.launch_tool)
   otwierający bieżący plik PDF w pdf2md — tylko gdy wykryty.
6. tests/test_pdf2md.py: mock subprocess (wzorzec test_converter.py): budowa
   komendy wg kontraktu, łańcuch md→pandoc, auto-fallback, błąd pdf2md → ConversionError.
   Test integracyjny za markerem integration (skipif brak pdf2md w PATH).
7. README: sekcja formatów wejściowych — wiersz PDF wskazuje pdf2md jako zalecany
   silnik; docs/user-guide.md analogicznie.
8. pytest, ruff, mypy. Commit: "feat(converters): pdf2md engine for PDF input + GUI handoff"
9. Zaproponuj PR.
```

---

## ⬆️ Etap 23 — Upgrade EPUB 2→3

```
Realizujemy Etap 23 z ROADMAP-epubforge-v3.md — "Upgrade EPUB 2 → 3".
Przeczytaj sekcję Etapu 23, moduły toc/ (reader, generator, writer, model),
core/metadata.py (wzorzec edycji OPF nie ruszającej reszty) i validators/epubcheck.py.

Wykonaj:
1. main + pull, gałąź: feature/stage-23-epub-upgrade
2. src/epubforge/converters/upgrade.py: upgrade_to_epub3(epub, *, keep_ncx=True)
   -> UpgradeReport (lista wykonanych transformacji). Zakres DOKŁADNIE wg
   roadmapy (7 punktów sekcji "Zakres transformacji"). Zasady:
   - wszystkie parsowania utwardzonym parserem z Etapu 15,
   - nie ruszaj dokumentów TREŚCI (tylko OPF + nowy nav.xhtml + ewentualnie NCX),
   - nav.xhtml buduj z modelu TOC wczytanego z NCX przez toc.reader; zapis przez
     toc.writer; wpis manifestu properties="nav",
   - guide→landmarks: mapa typów guide (cover, toc, text, ...) → epub:type
     (cover, toc, bodymatter); nieznane typy pomiń z notą w raporcie,
   - dcterms:modified w formacie CCYY-MM-DDThh:mm:ssZ (UTC, bez mikrosekund),
   - unique-identifier: jeśli atrybut nie wskazuje istniejącego id — napraw,
   - dc:date z opf:event: zostaw pierwszy publication/bez-eventu, usuń atrybut,
   - na EPUB 3 wejściowym → no-op (report.already_epub3 = True).
3. CLI: src/epubforge/cli/upgrade.py — `epubforge upgrade book.epub [--drop-ncx]
   [--dry-run] [-o OUT]`; --dry-run wypisuje plan (reuse Etapu 17); rejestracja
   w main.py.
4. GUI: przycisk "Uaktualnij do EPUB 3" (zdecyduj: Metadane czy Fixer; uzasadnij) —
   z potwierdzeniem i raportem w LogView.
5. tests/fixtures/make_sample_epub.py: dodaj generator wariantu EPUB 2
   (version="2.0", NCX, guide) → fixture sample_epub2.epub.
6. tests/test_upgrade.py: pełen zakres transformacji, no-op dla EPUB 3,
   --drop-ncx czyści manifest+spine@toc, idempotentność. Test integracyjny:
   po upgrade EpubCheck bez błędów (markery integration, skipif brak javy/jara).
7. pytest, ruff, mypy. Commit: "feat(converters): EPUB 2 to 3 upgrade (nav, landmarks, dcterms)"
8. Zaproponuj PR. Po merge zaproponuj tag v2.3.0 (gate: Etapy 22-23).
```

---

✅ zrobiony ## 🔤 Etap 24 — Subsetting fontów

```
Realizujemy Etap 24 z ROADMAP-epubforge-v3.md — "Subsetting fontów".
Przeczytaj sekcję Etapu 24 (pułapki!) i fixers/css_fixer.py (_font_files,
_FONT_MEDIA_TYPES — reuse wykrywania fontów).

Wykonaj:
1. main + pull, gałąź: feature/stage-24-font-subset
2. pyproject.toml: extra fonts = ["fonttools>=4.50", "brotli>=1.1"]; importy leniwe
   z czytelnym błędem "pip install epubforge[fonts]".
3. src/epubforge/fixers/fonts.py: FontSubsetOptions + subset_fonts(epub, options)
   -> FontReport:
   - zbiór znaków: WSZYSTKIE dokumenty spine (tekst przez utwardzony parser)
     + wartości content w CSS + STAŁY zestaw bezpieczeństwa: ASCII, polskie znaki,
     interpunkcja typograficzna „”«»—–…  ORAZ U+00AD i U+00A0 (efekty hyphenacji
     i typografii z Etapów 5/16 muszą się renderować!),
   - fonty z css_fixer._font_files (wydziel wspólny helper zamiast kopiować),
   - fonttools.subset z zachowaniem formatu (ttf→ttf, otf→otf, woff→woff, woff2→woff2),
   - @font-face z unicode-range → pomiń font z notą w raporcie (bezpieczniej),
   - zapis tylko gdy mniejszy; raport rozmiar przed/po per font,
   - brak brotli przy .woff2 → ostrzeżenie w raporcie, plik pominięty (nie wyjątek).
4. CLI: `epubforge fix --subset-fonts` (+ --dry-run pokazuje delty rozmiarów);
   krok subset_fonts w rejestrze receptur.
5. GUI: w sekcji fontów zakładki Fixer opcja "Przytnij fonty do użytych znaków"
   z ostrzeżeniem o licencjach (wzorzec ostrzeżenia soft-hyphen): "Niektóre
   licencje fontów zabraniają modyfikacji — sprawdź licencję fontu."
6. tests/test_fonts.py: font testowy zbuduj fontTools w fixture (kilka glifów);
   testy: cmap po subsetcie zawiera każdy codepoint z treści + zestaw bezpieczeństwa,
   format zachowany, większy-wynik → oryginał nietknięty, unicode-range pomijany.
   skipif przy braku fonttools.
7. pytest, ruff, mypy. Commit: "feat(fixers): font subsetting (fonttools)"
8. Zaproponuj PR.
```

---

✅ zrobiony ## ♿ Etap 25 — Ace (dostępność)

```
Realizujemy Etap 25 z ROADMAP-epubforge-v3.md — "Audyt dostępności (DAISY Ace)".
Przeczytaj sekcję Etapu 25 i validators/epubcheck.py — Ace integrujemy
DOKŁADNIE tym samym wzorcem (subprocess → temp dir → defensywny parser JSON).

Wykonaj:
1. main + pull, gałąź: feature/stage-25-a11y
2. core/detection.py: Tools.ace() (binarka "ace" w PATH; detect_version=True,
   `ace --version`); do detect_all i _NO_ARG_DETECTORS; pasek statusu narzędzi.
3. src/epubforge/validators/ace.py:
   - run_ace(epub_path, ace, *, timeout=600) -> AceReport: TemporaryDirectory,
     komenda [ace, "--outdir", tmp, str(epub)], raport z tmp/report.json,
   - parser DEFENSYWNY (każde pole .get, wzorzec parse_report z epubcheck.py):
     assertions → lista AceMessage(severity, rule, message, internal_path);
     mapowanie critical/serious→error, moderate→warning, minor→info,
   - błędy techniczne (brak raportu, timeout, zły JSON) → ValidationError
     z fragmentem stderr; "EPUB niedostępny" to NIE wyjątek.
4. CLI: src/epubforge/cli/a11y.py — `epubforge a11y book.epub [--json out.json]
   [--min-severity ...]` (wzorzec cli/check.py); rejestracja w main.py.
5. GUI zakładka Walidacja: przełącznik/drugi przycisk "Sprawdź dostępność (Ace)";
   wyniki w tej samej tabeli z klikalnymi wpisami (reuse skoku do pliku/linii,
   gdzie Ace podaje lokalizację); brak ace → przycisk wyszarzony z tooltipem
   instalacyjnym (npm install -g @daisy/ace).
6. tests/fixtures/ace/: report_ok.json, report_violations.json, report_broken.json
   (na podstawie realnego formatu Ace — sprawdź dokumentację
   https://daisy.github.io/ace/docs/report-json/). tests/test_ace.py: parsowanie
   wszystkich fixtures, mapowanie severity, błędy techniczne.
7. pybabel extract/update. pytest, ruff, mypy.
   Commit: "feat(validators): DAISY Ace accessibility audit"
8. Zaproponuj PR.
```

---

✅ zrobiony ## 🌐 Etap 26 — Metadane z ISBN i BN

```
Realizujemy Etap 26 z ROADMAP-epubforge-v3.md — "Metadane z ISBN i Biblioteki
Narodowej (opt-in)". Przeczytaj sekcję Etapu 26 — to PIERWSZY kod sieciowy
w projekcie; zasady bezpieczeństwa z audytu chodzkos-detection (D2) obowiązują
od pierwszej linii.

KROK 0 (OBOWIĄZKOWY, przed jakimkolwiek kodem): zbadaj dokumentację API BN
(https://data.bn.org.pl/docs) — aktualny endpoint wyszukiwania po ISBN, format
JSON odpowiedzi, pola z których wyciągniesz: tytuł, autorów, wydawcę, rok,
liczbę stron (MARC 300, tekst typu "320 s.") i deskryptory przedmiotowe.
WYPISZ mapowanie pól BN -> BookRecord i czekaj na moje potwierdzenie.

Po potwierdzeniu:
1. main + pull, gałąź: feature/stage-26-isbn
2. src/epubforge/bookmeta/ (stdlib urllib, ZERO nowych zależności; podpakiet
   bez importów z gui/ — kandydat do ekstrakcji jak gui-kit):
   - model.py: dataclass BookRecord (title, creators, publisher, date,
     description, language, isbn, page_count, subjects, series, source),
   - isbn.py: validate_isbn(text) -> str | None (normalizacja, sumy kontrolne
     ISBN-10/13),
   - providers/base.py: Protocol Provider.fetch_by_isbn(isbn, *, timeout=5),
   - providers/bn.py (wg KROKU 0), providers/openlibrary.py
     (https://openlibrary.org/isbn/{isbn}.json + /authors/...),
     providers/googlebooks.py (https://www.googleapis.com/books/v1/volumes?q=isbn:...),
   - chain.py: fetch_by_isbn — BN -> OL -> GB, scalanie per pole (puste pola
     dopełniane z kolejnych źródeł),
   - TWARDE zasady: tylko https, walidacja schematu URL, resp.read(1_000_000),
     każdy błąd → logger.debug + None (nigdy wyjątek do UI).
3. GUI zakładka Metadane: przycisk "Pobierz metadane…":
   - pole ISBN z prefill z obecnego identifiera (jeśli wygląda na ISBN),
   - pobranie w Worker (nie blokuj UI), status "Szukam…",
   - podgląd pól z CHECKBOXAMI per pole (domyślnie zaznaczone tylko puste
     pola formularza); deskryptory BN jako osobna lista checkboxów
     (domyślnie ODznaczone) → zapis do dc:subject,
   - liczba stron → <meta property="schema:numberOfPages"> w OPF (tylko
     EPUB 3; EPUB 2 → pomiń z notą w statusie),
   - offline/timeout/brak wyniku → status w dialogu, GUI żyje.
4. tests/test_bookmeta_providers.py: walidacja ISBN (10/13, złe sumy), mock
   urlopen (wzorzec _FakeResponse z chodzkos-detection): happy path BN
   (fixture JSON z realnej odpowiedzi z KROKU 0), fallback OL/GB, scalanie
   chain, odpowiedź > limitu odrzucona, http:// odrzucone, timeout → None.
   Jeden test integracyjny za markerem integration (skipif brak sieci).
5. pybabel extract/update. pytest, ruff, mypy.
   Commit: "feat(bookmeta): fetch metadata by ISBN (BN/OpenLibrary/GBooks, opt-in)"
6. Zaproponuj PR.
```

---

⏸️ odłożony ## 📦 Etap 27 — Dystrybucja

```
Realizujemy Etap 27 z ROADMAP-epubforge-v3.md — "Dystrybucja: PyPI, Linux/macOS,
winget". WARUNEK WSTĘPNY: REL-1 z Etapu 15 domknięty (zależność gui-kit z PyPI
albo świadoma decyzja o odroczeniu PyPI — w tym drugim wariancie pomiń punkt 1
i zaznacz to w PR).

Wykonaj:
1. PyPI:
   - .github/workflows/publish.yml: trigger na tag v* PO zielonym workflow Tests
     (workflow_run albo needs w jednym workflowie — uzasadnij wybór); build sdist+wheel
     (python -m build), publikacja przez pypa/gh-action-pypi-publish (pin do SHA)
     z trusted publishing (environment: pypi, permissions: id-token: write),
   - wypisz instrukcję jednorazowej konfiguracji publishera na pypi.org,
   - README: pip/pipx install po publikacji.
2. build.yml — macierz platform:
   - job build-linux (ubuntu-latest): PyInstaller onedir → tar.gz
     epubforge-linux-x86_64.tar.gz; przejrzyj build/epubforge-dir.spec pod kątem
     ścieżek Windows (icon.ico tylko dla win32; datas z separatorami przez os.path),
   - job build-macos (macos-latest): onedir → zip epubforge-macos.zip
     (bez podpisu; w README sekcja o Gatekeeper: xattr -dr com.apple.quarantine),
   - smoke test w KAŻDYM jobie: uruchom zbudowany plik z --version
     (linux: przed testem apt-get install libegl1 libxkbcommon0),
   - wszystkie artefakty do Release (rozszerz krok softprops).
3. winget: katalog build/winget/ z manifestami (version/installer/locale YAML)
   dla epubforge-setup.exe; installer URL wskazuje asset Release; wypisz
   instrukcję PR do microsoft/winget-pkgs (nie wysyłaj automatycznie).
4. README: tabela instalacji per platforma (Windows setup/portable/winget,
   Linux tar.gz, macOS zip, pipx).
5. Wszystkie nowe akcje przypięte do SHA (zasada z Etapu 15/SEC-3).
6. Commit: "build: multi-platform artifacts + PyPI publish workflow"
7. Zaproponuj PR. Po merge i wydaniu: zaproponuj tag v3.0.0 (gate: Etapy 24-27),
   aktualizację FEATURES.md, CHANGELOG i zrzutów ekranu w README.
```

---

✅ zrobiony ## 📖 Etap 28 — LubimyCzytac + dopasowanie

```
Realizujemy Etap 28 z ROADMAP-epubforge-v3.md — "Provider LubimyCzytac +
dopasowanie bez ISBN". Przeczytaj sekcję Etapu 28 i src/epubforge/bookmeta/
(Etap 26). WAŻNE: scraper piszemy OD ZERA — nie portuj kodu z calibre-web ani
pluginów Calibre (GPL); wolno podejrzeć wyłącznie strukturę URL-i serwisu.

KROK 0 (OBOWIĄZKOWY): pobierz ręcznie 2-3 strony książek z lubimyczytac.pl
(zapisz jako tests/fixtures/lc/*.html) i zbadaj: czy strona książki zawiera
application/ld+json (schema.org Book)? Jak działa wyszukiwanie po ISBN i po
tytule? WYPISZ plan parsowania (JSON-LD first, HTML fallback per brakujące
pole) i czekaj na moje potwierdzenie.

Po potwierdzeniu:
1. main + pull, gałąź: feature/stage-28-lubimyczytac
2. bookmeta/providers/lubimyczytac.py: search_by_isbn + search_title_author
   -> list[Candidate]; parsowanie strony książki: opis, liczba stron,
   cykl/saga, kategorie (surowe stringi do subjects). Parsowanie: JSON-LD
   przez json ze stdlib; HTML przez html.parser — KAŻDE pole opcjonalne,
   brak/zmiana layoutu → None, nigdy wyjątek.
3. bookmeta/match.py: normalize() (diakrytyki przez unicodedata, lower,
   interpunkcja, odcięcie podtytułu po ":") + score difflib.SequenceMatcher;
   próg pewności (np. 0.85) w stałej modułu.
4. bookmeta/isbn.py: extract_isbn_from_epub(epub, max_docs=5) — regex po
   pierwszych dokumentach spine (strona redakcyjna).
5. bookmeta/cache.py: SQLite w katalogu configu (klucz provider+query,
   TTL 30 dni, wersjonowany schemat — lekcja z mediaforge); rate limiter
   (time.monotonic, min. 2 s między żądaniami LC, bez równoległości);
   User-Agent "EpubForge/x.y (+URL repo)".
6. chain.py: LC w łańcuchu po BN; tryb bez ISBN → lista kandydatów do GUI.
7. GUI: dialog wyboru kandydata (tytuł/autor/rok/score); poniżej progu —
   nic nie zapisuj bez wyboru użytkownika.
8. tests/test_lubimyczytac.py + test_match.py + test_cache.py: wyłącznie
   fixtures (bez sieci); zepsuty layout → None; cache hit → 0 wywołań
   urlopen; rate limiter na mocku czasu.
9. pybabel extract/update. pytest, ruff, mypy.
   Commit: "feat(bookmeta): LubimyCzytac provider + fuzzy title/author matching"
10. Zaproponuj PR.
```

---

✅ zrobiony ## 🏷️ Etap 29 — Taksonomia + tagi AI

```
Realizujemy Etap 29 z ROADMAP-epubforge-v3.md — "Taksonomia tagów + tagowanie
AI (opt-in)". Przeczytaj sekcję Etapu 29, bookmeta/ (Etapy 26/28) oraz
mechanizm receptur (wzorzec czytania TOML przez tomllib).

Wykonaj:
1. main + pull, gałąź: feature/stage-29-tags
2. src/epubforge/data/taxonomy_pl.toml: kategorie [gatunek] [epoka] [miejsce]
   [tematy] — tag kanoniczny PL + synonimy + mapowania deskryptorów BN
   i kategorii LC/GB. Startowy zestaw wg sekcji etapu; uzupełnij sensownie
   do ~30-40 tagów kanonicznych. Plik pakowany do wheela jak presets;
   plik użytkownika w katalogu configu ma precedens nad wbudowanym.
3. bookmeta/taxonomy.py: load_taxonomy() (tomllib), map_subjects(raw:
   list[str]) -> MappedTags (kanoniczne + niezmapowane jako propozycje),
   deduplikacja po synonimach, limit 10 z priorytetem
   gatunek → epoka/miejsce → tematy.
4. bookmeta/ai.py (stdlib urllib): klient POST {base_url}/chat/completions
   (format OpenAI, temperature 0):
   - presety: ollama (http://localhost:11434/v1, DOMYŚLNY), anthropic,
     openai, gemini, deepseek, glm — base_url i model edytowalne w configu;
     ZWERYFIKUJ aktualne URL-e zgodności z OpenAI dla chmur i wypisz je w PR,
   - klucz API wyłącznie ze zmiennej środowiskowej (w configu tylko jej
     nazwa; NIGDY plaintext w pliku konfiguracyjnym),
   - wyjątek od zasady https: http tylko dla loopback/RFC1918 (Ollama /
     LiteLLM w LAN); hosty publiczne wyłącznie https; limit odpowiedzi
     jak w D2,
   - suggest_tags(description, toc, taxonomy) -> TagSuggestion: prompt PO
     POLSKU; gatunek/epoka/miejsce/tematy TYLKO z listy zamkniętej (wklej
     listę do promptu), postacie/organizacje otwarte; odpowiedź jako JSON,
     walidacja przeciw taksonomii, 1 retry, tag spoza listy → odrzuć.
5. Kaskada (nowy moduł bookmeta/tagging.py): (1) map_subjects z providerów,
   (2) AI na opis+TOC gdy tagów < 3, (3) AI na próbce treści (pierwsze
   ~5 tys. słów ze spine) tylko gdy brak opisu. Polityki scalania:
   keep/append/replace (domyślnie append), deduplikacja z istniejącymi
   dc:subject.
6. GUI: sekcja "Tagi" w zakładce Metadane — przycisk "Zaproponuj tagi":
   lista propozycji z checkboxami i źródłem (BN/LC/AI); ustawienia AI
   w konfiguracji GUI (zdecyduj gdzie: dialog ustawień czy sekcja zakładki;
   uzasadnij); brak endpointu → czytelny komunikat z instrukcją, kaskada
   (1) działa bez AI.
7. tests/test_taxonomy.py + test_tagging.py + test_ai.py: mapowanie /
   synonimy / limit / priorytety / polityki; klient AI na mocku urlopen
   (poprawny JSON, śmieci → retry → odrzut, http do hosta publicznego →
   błąd); ZERO realnych wywołań sieciowych w testach.
8. pybabel extract/update. pytest, ruff, mypy.
   Commit: "feat(bookmeta): PL tag taxonomy + AI tagging (Ollama default)"
9. Zaproponuj PR.
```

---

✅ zrobiony ## 📦 Etap 30 — Enrich hurtowo + calibredb

```
Realizujemy Etap 30 z ROADMAP-epubforge-v3.md — "Wzbogacanie hurtowe +
calibredb". Przeczytaj sekcję Etapu 30, cli/_batch.py (Etap 17), workers
(Etap 19), core/detection.py i bookmeta/ (Etapy 26-29).

Wykonaj:
1. main + pull, gałąź: feature/stage-30-enrich-batch
2. cli/enrich.py: `epubforge enrich <pliki/katalog> [--fields tytuł,opis,...]
   [--tags] [--policy fill|append|overwrite] [--dry-run] [--report out.csv]`
   — batch przez mechanizm Etapu 17; postęp/anulowanie z Etapu 19;
   --dry-run pokazuje pełny plan per książka, 0 zapisów. Rejestracja
   w main.py.
3. Raport CSV/JSON: per książka — dopasowanie (isbn/fuzzy/brak), źródło,
   pola zmienione/pominięte, błąd; podsumowanie
   (znalezione/nieznalezione/z cache).
4. core/detection.py: Tools.calibredb() (obok istniejącej detekcji Calibre);
   do detect_all i paska statusu narzędzi.
5. Tryb --calibre-library PATH:
   - preflight: calibredb list --for-machine --limit 1 → blokada bazy
     (otwarte GUI Calibre) → czytelny komunikat i STOP,
   - odczyt (id, title, authors, isbn, tags) → wzbogacenie przez bookmeta →
     zapis calibredb set_metadata; NIGDY nie dotykaj plików biblioteki
     bezpośrednio na dysku,
   - domyślne polityki w hurcie: fill dla pól, append dla tagów.
6. Rate limiting współdzielony (jedna instancja limitera na proces) —
   hurt nie omija odstępów między żądaniami LC.
7. tests/test_enrich.py: batch na fixtures z mockiem chain (bez sieci),
   polityki, dry-run bez zapisów, format raportu; calibredb na mocku
   subprocess (wzorzec test_converter.py): budowa komend, blokada → STOP.
8. pybabel extract/update. pytest, ruff, mypy.
   Commit: "feat(cli): bulk metadata enrichment + calibredb integration"
9. Zaproponuj PR. Po merge zaproponuj tag v3.1.0 (gate: Etapy 28-30;
   README/CHANGELOG/FEATURES.md, zrzuty ekranu).
```

---

## 🚦 Zasady wspólne (przypomnienie dla wszystkich promptów)

1. Etap 15 blokuje wszystkie pozostałe; wewnątrz wydań kolejność etapów 20/21/24/25/26 dowolna.
2. Każdy nowy string użytkownika przez `_()`/`ngettext` + aktualizacja katalogów `pybabel` (pl/en/de).
3. Nowe parsowanie XML **wyłącznie** utwardzonym parserem (Etap 15/SEC‑1).
4. Fixery piszą do bufora `Epub`, `save()` należy do wołającego; eksporty nie mutują wejścia (COR‑1).
5. Długie operacje w GUI zawsze przez `Worker`; od Etapu 19 — z obsługą anulowania.
6. DoD z `ROADMAP.md` bez zmian: mypy strict (3 platformy), pytest, ruff, coverage ≥ 70% nowego modułu, conventional commit, PR squash + delete branch.
