# 🗺️ EpubForge — Roadmap

Plan rozwoju projektu krok po kroku. **Każdy etap = osobna gałąź feature**. Po zakończeniu i przejściu testów — merge do `main`.

---

## Konwencja gałęzi

| Typ | Wzór nazwy | Przykład |
|---|---|---|
| Funkcja | `feature/stage-N-nazwa` | `feature/stage-1-core-epub` |
| Naprawa | `fix/opis` | `fix/metadata-encoding` |
| Refactor | `refactor/co` | `refactor/extract-widgets` |
| Dokumentacja | `docs/co` | `docs/api-reference` |

Po zmergowaniu PR — gałąź zostaje usunięta automatycznie (`gh pr merge --delete-branch`).

---

## 🎯 Etap 0 — Fundament (Foundation)

**Gałąź:** `feature/stage-0-foundation`
**Czas:** ~30 min
**Cel:** Działająca struktura projektu, CI/CD, pierwszy zielony build.

### Pliki do utworzenia/sprawdzenia
- ✅ `pyproject.toml` (zależności, metadane)
- ✅ `LICENSE` (MIT)
- ✅ `.gitignore`
- ✅ `README.md`
- ✅ `CLAUDE.md`
- ✅ `.github/workflows/test.yml` — testy + linting
- ✅ Struktura katalogów `src/epubforge/...` z `__init__.py`
- ✅ Pierwszy test sanity-check

### Kryteria akceptacji
- [ ] `pip install -e ".[dev]"` przechodzi bez błędów
- [ ] `pytest` pokazuje min. 1 zielony test
- [ ] `ruff check .` zero błędów
- [ ] GitHub Actions: zielona dioda przy CI

### Merge command
```bash
gh pr create --title "Stage 0: Project foundation" --body "Sets up project structure, CI/CD pipeline, and tooling."
gh pr merge --squash --delete-branch
```

---

## 📦 Etap 1 — Core: klasa Epub

**Gałąź:** `feature/stage-1-core-epub`
**Czas:** ~2 godziny
**Cel:** Klasa `Epub` do otwierania, edycji i zapisu plików EPUB.

### Co powstanie
- `src/epubforge/core/epub.py` — klasa `Epub`
- `src/epubforge/core/exceptions.py` — własne wyjątki
- `tests/test_epub.py` — testy + fixture z prawdziwym EPUB

### API klasy `Epub`
```python
class Epub:
    def __init__(self, path: Path) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> "Epub": ...
    def __exit__(self, *args) -> None: ...

    @property
    def opf_path(self) -> str: ...  # odczytany z META-INF/container.xml
    @property
    def manifest(self) -> list[ManifestItem]: ...
    @property
    def spine(self) -> list[str]: ...

    def read_file(self, internal_path: str) -> bytes: ...
    def write_file(self, internal_path: str, data: bytes) -> None: ...
    def list_files(self) -> list[str]: ...
    def save(self, output_path: Path | None = None) -> Path: ...
    def backup(self) -> Path: ...
```

### ⚠️ KRYTYCZNE: zasady bezpiecznego zapisu EPUB (ZIP)

EPUB to archiwum ZIP z **rygorystycznymi wymogami strukturalnymi**. Naiwne `zipfile.write()` w pętli tworzy plik, który EpubCheck i część czytników odrzuca. Klasa `Epub.save()` MUSI:

1. **Plik `mimetype` jest PIERWSZY w archiwum** — przed czymkolwiek innym
2. **Plik `mimetype` zapisany BEZ kompresji** — `ZIP_STORED`, NIE `ZIP_DEFLATED`
3. **Plik `mimetype` bez extra fields** — czysty zapis, zawartość dokładnie `application/epub+zip` (bez końcowego newline)
4. **Pozostałe pliki** mogą być kompresowane (`ZIP_DEFLATED`)
5. **Zapis atomowy** — najpierw do pliku tymczasowego (`.tmp`), potem `os.replace()`
6. **Backup przed nadpisaniem** oryginału (`.bak`)

