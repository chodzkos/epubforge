# CLAUDE.md

Ten plik daje Claude Code wskazówki do pracy nad projektem. **Czytaj go na początku każdej sesji.**

---

## Projekt

**EpubForge** — modułowa biblioteka i aplikacja Python (GUI + CLI) do pracy z plikami EPUB. Cross-platform, licencja MIT.

Repo: `github.com/chodzkos/epubforge`  
Branch główny: `main`  
Licencja: MIT

### Cele projektu
1. **Klarowny modułowy kod** — żadnych plików > 500 linii
2. **Pełne pokrycie testami** — >70% coverage dla każdego modułu core
3. **Type safety** — `mypy --strict` przechodzi czysto
4. **Cross-platform** — działa na Windows, Linux, macOS
5. **API + CLI + GUI** — biblioteka jako fundament, narzędzia użytkowe na wierzchu

---

## Zasady (NIENEGOCJOWALNE)

### Git workflow
- **Conventional commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `style:`, `perf:`
- **Każdy etap z ROADMAP.md = osobna gałąź feature** (`feature/stage-N-nazwa`)
- **Squash merge** do `main` (czysta historia)
- **NIGDY** nie pushuj na `main` bezpośrednio
- **NIGDY** nie pushuj bez wyraźnej zgody użytkownika — zaproponuj komendę
- Po merge: usuwaj lokalną i zdalną gałąź

### Kod
- **Komentarze i docstrings — po polsku**
- **Nazwy zmiennych, funkcji, klas — po angielsku** (snake_case / PascalCase)
- **Type hints — wymagane** w publicznych API
- **Dataclasses** zamiast słowników gdzie tylko możliwe
- **f-strings** zamiast `.format()` lub `%`
- **`pathlib.Path`** zamiast `os.path`
- **`logging`** zamiast `print` (w bibliotece; CLI może używać prints)

### Testy
- **pytest** — wszystkie nowe funkcje muszą mieć testy
- **Coverage min. 70%** dla nowego kodu
- **Fixtures w `tests/fixtures/`** — prawdziwe pliki EPUB do testowania
- **Mocki dla subprocess** — nie wywołujemy Pandoc/Calibre w CI
- **xvfb-run dla testów GUI** w Linux CI

### Dokumentacja
- **Docstring w stylu Google** dla każdej publicznej funkcji/klasy
- **Type hints liczone jako dokumentacja** (nie powielaj w docstringu)
- **README aktualizowany przy każdej istotnej zmianie funkcji**

---

## Stack technologiczny

| Element | Wybór | Wersja |
|---|---|---|
| Python | 3.10+ | match statements, type hints |
| GUI | tkinter | wbudowany w Pythona |
| XML/HTML | lxml | szybki, robust |
| CSS | tinycss2 | nowoczesny parser (NIE cssutils) |
| Hyphenation | pyphen | 50+ języków |
| Drag&Drop | tkinterdnd2 | opcjonalne |
| Obrazy | Pillow | dla ikon |
| Packaging | hatchling + pyproject.toml | nowoczesny |
| Test | pytest + pytest-cov | standard |
| Lint | ruff | szybki, all-in-one |
| Type check | mypy --strict | strict mode |
| Build | PyInstaller | tylko Windows .exe |
| CI/CD | GitHub Actions | tests + build |
| Logger | stdlib logging | structured |

---

## Build

### Lokalny build Windows
```bat
build\build.bat
```

Skrypt:
1. wybiera Pythona 3.10+ (`py -3.12`, `py -3.11`, `py -3.10`, a dopiero potem
   `python`),
2. instaluje projekt z dodatkami `build,gui`, żeby PyInstaller widział m.in.
   `darkdetect`, `tkinterdnd2` i Pillow,
3. sprawdza środowisko przez `build/check_build_env.py`,
4. buduje `build\dist\epubforge.exe` (portable),
5. buduje `build\dist\epubforge\` (onedir pod instalator),
6. jeśli znajdzie `ISCC.exe`, tworzy `build\dist\epubforge-setup.exe`.

Jeśli domyślne `python` wskazuje na 3.9 albo starsze, build nadal powinien działać
przez Python Launcher. Gdy `py -3.10 --version` też nie działa, trzeba
zainstalować nowszego Pythona.

Brak `epubforge-setup.exe` zwykle oznacza brak Inno Setup albo brak `ISCC.exe`
w `PATH` / standardowym katalogu `Program Files`.

---

## Architektura

### Struktura modułowa
```
src/epubforge/
├── __init__.py             ← __version__, public API exports
├── __main__.py             ← entry point (python -m epubforge)
├── core/                   ← biblioteka core (no GUI deps!)
│   ├── epub.py             ← klasa Epub (read/write ZIP + OPF)
│   ├── metadata.py         ← Dublin Core
│   ├── detection.py        ← wykrywanie narzędzi zewnętrznych
│   ├── config.py           ← config.json persistence
│   └── exceptions.py       ← własne wyjątki
├── converters/
│   ├── to_epub.py          ← *.* → EPUB
│   └── to_kfx.py           ← EPUB → KFX
├── fixers/
│   ├── hyphenator.py       ← dzielenie wyrazów
│   └── css_fixer.py        ← naprawa CSS
├── cli/                    ← linia poleceń
│   ├── main.py             ← argparse setup
│   ├── convert.py          ← subkomenda convert
│   ├── fix.py              ← subkomenda fix
│   ├── meta.py             ← subkomenda meta
│   └── kfx.py              ← subkomenda kfx
└── gui/                    ← interfejs graficzny
    ├── app.py              ← App(tk.Tk)
    ├── theme.py            ← motyw jasny/ciemny
    ├── streaming.py        ← log streamer (thread-safe)
    ├── widgets/            ← reużywalne widgety
    └── tabs/               ← zakładki notebooka