Wzorzec zapisu — **kopiuj niezmienione wpisy bezpośrednio ze źródłowego ZIP** (nie ładuj całości do pamięci, ważne dla dużych EPUB-ów z grafiką):
```python
import zipfile, os
from pathlib import Path


def _write_epub(source: Path, target: Path, modified: dict[str, bytes]) -> None:
    """Zapis z kopiowaniem strumieniowym ze źródła.

    Args:
        source: oryginalny EPUB (do skopiowania niezmienionych plików)
        target: plik docelowy
        modified: tylko ZMIENIONE pliki {ścieżka: dane}
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(tmp, "w") as zout:
        # 1. mimetype PIERWSZY, BEZ kompresji
        zout.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        # 2. reszta: zmienione z dict, niezmienione kopiowane ze źródła
        for item in zin.infolist():
            if item.filename == "mimetype":
                continue
            data = modified.get(item.filename)
            if data is None:
                data = zin.read(item.filename)  # kopiuj oryginał
            zout.writestr(item.filename, data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, target)  # atomic
```
Dzięki temu w pamięci trzymamy tylko zmodyfikowane pliki, nie cały EPUB — przy 100 MB książce z grafiką to różnica między 5 MB a 100 MB RAM.

### ⚠️ Odczyt ścieżki OPF — przez container.xml

Ścieżki do pliku OPF NIE wolno zgadywać. Trzeba ją odczytać z `META-INF/container.xml`:
```python
# META-INF/container.xml zawiera:
# <rootfiles><rootfile full-path="OEBPS/content.opf" .../></rootfiles>
# Najpierw parsujemy container.xml, dopiero potem znamy opf_path
```

### Kryteria akceptacji
- [ ] Otwarcie EPUB → odczyt `opf_path` z container.xml → manifest i spine
- [ ] Modyfikacja pliku wewnętrznego → zapis zachowuje strukturę ZIP
- [ ] **`mimetype` pierwszy i nieskompresowany w wyjściowym EPUB** (test sprawdza `ZipInfo.compress_type == ZIP_STORED`)
- [ ] Zapisany EPUB przechodzi walidację EpubCheck (jeśli dostępny — test integracyjny)
- [ ] `backup()` tworzy `.bak` przed zapisem
- [ ] Zapis atomowy (plik tymczasowy + replace)
- [ ] **Niezmienione pliki kopiowane ze źródła** (nie ładowane wszystkie do RAM)
- [ ] Coverage > 80% dla `epub.py`

---

## 🏷️ Etap 2 — Core: Metadane Dublin Core

**Gałąź:** `feature/stage-2-metadata`
**Czas:** ~1.5 godziny
**Cel:** Odczyt i zapis metadanych EPUB (Dublin Core).

### Co powstanie
- `src/epubforge/core/metadata.py` — klasa `Metadata`
- Rozszerzenie `Epub` o `.metadata` (property)
- `tests/test_metadata.py`

### API klasy `Metadata`
```python
@dataclass
class Metadata:
    title: str = ""
    creators: list[str] = field(default_factory=list)
    language: str = "en"
    identifier: str = ""  # ISBN/UUID
    publisher: str = ""
    date: str = ""  # ISO 8601
    description: str = ""
    subjects: list[str] = field(default_factory=list)

    @classmethod
    def from_opf(cls, opf_xml: bytes) -> "Metadata": ...
    def to_opf(self, existing_opf: bytes) -> bytes: ...
```

### ⚠️ Pułapka: namespace'y w OPF

OPF używa przestrzeni nazw XML. Metadane są w namespace Dublin Core, elementy struktury w namespace OPF. Parsowanie BEZ obsługi namespace'ów zwróci puste wyniki. Trzeba użyć namespace map:
```python
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf",
}
# lxml: root.findall(".//dc:creator", namespaces=NS)
# xml.etree: root.findall(".//{http://purl.org/dc/elements/1.1/}creator")
```
Zachowaj deklarację XML i kodowanie UTF-8 przy zapisie (polskie znaki!).

### Kryteria akceptacji
- [ ] Odczyt metadanych z fixture EPUB
- [ ] Edycja + zapis nie psuje innych elementów OPF
- [ ] Obsługa wielu autorów (`<dc:creator>` × N)
- [ ] Poprawna obsługa namespace'ów (dc:, opf:)
- [ ] Polskie znaki (`ąęłżźć`) — odczyt i zapis poprawny
- [ ] Deklaracja `<?xml ... encoding="utf-8"?>` zachowana po zapisie

### Stage gate (po tym etapie)
✋ **Tag:** `git tag v0.1.0-alpha` — pierwsza biblioteka działa.

---

## 🔍 Etap 3 — Core: Wykrywanie narzędzi

**Gałąź:** `feature/stage-3-detection`
**Czas:** ~1 godzina
**Cel:** Funkcje do auto-detekcji Pandoc, Calibre, Sigil, KP3, wtyczki KFX.

### Co powstanie
- `src/epubforge/core/detection.py` — `Tools` namespace
- `src/epubforge/core/config.py` — wczytywanie/zapis `config.json`
- `tests/test_detection.py` (z mockami)

### API
```python
@dataclass(frozen=True)
class Tool:
    name: str
    path: Path | None
    version: str = ""
    available: bool = False


class Tools:
    @staticmethod
    def pandoc() -> Tool: ...
    @staticmethod
    def calibre_ebook_convert() -> Tool: ...
    @staticmethod
    def calibre_viewer() -> Tool: ...
    @staticmethod
    def sigil() -> Tool: ...
    @staticmethod
    def kindle_previewer() -> Tool: ...
    @staticmethod
    def calibre_kfx_plugin() -> bool: ...
    @staticmethod
    def detect_all() -> dict[str, Tool]: ...
```

### Kryteria akceptacji
- [ ] Testy z mockowanymi ścieżkami (Windows i Linux)
- [ ] Cache wyników detekcji w `config.json`
- [ ] Możliwość ręcznego override'u ścieżki

---

## 🔄 Etap 4 — Konwerter → EPUB

**Gałąź:** `feature/stage-4-converter`
**Czas:** ~2 godziny
**Cel:** Konwersja TXT/DOCX/HTML/MD/ODT/RTF → EPUB.

### Co powstanie
- `src/epubforge/converters/to_epub.py`
- `src/epubforge/converters/__init__.py`
- `tests/test_converter.py`

### API
```python
@dataclass
class ConvertOptions:
    epub_version: Literal["epub2", "epub3"] = "epub3"
    metadata: Metadata | None = None
    cover_image: Path | None = None
    toc: bool = True
    toc_depth: int = 3
    css: Path | None = None


def to_epub(
    source: Path,
    target: Path,
    options: ConvertOptions = ConvertOptions(),
    engine: Literal["pandoc", "calibre", "auto"] = "auto",
) -> ConversionResult: ...
```

### Obsługiwane formaty wejściowe
- `.txt`, `.md`, `.markdown` — Pandoc
- `.docx`, `.odt`, `.rtf` — Pandoc
- `.html`, `.htm` — Pandoc
- `.pdf` → Calibre (fallback, bo Pandoc nie obsługuje PDF)
- `.fb2`, `.lit`, `.mobi` → Calibre

### Kryteria akceptacji
- [ ] Każdy format wejściowy w fixture → poprawny EPUB
- [ ] Metadane są zapisane w wyjściowym EPUB
- [ ] Okładka dodawana poprawnie

---

## ✂️ Etap 5 — Dzielenie wyrazów (Hyphenation)

**Gałąź:** `feature/stage-5-hyphenation`
**Czas:** ~1.5 godziny
**Cel:** Wstawianie soft-hyphens (`\u00ad`) w tekście EPUB.