```

### Zasada zależności
**`core` nie importuje z `gui`** — zawsze odwrotnie. CLI i GUI używają core.

### Wzorce
- **Strategy** dla silników konwersji (Pandoc/Calibre — wymienne)
- **Dataclass options** dla parametryzacji funkcji (`ConvertOptions`, `CssFixOptions`)
- **Context manager** dla `Epub` (auto-cleanup)
- **Result objects** (`ConversionResult`) zamiast wyjątków dla flow control

---

## Pułapki techniczne (z poprzedniego projektu)

### 1. DLL Conflict w PyInstaller
**Problem:** `python311.dll` z bundle vs Python użytkownika powoduje crash przy subprocess.

**Rozwiązanie:**
- Plików `.pyd` NIE umieszczaj w głównym katalogu `_MEIPASS`
- Subprocess z `python` musi mieć `sys.path[0]` wskazujący gdziekolwiek INDZIEJ niż na `_MEIPASS`
- Najprościej: kopia `__main__.py` do podkatalogu i odpalaj jak `python ./subdir/main.py`

### 2. Kindle Previewer output directory
**Problem:** KP3 nie pozwala na bezpośrednie wskazanie pliku wyjściowego — tworzy własny podkatalog.

**Rozwiązanie:**
```python
# Po konwersji:
for kfx_file in temp_outdir.rglob("*.kfx"):
    shutil.move(kfx_file, target_path)
```

### 3. Polskie znaki w ścieżkach
**Problem:** Windows CMD domyślnie cp1250, Python 3.11+ używa UTF-8 jako domyślny encoding.

**Rozwiązanie:**
- Wszystkie `open()` z `encoding="utf-8"`
- Subprocess z `text=True, encoding="utf-8", errors="replace"`
- Path operations zawsze przez `pathlib`, nie string concat

### 4. PDF → EPUB
**Problem:** Pandoc NIE czyta PDF jako input.

**Rozwiązanie:** automatic fallback do Calibre ebook-convert gdy source.suffix == ".pdf"

### 5. KFX engine selection
**WAŻNE:** Główny silnik to **Calibre + wtyczka KFX Output** (sprawdzony, mniej wrażliwy na formatowanie).  
Kindle Previewer 3 jest **EXPERIMENTAL** — wrażliwy na nieidealne formatowanie EPUB. Zawsze oznaczaj jako "experimental" w UI.

### 6. tkinter w testach na Linux CI
**Problem:** Brak displayu w GitHub Actions Ubuntu runner.

**Rozwiązanie:**
```yaml
- run: sudo apt-get install -y xvfb
- run: xvfb-run -a pytest tests/gui/
```

### 7. Czysty subprocess na Windows
**Problem:** Subprocess otwiera czarne okno CMD podczas konwersji.

**Rozwiązanie:**
```python
import sys
FLAGS = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
subprocess.run(cmd, creationflags=FLAGS, ...)
```

### 8. tkinterdnd2 — opcjonalna zależność
**Problem:** Drag&drop wymaga `tkinterdnd2`, ale niektórzy użytkownicy mogą nie mieć.

**Rozwiązanie:**
```python
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
# W kodzie warunek - jeśli HAS_DND to rejestruj D&D, inaczej nie
```

**Dodatkowo przy PyInstaller:** `tkinterdnd2` dołącza natywne binaria `tkdnd`, których PyInstaller domyślnie nie pakuje → `.exe` wywala się z `can't find package tkdnd`. W `.spec` trzeba jawnie dodać katalog `tkdnd` do `datas` (lub `--collect-all tkinterdnd2`).

### 9. Duże pliki EPUB — nie ładuj wszystkiego do RAM
**Problem:** EPUB z grafiką/wideo może mieć 50-150 MB. Trzymanie całości w `dict[str, bytes]` zjada RAM przy batch processing.

**Rozwiązanie:** przy zapisie kopiuj niezmienione wpisy bezpośrednio ze źródłowego ZIP, w pamięci trzymaj tylko zmodyfikowane pliki (wzorzec w ROADMAP Etap 1).

### 10. CSS — używaj tinycss2, nie cssutils
**Problem:** `cssutils` jest przestarzały, hałasuje ostrzeżeniami przy CSS3 (`--var`, `@supports`, `calc()`) i bywa nadgorliwy przy modyfikacjach — może uszkodzić poprawny layout.