### Co powstanie
- `src/epubforge/fixers/hyphenator.py`
- `src/epubforge/fixers/__init__.py`
- `tests/test_hyphenator.py`

### API
```python
@dataclass
class HyphenationOptions:
    language: str = "pl"  # ISO 639-1
    method: Literal["soft-hyphen", "css"] = "soft-hyphen"
    skip_headers: bool = True  # h1-h3
    skip_tags: set[str] = field(default_factory=lambda: {"code", "pre", "kbd"})
    min_word_length: int = 5


def hyphenate(epub: Epub, options: HyphenationOptions) -> None: ...
```

### ⚠️ WAŻNE: kompromis metod dzielenia wyrazów

Dwie metody, każda z wadami — **pozwól użytkownikowi wybrać, nie wybieraj za niego**:

| Metoda | Działa wszędzie | Wada |
|---|---|---|
| `soft-hyphen` (wstawia `\u00ad`) | tak, też stary Kindle/MOBI/KFX | **psuje słownik i wyszukiwarkę na czytniku** — zaznaczone słowo z ukrytym myślnikiem nie zostanie znalezione w słowniku |
| `css` (`hyphens: auto`) | nie — słabo wspierane na Kindle | czysty tekst, ale brak efektu na wielu czytnikach e-ink |

**Implementacja `soft-hyphen`:** wstawia `\u00ad` w słowach (jak dotychczas).
**Implementacja `css`:** wstrzykuje globalną regułę do CSS:
```css
body { hyphens: auto; -webkit-hyphens: auto; -moz-hyphens: auto; hyphenate-limit-chars: 5 2 2; }
```

GUI MUSI pokazać ostrzeżenie przy wyborze `soft-hyphen`: *„Ta metoda działa na wszystkich czytnikach, ale może utrudnić wyszukiwanie słów i działanie słownika na urządzeniu."*

### Biblioteka
- `pyphen` — słowniki dla 50+ języków, w tym polski (tylko dla metody soft-hyphen)

### Kryteria akceptacji
- [ ] Metoda soft-hyphen: polski tekst hyphenowany poprawnie
- [ ] Metoda css: reguła wstrzyknięta, tekst nietknięty
- [ ] Tagi `<code>`, `<pre>` pomijane (soft-hyphen)
- [ ] Nagłówki opcjonalnie pomijane
- [ ] Idempotentność — drugi przebieg nie podwaja hyphenów
- [ ] Ostrzeżenie dostępne w API (np. `HyphenationOptions` ma docstring z przestrogą)

---

## 🎨 Etap 6 — CSS Fixer

**Gałąź:** `feature/stage-6-css-fixer`
**Czas:** ~2 godziny
**Cel:** Czyszczenie i normalizacja CSS w plikach EPUB.

### Co powstanie
- `src/epubforge/fixers/css_fixer.py`
- `tests/test_css_fixer.py`

### API
```python
@dataclass
class CssFixOptions:
    remove_colors: bool = False
    remove_fonts: bool = False
    inject_reset: bool = True
    replace_justify: Literal["keep", "left"] = "keep"
    inject_book_margin_px: int | None = None
    skip_hyphenation_headers: bool = True


def fix_css(epub: Epub, options: CssFixOptions) -> None: ...
```

### Funkcje
1. **Remove colors** — usuwa `color:`, `background:`, `background-color:`
2. **Remove fonts** — usuwa `@font-face`, `font-family:`, fizycznie usuwa pliki fontów
3. **Inject reset** — dodaje minimalny reset CSS (`margin: 0; padding: 0;`)
4. **Replace justify** — `text-align: justify` → `text-align: left`
5. **Book margin** — `@page { margin: Npx }`
6. **Skip hyphenation in headers** — `h1, h2, h3 { hyphens: none; }`

### Biblioteka
- `tinycss2` — nowoczesny, lekki parser CSS oparty o specyfikacje W3C. **Nie używamy cssutils** — jest przestarzały, hałasuje przy CSS3 (`--var`, `@supports`, `calc()`) i bywa nadgorliwy przy modyfikacjach.
- Dla prostych operacji (usuń kolory, justify→left) tinycss2 lub precyzyjny regex są bezpieczniejsze niż cssutils.

### ⚠️ Uwaga implementacyjna
`tinycss2` to tokenizer/parser niskiego poziomu (nie obiektowy model jak cssutils). Operujesz na liście tokenów:
```python
import tinycss2

rules = tinycss2.parse_stylesheet(css_text, skip_whitespace=True)
# Modyfikuj/filtruj tokeny, potem serialize:
new_css = tinycss2.serialize(rules)
```
Zachowuj nieznane reguły (`@supports`, `calc()`, zmienne) bez zmian — modyfikuj tylko to, co jawnie celujesz.

### Kryteria akceptacji
- [ ] Każda opcja działa niezależnie
- [ ] Kombinacja opcji działa (np. remove-colors + replace-justify)
- [ ] **Nowoczesny CSS3 (`--var`, `@supports`, `calc()`) NIE jest uszkadzany**
- [ ] CSS pozostaje parsowalny po zmianach

---

## 🏷️ Stage gate v0.5.0

**Tag:** `git tag v0.5.0`
**Co działa:** Biblioteka + CLI (`epubforge fix`, `epubforge convert`, `epubforge meta`).
**Co nie działa:** GUI, KFX.

---

## 📚 Etap 7 — Konwerter EPUB → KFX

**Gałąź:** `feature/stage-7-kfx`
**Czas:** ~2 godziny
**Cel:** Konwersja EPUB → KFX z dwoma silnikami.

### Co powstanie
- `src/epubforge/converters/to_kfx.py`
- `tests/test_kfx.py` (z mockami subprocess)

### API
```python
@dataclass
class KfxOptions:
    engine: Literal["calibre", "kindle-previewer", "auto"] = "calibre"  # Calibre = główny
    fix_epub_first: bool = True  # uruchom CSS fixer przed konwersją


def to_kfx(
    source: Path, target_dir: Path, options: KfxOptions = KfxOptions()
) -> ConversionResult: ...
```

### Decyzje
- **Główny silnik:** Calibre + wtyczka KFX Output (sprawdzony, mniej wrażliwy na formatowanie)
- **Zapasowy:** Kindle Previewer 3 (oznaczone jako *experimental* w GUI)
- KP3 tworzy własny podkatalog wyjściowy → użyj `rglob("*.kfx")` i przenieś plik

### Kryteria akceptacji
- [ ] Calibre + wtyczka KFX wykryte przy starcie
- [ ] Detekcja KP3 (Windows: `%LOCALAPPDATA%\Amazon\Kindle Previewer 3`)
- [ ] Plik `.kfx` powstaje w wybranym katalogu

---

## 🖥️ Etap 8 — GUI: Framework i widgety

**Gałąź:** `feature/stage-8-gui-framework`
**Czas:** ~3 godziny
**Cel:** Główna klasa App, system motywów, podstawowe widgety.

### Co powstanie
- `src/epubforge/gui/app.py` — klasa `App(tk.Tk)`
- `src/epubforge/gui/theme.py` — motyw jasny/ciemny
- `src/epubforge/gui/widgets/path_entry.py`
- `src/epubforge/gui/widgets/file_list.py`
- `src/epubforge/gui/widgets/toggle.py`
- `src/epubforge/gui/widgets/section.py`
- `src/epubforge/gui/widgets/tooltip.py`
- `src/epubforge/gui/streaming.py` — log streamer
- `tests/gui/test_widgets.py` (xvfb-run)

### Kryteria akceptacji
- [ ] Okno otwiera się z jedną zakładką (placeholder)
- [ ] Przełącznik motywu jasny/ciemny działa
- [ ] Pasek statusu pokazuje wykryte narzędzia
- [ ] Wszystkie widgety mają tooltipy