**Rozwiązanie:** `tinycss2` (tokenizer W3C) lub precyzyjny regex. Zachowuj nieznane reguły bez zmian, modyfikuj tylko jawnie celowane.

### 11. Hyphenation — soft-hyphen vs CSS to kompromis
**Problem:** Soft-hyphen (`\u00ad`) działa wszędzie (też stary Kindle), ale psuje słownik i wyszukiwarkę na czytniku. CSS `hyphens: auto` jest czysty, ale słabo wspierany na Kindle.

**Rozwiązanie:** oferuj OBIE metody, NIE wybieraj za użytkownika. Przy soft-hyphen pokaż ostrzeżenie w GUI.

---

## Workflow Claude Code

### Każda sesja zaczyna się od:
1. `git status` — co jest na tapecie
2. `git log --oneline -10` — ostatnie commity
3. `gh pr list` — otwarte PR-y
4. Czytanie `ROADMAP.md` — gdzie jesteśmy

### Przed pisaniem kodu:
1. Sprawdź czy są testy dla istniejącego API
2. Sprawdź czy podobne wzorce są już użyte gdzie indziej
3. **Przy pracy nad warstwą wyższą (GUI, CLI) ZAWSZE najpierw przeczytaj aktualny stan modułów core których będziesz używać** — kształt dataclass, sygnatury funkcji. NIE twórz mocków ani duplikatów klas z `core/`. Importuj i używaj prawdziwych. To zapobiega rozjazdowi między warstwami przy długich sesjach.
4. Zaproponuj plan jeśli zadanie ma >50 linii kodu

### Przed commitem:
1. `pytest` — wszystkie zielone
2. `ruff check . --fix` — auto-fix lint
3. `mypy src/` — type check
4. `git diff` — przegląd zmian

### Commit message format:
```
<typ>(<scope>): <krótki opis - obecny czas, mała litera>

<dłuższy opis opcjonalnie>

<footer opcjonalny, np. Closes #42>
```

Typy: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `style`, `perf`, `ci`, `build`

Przykład:
```
feat(core): add Epub.metadata property for Dublin Core access
```

### Po wykonaniu zadania:
1. Podsumuj co zostało zrobione
2. Pokaż git status / git log
3. **Zaproponuj** komendy push i PR (nie wykonuj sam)
4. Czekaj na zatwierdzenie

---

## Pliki, które ZAWSZE czytaj na początku sesji

1. **`CLAUDE.md`** (ten plik)
2. **`ROADMAP.md`** — gdzie jesteśmy
3. **`ROADMAP_FEATURES_v1.1.md`** — plan funkcji v1.1 (jeśli pracujemy nad nową funkcją)
4. **`GUI_STANDARD.md`** — standardy i wzorce GUI (jeśli pracujemy nad GUI)
5. **`pyproject.toml`** — zależności, scripts
6. **Aktualne `PROMPTS.md`** — co użytkownik mógł właśnie wkleić

---

## Komendy często używane

```bash
# Setup
pip install -e ".[dev]"

# Testy
pytest                           # wszystkie
pytest tests/test_metadata.py    # konkretny plik
pytest -v -k "test_polish"       # z filtrem nazwy
pytest --cov=src/epubforge       # z coverage

# Lint
ruff check .
ruff check . --fix
ruff format .

# Typy
mypy src/

# Git
git checkout -b feature/stage-N-name
git add -A && git commit -m "feat(scope): description"
git push -u origin HEAD

# GitHub
gh pr create --title "..." --body "..."
gh pr merge --squash --delete-branch
gh pr list
gh run list
gh run view <id> --log

# Build (Windows only)
build/build.bat

# Run
python -m epubforge --help      # CLI
epubforge-gui                   # GUI (po instalacji)
```

---

## Anti-patterns — czego NIE robić

❌ Globalne zmienne mutowalne  
❌ `from epubforge.core.epub import *` (wildcard imports)  
❌ Funkcje > 50 linii (rozbij na mniejsze)  
❌ Pliki > 500 linii (podziel na moduły)  
❌ `except Exception:` bez specyficznego typu  
❌ `print()` w kodzie biblioteki (użyj `logging`)  
❌ Hardcoded ścieżki absolutne  
❌ Subprocess bez timeout  
❌ ZIP operations bez context managera  
❌ Mock everything (testy integracyjne też są ważne)  
❌ Commit bez wcześniejszego `pytest`  
❌ Push bez zgody użytkownika

---

## Pytania, które ZAWSZE warto zadać przed dużą zmianą

1. Czy to powinno być w `core/`, `converters/`, `fixers/`, czy `gui/`?
2. Czy ta funkcja ma sens jako część biblioteki (API) czy tylko CLI/GUI?
3. Czy mockujemy zewnętrzne zależności w testach?
4. Czy publiczne API ma docstring i type hints?
5. Czy potrzebujemy migration path dla użytkowników (jeśli zmiana API)?
6. Czy aktualizujemy README.md / docs/?

---

**Pamiętaj:** Ten projekt to **nauka na błędach poprzedniego forka epubQTools**. Tam mieliśmy 2000-liniowy monolit. Tutaj robimy to inaczej — mały, modularny, testowalny.