### Kod do skopiowania ze starego projektu
Zobacz `REUSABLE_CODE.md` sekcja **Widgets** — gotowe klasy do skopiowania.

---

## 📑 Etap 9 — GUI: Zakładka Metadane

**Gałąź:** `feature/stage-9-gui-metadata`
**Czas:** ~2 godziny
**Cel:** Zakładka do podglądu i edycji metadanych Dublin Core.

### Co powstanie
- `src/epubforge/gui/tabs/metadata.py`
- Integracja z `core.metadata`
- Lista plików EPUB z odświeżaniem
- Przyciski: **Sigil**, **Calibre Editor**, **Calibre Viewer**

### Kryteria akceptacji
- [ ] Wybór pliku z listy → pola wypełniają się metadanymi
- [ ] Edycja + zapis → backup `.bak` automatyczny
- [ ] Drag & drop (jeśli `tkinterdnd2` dostępne)

---

## 🔄 Etap 10 — GUI: Zakładka Konwerter

**Gałąź:** `feature/stage-10-gui-converter`
**Czas:** ~1.5 godziny

- Lista plików wejściowych
- Wybór silnika (Pandoc/Calibre/auto)
- Pola metadanych
- Wybór okładki
- **PDF za jawnym potwierdzeniem**: gdy użytkownik doda plik `.pdf`, pokaż ostrzeżenie w dialogu: *„Konwersja PDF → EPUB jest eksperymentalna. Calibre wstawia sztywne marginesy i może łamać akapity. Najlepsze wyniki dla prostych PDF tekstowych. Kontynuować?"* — dopiero po potwierdzeniu plik trafia na listę.

---

## ✂️ Etap 11 — GUI: Zakładka Fixer

**Gałąź:** `feature/stage-11-gui-fixer`
**Czas:** ~1.5 godziny

- Hyphenacja (język z dropdown)
- CSS fixer (wszystkie opcje jako checkboxy)
- Podgląd wynikowego pliku w Calibre viewer

---

## 📚 Etap 12 — GUI: Zakładka KFX

**Gałąź:** `feature/stage-12-gui-kfx`
**Czas:** ~1 godzina

- Wybór silnika (Calibre — domyślnie, KP3 — experimental z ostrzeżeniem)
- Checkbox „Napraw EPUB przed konwersją"
- Pasek postępu dla wielu plików

---

## 🏗️ Etap 13 — Build pipeline

**Gałąź:** `feature/stage-13-build`
**Czas:** ~1 godzina
**Cel:** PyInstaller `.spec` (portable + onedir), ikona, instalator Inno Setup, GitHub Actions Release.

### Co powstanie
- `build/epubforge-portable.spec` — PyInstaller `--onefile` (jeden `epubforge.exe`)
- `build/epubforge-dir.spec` — PyInstaller `--onedir` (folder pod instalator)
- `build/installer.iss` — skrypt Inno Setup (instalator z menu Start, „Dodaj/usuń programy")
- `build/create_icon.py` — generator placeholderowej `icon.ico` (Pillow)
- `build/build.bat` — lokalny build obu wariantów + instalatora (Windows)
- `.github/workflows/build.yml` — Release przy tagu `v*` z OBOMA plikami
- `src/epubforge/gui/assets/` — miejsce na dostarczane później `logo.png` / `icon.ico`

### Dwa warianty dystrybucji
- **Portable** — `epubforge.exe`, jeden plik, bez instalacji.
- **Instalator** — `epubforge-setup.exe` (Inno Setup): skrót w menu Start, opcjonalnie na
  pulpicie, wpis w „Dodaj/usuń programy", licencja MIT, katalog `{autopf}\EpubForge`.

### Assety (dostarczane później)
Kod ładuje `logo.png` (zakładka About, przez `sys._MEIPASS` w bundlu) i `icon.ico`
(spec/instalator), jeśli istnieją. Gdy `icon.ico` brak — `create_icon.py` generuje
placeholder. Podmiana plików w `assets/` nie wymaga zmian w kodzie ani spec-ach.

### Pułapki techniczne (z poprzedniego projektu!)
**DLL conflict** — `python311.dll` z PyInstaller vs Python użytkownika. Rozwiązanie: izoluj pliki w podkatalogu, ustaw `sys.path[0]` tak, by NIE wskazywał na `_MEIPASS` przy wywołaniach subprocess.

**tkinterdnd2 + PyInstaller** — `tkinterdnd2` dołącza natywne binaria `tkdnd`, których PyInstaller domyślnie NIE pakuje → `.exe` wywala się z `can't find package tkdnd`. Rozwiązanie w `.spec`:
```python
import tkinterdnd2, os

tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
datas += [(tkdnd_dir, "tkinterdnd2/tkdnd")]
# Alternatywnie: pyinstaller --collect-all tkinterdnd2
```

### Kryteria akceptacji
- [ ] Lokalny `build.bat` produkuje `epubforge.exe` (portable) i `epubforge-setup.exe` (instalator)
- [ ] `.exe` otwiera się i działają wszystkie zakładki
- [ ] **Drag & drop działa w `.exe`** (test: przeciągnij plik na okno)
- [ ] Instalator tworzy skrót w menu Start i wpis w „Dodaj/usuń programy"
- [ ] GitHub Actions przy tagu `v*` dołącza do Release oba pliki

---

## 📖 Etap 14 — Dokumentacja i Release v1.0

**Gałąź:** `feature/stage-14-docs`
**Czas:** ~2 godziny

- Screenshots w README
- `docs/user-guide.md`
- `docs/api-reference.md` (autogenerowane przez `pdoc`)
- CHANGELOG.md
- `git tag v1.0.0` + GitHub Release

---

## 📊 Podsumowanie czasowe

| Etap | Czas | Skumulowany |
|---|---|---|
| 0. Foundation | 30 min | 30 min |
| 1. Core Epub | 2 h | 2.5 h |
| 2. Metadata | 1.5 h | 4 h |
| 3. Detection | 1 h | 5 h |
| 4. Converter | 2 h | 7 h |
| 5. Hyphenation | 1.5 h | 8.5 h |
| 6. CSS Fixer | 2 h | 10.5 h |
| 7. KFX | 2 h | 12.5 h |
| 8. GUI Framework | 3 h | 15.5 h |
| 9-12. GUI Tabs | 6 h | 21.5 h |
| 13. Build | 1 h | 22.5 h |
| 14. Docs | 2 h | 24.5 h |

**~25 godzin** rozłożone na 14 etapów. Realistycznie: **3-5 tygodni** pracy popołudniami.

---

## 🎯 Definicja zakończonego etapu (DoD)

Każdy etap kończy się **dopiero** gdy:

1. ✅ Kod skompilowany bez błędów (`mypy strict`)
2. ✅ Wszystkie testy zielone (`pytest`)
3. ✅ Lint czysty (`ruff check`)
4. ✅ Coverage testów min. 70% dla nowego modułu
5. ✅ Dokumentacja (docstring) na publicznych funkcjach
6. ✅ Conventional commit (`feat:`, `fix:`, ...)
7. ✅ PR zatwierdzony i zmergowany
8. ✅ Lokalna gałąź usunięta

---

## 🚦 Gdy coś idzie nie tak

**Etap się rozrasta?**
- Podziel na pod-etapy `feature/stage-N-część-A` i `feature/stage-N-część-B`

**Wykryto błąd po merge?**
- Nowa gałąź `fix/opis-błędu` z `main`

**Refactoring potrzebny?**
- Osobna gałąź `refactor/co` — NIE łącz z nowymi funkcjami

---

🚀 **Następny krok**: otwórz `PROMPTS.md` i wklej prompt dla **Etapu 0** do Claude Code.
