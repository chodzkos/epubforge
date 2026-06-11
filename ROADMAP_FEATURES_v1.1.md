# 🗺️ EpubForge — Roadmap v1.1+ (migracja Qt + Features F1, F2, F3+, F7, F8, F10, F11)

Plan rozwoju po wydaniu v1.0. Obejmuje:
**F-M** — migrację GUI tkinter → **PySide6** zgodnie z `GUI_STANDARD.md` (EpubForge oznaczony tam jako „rozważyć migrację po v1.0" — robimy to teraz, **przed** nowymi funkcjami, zgodnie z zasadą „osobny refactor, nie miesza się z funkcjami"),
oraz funkcje z `FEATURES.md`: **F1** (i18n), **F2** (EpubCheck), **F3** (edytor — **rozszerzony o inspektor reguł CSS z podglądem na żywo**), **F7** (MOBI→EPUB), **F8** (statystyki), **F10** (TOC), **F11** (presety CSS).

Dokument uzupełnia `ROADMAP.md`, `CLAUDE.md` i `GUI_STANDARD.md` (zasady bez zmian: pliki < 500 linii, mypy --strict, coverage ≥ 70%, conventional commits, squash merge, core nie importuje gui, paleta i wzorce układu ze standardu §5–6). Prompty: `PROMPTS_FEATURES_v1.1.md`.

---

## 0. Kolejność realizacji i zależności

```
F-M (migracja GUI → PySide6) ───► WSZYSTKO poniżej pisane już natywnie w Qt
F-A (F1 i18n) ──────────────────► wszystkie nowe stringi od razu przez _()
F-B (F11 presety CSS) ──┐
F-C (F3 edytor core) ───┼──► F-D (F3+ inspektor CSS live preview, QTextDocument)
                        │         │
F-C ────────────────────┴──► F-E (F2 EpubCheck — klikalne błędy skaczą do edytora)
F-C ─────────────────────────► F-F (F10 TOC — QTreeWidget z natywnym drag&drop)
F-G (F7 MOBI→EPUB)  — niezależny (bez GUI-ciężkich zmian)
F-H (F8 statystyki) — niezależny
```

| Etap | Zakres | Gałąź | Estymacja | Zależy od |
|---|---|---|---|---|
| **F-M** | **migracja gui/ na PySide6 (parytet 1:1 z v1.0)** | `refactor/gui-pyside6` | **10–14 h** | — |
| F-A | F1 — i18n (gettext) | `feature/f1-i18n` | 5–7 h | F-M |
| F-B | F11 — presety CSS | `feature/f11-css-presets` | 4–5 h | F-A |
| F-C | F3 — edytor (core) | `feature/f3-editor-core` | 7–9 h | F-A |
| F-D | F3+ — inspektor CSS live | `feature/f3-css-inspector` | 7–9 h | F-C |
| F-E | F2 — EpubCheck | `feature/f2-epubcheck` | 6–8 h | F-C |
| F-F | F10 — TOC | `feature/f10-toc` | 8–10 h | F-C |
| F-G | F7 — MOBI→EPUB | `feature/f7-mobi-to-epub` | 3–4 h | F-M |
| F-H | F8 — statystyki | `feature/f8-stats` | 6–8 h | F-A |

Uzasadnienie: **migracja jako etap zerowy** — każda kolejna zakładka (Edytor, Walidacja, TOC, Statystyki) powstaje raz, w Qt, zamiast być pisana w tkinter i portowana. F1 zaraz po niej, bo dotyka każdego stringa. F3 przed F2/F10 (kontrakt `open_in_editor` + wzorce). Estymacje F-C/F-D/F-F **spadły** względem wariantu tkinter: Qt daje QSyntaxHighlighter, QTextDocument z CSS i wbudowany drag&drop w drzewach.

---

## 1. Decyzje architektoniczne (globalne)

### 1.1. Stack GUI po migracji (zgodnie z GUI_STANDARD §4)

| Element | Wybór |
|---|---|
| Framework | PySide6 ≥ 6.6 (LGPL — zgodne z MIT; bundling PyInstallerem OK, linkowanie dynamiczne) |
| Motyw | `pyqtdarktheme` (qdarktheme) — ciemny; **jasny = przywrócony natywny styl Qt** (pułapka „wypranego" light z IcoForge) |
| Akcent | `#5DCAA5` / `#1D9E75` przez `custom_colors` (znak rozpoznawczy ze standardu §5) |
| Pasek tytułu | DWM przez `ctypes`, HWND z `winId()` w `showEvent`; re-wymuszenie w `changeEvent(ActivationChange)` |
| D&D | natywny Qt (`dragEnterEvent`/`dropEvent`) — **tkinterdnd2 wylatuje** |
| Wątki | QThread + sygnały (LogStreamer wg tabeli komponentów standardu §7) |
| Testy GUI | `pytest-qt` + `QT_QPA_PLATFORM=offscreen` — **xvfb wylatuje z CI** |

Zależności po migracji: `[gui] = PySide6, pyqtdarktheme` (Pillow zostaje tylko jeśli faktycznie potrzebny — Qt ma QPixmap; do weryfikacji w F-M). Usuwane: `tkinterdnd2`, `darkdetect` (qdarktheme ma własną detekcję; jeśli wersja qdarktheme jej wymaga — zostaje jako transitive). Dev: `pytest-qt`.

⚠️ **Znane ryzyko:** `pyqtdarktheme` 2.1.0 nie jest aktywnie utrzymywany i miał problem importu na Python 3.12. Mitygacja: użyć **dokładnie tego samego pakietu/wersji/obejścia co w IcoForge** (tam już działa); jeśli problem wystąpi — fork `pyqtdarktheme-fork` z PyPI albo pin Pythona w buildzie. Decyzja zapisana w F-M.

### 1.2. Nowe moduły — mapa docelowa

```
src/epubforge/
├── i18n.py                      ← F1: gettext wrapper, _(), set_language()
├── locale/{pl,en,de}/LC_MESSAGES/epubforge.{po,mo}
├── validators/epubcheck.py      ← F2
├── toc/{model,reader,generator,writer,repair}.py   ← F10
├── stats.py + stats_stopwords/  ← F8
├── fixers/css_presets.py + presets/                 ← F11
├── fixers/css_rules.py          ← F3+: parse_rules/replace_rule/spany (czysta logika, bez GUI)
├── converters/{to_epub.py, kindle_drm.py}           ← F7
├── cli/{check,toc,stats,presets}.py
└── gui/                         ← PO MIGRACJI: wyłącznie PySide6
    ├── app.py                   ← QApplication + MainWindow(QMainWindow)
    ├── theme.py                 ← ThemeManager (qdarktheme + native light + paleta standardu)
    ├── window_theme.py          ← DWM titlebar (winId)
    ├── workers.py               ← QThread worker + LogStreamer (sygnały)
    ├── widgets/                 ← gui-kit wg GUI_STANDARD §7
    │   ├── path_entry.py  file_list.py  section.py  tooltip helpers  about_panel.py
    │   ├── code_editor.py       ← F3: QPlainTextEdit + numery linii + find bar
    │   ├── syntax_highlight.py  ← F3: QSyntaxHighlighter (xml/css)
    │   └── css_inspector.py     ← F3+: panel reguł + podgląd QTextDocument
    └── tabs/{metadata,converter,fixer,kfx}.py        ← port 1:1
        + editor.py (F3)  validator.py (F2)  toc.py (F10)  stats.py (F8)
```

Zasada bez zmian: wszystko poza `gui/` — **zero importów z gui i z PySide6**. To dzięki temu migracja w ogóle jest tania (GUI_STANDARD §11 wprost: „przepisujesz tylko gui/").

### 1.3. i18n — gettext, nie Qt Linguist

Świadoma decyzja: **zostajemy przy gettext** (a nie `tr()`/QTranslator), bo: (1) jeden system obejmuje też CLI, (2) workflow babel/.po jest niezależny od frameworka, (3) `.po` edytuje się zwykłym tekstem (tłumaczy AI). msgid = polski (obecne stringi), tłumaczenia en/de, `.mo` commitowane, `build/compile_locales.py` regeneruje. Zmiana języka: wymaga restartu (komunikat w UI) — dynamiczne `retranslateUi` to ewentualna przyszłość.

### 1.4. PyInstaller / build — skutki

- Rozmiar exe rośnie do ~60–110 MB (akceptowane w standardzie §4). W `.spec`: wyklucz nieużywane moduły Qt (`QtWebEngine*`, `Qt3D*`, `QtQuick*`, `QtMultimedia` itd.) — to główna dźwignia rozmiaru.
- `datas`: `epubforge/locale/**/*.mo` (F1), `fixers/presets/*` (F11), `stats_stopwords/*` (F8), `gui/assets/*`.
- `build/check_build_env.py`: sprawdzenie importu PySide6 + qdarktheme + obecności zasobów; usunięcie checków tkdnd.
- Pułapka DLL/subprocess z CLAUDE.md (python3xx.dll) obowiązuje nadal.

### 1.5. CI (oszczędzanie minut)

Zmiana **na plus**: zamiast `apt-get install xvfb` + `xvfb-run` — `QT_QPA_PLATFORM=offscreen` w env joba (na Ubuntu potrzebne jeszcze `libegl1`/`libgl1` — jedna linia apt, szybsza niż xvfb). `pytest-qt` w dev. Zero nowych workflow; testy F2/F7 mockują subprocess jak dotąd.

---

## 2. Etap F-M — migracja GUI tkinter → PySide6

**Cel:** parytet funkcjonalny 1:1 z v1.0 (Metadane, Konwerter, Fixer, Eksport Kindle, About, motywy, D&D, ciemny pasek tytułu), zero zmian w `core/`, `converters/`, `fixers/`, `cli/`. Wygląd wg GUI_STANDARD §5–6.

**Projekt:**

1. **Szkielet** (`app.py`): `QApplication` → `MainWindow(QMainWindow)`; centralny widget = pionowy layout: **górny pasek** (logo+„EpubForge" po lewej; po prawej QToolButton „Motyw" z menu auto/jasny/ciemny + QToolButton „ⓘ" About — meta-rzeczy NIE jako zakładki, standard §6) → `QTabWidget` (tylko funkcje robocze) → **pasek statusu** (`statusBar()` z wykrytymi narzędziami). Geometria i motyw z/do `config.json` (mechanizm `core/config.py` bez zmian).
2. **ThemeManager** (`theme.py`): przed pierwszą zmianą zapamiętaj `app.style().objectName()`, `app.palette()`, `app.styleSheet()`; `dark`/`auto-dark` ⇒ `qdarktheme.setup_theme("dark", custom_colors={"primary": "#5DCAA5"})`; `light` ⇒ **przywrócenie natywnych** zapamiętanych wartości (+ ewentualny minimalny stylesheet z akcentem) — pułapka „wyprany light" z IcoForge; po zmianie `unpolish/polish` na `app.allWidgets()`. Eksponuje dataclass `Theme` z rolami palety standardu (bg/bg2/bg3/fg/fg2/accent/red/amber/border) dla customowych widżetów — **żadnych hardcoded hexów w tabach**, tylko role.
3. **Pasek tytułu** (`window_theme.py`): `DwmSetWindowAttribute(20)` na `int(self.winId())` wołane z `showEvent`; `changeEvent` na `ActivationChange` ponawia (pułapka „dialog odbiera focus → pasek jaśnieje"); Win10: `WM_NCACTIVATE` + `RedrawWindow(RDW_FRAME)`.
4. **gui-kit** (`widgets/`, wg tabeli standardu §7): `PathEntry` (QLineEdit+„…"), `FileList` (QListWidget + toolbar Dodaj/Folder/Usuń/Wyczyść + licznik + natywne D&D z `setAcceptDrops`), `Section` (QGroupBox), Toggle→QCheckBox, tooltipy przez `setToolTip` (Qt motywuje je poprawnie — cały customowy Tooltip znika), `AboutPanel` (logo warunkowo, wersja z `__version__`, linki `webbrowser`).
5. **Wątki** (`workers.py`): `Worker(QThread)` z sygnałami `line(str, level)`, `finished(result)`, `failed(str)`; log w GUI = `QPlainTextEdit` read-only z `QTextCharFormat` per poziom (ok/warn/err wg ról Theme). Zastępuje `streaming.py` (kolejka+after). **Żadnych wywołań GUI z wątku roboczego — tylko sygnały.**
6. **Port zakładek 1:1**: metadata, converter, fixer, kfx — logika wywołań core bez zmian (czytać aktualne sygnatury core przed portem!), layouty QGridLayout/QFormLayout, dialogi `QFileDialog` (opcja `DontUseNativeDialog` powiązana z motywem ciemnym — natywne jasne dialogi były głównym powodem migracji), `QMessageBox` zamiast messagebox.
7. **Czyszczenie**: usunięcie `tkinterdnd2`/`darkdetect` z deps i `_init_tkdnd`; README sekcja GUI (znika ostrzeżenie o jasnych dialogach!); testy `tests/gui/` przepisane na pytest-qt; CI: offscreen zamiast xvfb; `.spec` przebudowany (collect PySide6, exclude zbędnych Qt modułów, bez tkdnd); `GUI_STANDARD.md` — aktualizacja mapy projektów (EpubForge → Qt).
8. **Definicja parytetu (kryteria akceptacji):** wszystkie operacje v1.0 wykonywalne; motyw ciemny obejmuje dialogi plików i menu; D&D plików działa we wszystkich listach; exe portable + instalator budują się i odpalają; `pytest -m gui` zielone offscreen.

**Testy:** pytest-qt: smoke startu MainWindow, przełączenie motywu nie wywala i zmienia paletę, FileList przyjmuje pliki (symulacja QDropEvent lub API), PathEntry ustawia ścieżkę, każdy tab się buduje, worker emituje sygnały (z mockiem subprocess), AboutPanel pokazuje `__version__`.

**Twoje zadania (człowiek):**
1. Decyzja przed startem: minimalna wersja PySide6 i wersja pyqtdarktheme — **sprawdź w pyproject IcoForge i podaj te same** (unikamy drugi raz tej samej walki; ewentualny fork pyqtdarktheme-fork).
2. Po porcie: pełny przeklik wszystkich 4 zakładek na Windows w obu motywach, w tym dialogi plików w ciemnym; porównaj z v1.0 (odpal starą wersję obok).
3. `build\build.bat` → sprawdź rozmiar exe; jeśli > ~120 MB, zgłoś do doszlifowania excludes.
4. Zaktualizuj zrzuty ekranu w README (to dobry moment — nowy wygląd).
5. Rozważ tag `v1.0.x-tkinter` przed merge (ostatni punkt powrotu starego GUI).

---

## 3. Projekty szczegółowe funkcji

*(Wszystkie GUI poniżej — już w PySide6, wg wzorców z F-M; stringi przez `_()` od F-A.)*

### F-A · F1 — Wielojęzyczność (i18n)

**Projekt:** jak w §1.3 — `src/epubforge/i18n.py` (`init_i18n`, `_`, `ngettext` — PL ma 3 formy mnogie, `detect_system_language` przez `QLocale.system().name()` z fallbackiem `locale`, `available_languages`, localedir odporny na `sys._MEIPASS`). Refactor: wszystkie stringi użytkownika w `gui/` i `cli/` przez `_()`; docstringi/logi/wyjątki wewnętrzne — nie. Babel: `babel.cfg`, extract → `epubforge.pot`, init en/de, **tłumaczenia wypełnia Claude Code**, kompilacja `build/compile_locales.py`, `.mo` w repo. GUI: w pasku górnym obok „Motyw" QToolButton „Język" (Auto/Polski/English/Deutsch), zapis `config["language"]`, QMessageBox o restarcie. Uwaga Qt: stringi muszą być tłumaczone **w momencie budowy widżetu** (po `init_i18n`), nie na poziomie stałych modułowych importowanych przed initem.

**Testy:** `_()` pod wymuszonym en, fallback, `ngettext` 1/2/5 PL, spójność .pot↔.po (brak pustych/fuzzy), aktualność .mo względem .po, smoke pytest-qt z `language=en`.

**Twoje zadania:** przegląd EN/DE (kalki, długość etykiet DE!), test exe z locale, decyzja o domyślnym „auto" (rekomendacja: tak).

---

### F-B · F11 — Biblioteka presetów CSS

**Projekt (warstwa logiki — identyczna niezależnie od GUI):**
```python
@dataclass(frozen=True)
class CssPreset: id; name; description; css; builtin; path
def list_presets(user_dir=None) -> list[CssPreset]
def apply_preset(epub, preset, mode: Literal["append","replace"]="append") -> None
def import_user_preset(source_css, name, user_dir) -> CssPreset
```
`append` (domyślny): zapis `{opf_dir}/styles/epubforge-preset.css`, rejestracja `<item>` w manifeście OPF, `<link>` jako **ostatnie** dziecko `<head>` każdego pliku spine (lxml, ścieżki względne przez posixpath.relpath; bazy manifestu i linków są RÓŻNE). `replace`: usunięcie istniejących arkuszy (manifest+linki+pliki) → append. Idempotencja: ponowna aplikacja = podmiana zawartości arkusza. Wbudowane (`fixers/presets/` + `presets.json` z nazwami/opisami pl/en/de): `reader-friendly`, `print-like`, `dark-oled` (komentarz: e-ink nadpisuje kolory), `manga-rtl` (komentarz: ograniczone wsparcie czytników). Presety użytkownika: `<config>/presets/*.css`, import walidowany tinycss2.

CLI: `epubforge presets list`, `epubforge fix --preset ID [--preset-mode replace]`. GUI: w `FixerTab` `Section` „Preset CSS": QComboBox (nazwa — opis), QRadioButton append/replace, „Importuj własny…" (QFileDialog), checkbox włączający krok w pipeline. Po F-D dojdzie przycisk „Podgląd".

**Testy:** apply/idempotencja/replace na fixture, link ostatni w head każdego spine, EPUB po save otwiera się (mimetype pierwszy, ZIP_STORED), import waliduje i odrzuca śmieci, CLI list/fix.

**Twoje zadania:** wizualna ocena presetów na czytniku (dark-oled na Kindle!), finalne wartości typografii, ewentualny własny preset „Mój standard PL".

---

### F-C · F3 — Edytor wewnętrzny (core)

**Cel:** przegląd + szybka edycja HTML/CSS w EPUB; quick fix, nie Sigil.

**Projekt:**
- `widgets/syntax_highlight.py`: dwie klasy `QSyntaxHighlighter` — `XmlHighlighter` (komentarz, tag, atrybut, wartość, encja) i `CssHighlighter` (komentarz, selektor, @-reguła, właściwość, wartość, !important); reguły jako lista (QRegularExpression, format); kolory z ról `Theme` (jasny/ciemny); obsługa stanów wieloliniowych (komentarze) przez `setCurrentBlockState` — Qt sam dba o inkrementalność (highlight per blok), znika cały ręczny debounce z wariantu tk.
- `widgets/code_editor.py`: `QPlainTextEdit` + **line number area** (kanoniczny wzorzec Qt: `lineNumberAreaPaintEvent` + `blockCountChanged`/`updateRequest`) + pasek wyszukiwania (Ctrl+F: QLineEdit, Następny/Poprzedni F3/Shift+F3, podświetlenie trafień przez `setExtraSelections`, licznik „3/17") + status wiersz:kolumna (`cursorPositionChanged`). API: `load(text, profile)`, `get_text()`, `goto_line(n)` (QTextCursor + `centerCursor`), `read_only` (`setReadOnly`), sygnał `modified_changed` (z `document().modificationChanged`). Undo/redo ma QPlainTextEdit za darmo.
- `tabs/editor.py` — zakładka „Edytor":
  - toolbar: „Otwórz EPUB…", ścieżka, „Zapisz EPUB" (enabled przy zmianach), toggle „Tryb edycji" (**domyślnie wyłączony** — start read-only);
  - `QSplitter`: lewo `QTreeWidget` (grupy Tekst/Style/Obrazy/Fonty/Inne wg media-type z manifestu, fallback po rozszerzeniu dla `list_files()` spoza manifestu; `*` przy zmodyfikowanych), prawo `QStackedWidget`: CodeEditor / podgląd obrazu (`QLabel` + `QPixmap.fromImage`, skalowanie `KeepAspectRatio` w `resizeEvent`) / panel info dla binariów;
  - stan: jeden `Epub` na życie zakładki; `_dirty: dict[str, str]` (treści niezapisane do bufora Epub); flow zmiany pliku z pytaniem Zapisz/Porzuć/Anuluj (QMessageBox);
  - Ctrl+S: dla XHTML/OPF próba `lxml.etree.fromstring` → błąd ⇒ „Plik nie jest poprawnym XML… Zapisać mimo to?"; zapis = `epub.write_file(path, text.encode("utf-8"))`; „Zapisz EPUB" = `epub.save()` (backup .bak jak dotąd); osobny wskaźnik „EPUB ma niezapisane zmiany";
  - dekodowanie `utf-8, errors="replace"`; znaki zastępcze ⇒ infobar + wymuszony read-only pliku;
  - `closeEvent` MainWindow pyta `editor_tab.has_unsaved_changes()`.
- **Kontrakt między-zakładkowy** w `MainWindow`:
  ```python
  def open_in_editor(self, epub_path: Path, internal_path: str | None = None, line: int | None = None) -> None
  ```
  (przełącz QTabWidget, otwórz/reużyj EPUB, zaznacz w drzewie, `goto_line`). Konsumenci: F-E, F-D.

**Testy:** czyste: klasyfikacja plików, przeliczenia offset↔(linia,kolumna); pytest-qt: load/get_text z polskimi znakami, goto_line, read_only blokuje `qtbot.keyClicks`, search liczy trafienia, pełny flow edycja→write_file→save→reopen przez Epub, plik nie-UTF8 → read-only, `open_in_editor` zaznacza i ustawia linię, highlighter koloruje (sprawdzenie formatów bloku).

**Twoje zadania:** UX-test na dużej książce (50+ MB), akceptacja decyzji „read-only domyślnie", lista oczekiwanych skrótów.

---

### F-D · F3+ — Inspektor reguł CSS z podglądem na żywo *(rozszerzenie spoza FEATURES.md)*

**Cel:** przy otwartym `.css` — panel z listą reguł; każda reguła pokazuje **przykładowy tekst sformatowany tak, jak zadziała**; edycja reguły aktualizuje podgląd **na żywo**; „Zastosuj" wpisuje zmianę do arkusza.

**Projekt — dwie warstwy:**

1. **Logika bez GUI — `src/epubforge/fixers/css_rules.py`** (czyste funkcje, pełne testy jednostkowe):
   - `parse_rules(source) -> list[CssRuleInfo]` — `CssRuleInfo(selector, declarations, span, media, previewable, parse_errors)`; **span = offsety znakowe `[start, end)` reguły w źródle**, liczone z `source_line/source_column` tokenów tinycss2 + tabeli offsetów początków linii; koniec = pozycja domykającej `}` wyznaczona od pozycji końca ostatniego tokenu content (odporność na `}` w stringach/komentarzach); reguły w `@media` rekurencyjnie z kontekstem; `@font-face/@page/@import` — previewable=False.
   - `replace_rule(source, span, new_text) -> str` — **jedyna** legalna modyfikacja źródła (zero re-serializacji tinycss2 — zachowujemy formatowanie użytkownika).
   - `parse_single_rule(text)` — walidacja edytowanej reguły.
   - `declarations_to_preview(decls) -> tuple[str, list[str]]` — buduje **inline `style="…"`** z deklaracji przefiltrowanych do podzbioru CSS wspieranego przez silnik rich text Qt („Supported HTML Subset"): font-family/-size/-weight/-style, color, background-color, text-align (**w tym justify — działa!**), text-indent, line-height, margin-*, padding-*, text-decoration, text-transform; jednostki px/pt/em/% normalizowane; reszta → lista „nieobsługiwane w podglądzie". Celowo **inline style zamiast selektorów** w `setDefaultStyleSheet` — omijamy ograniczenia dopasowania selektorów w Qt i zachowujemy pełną kontrolę nad listą nieobsługiwanych.
   - `sample_for_selector(selector) -> (html_tag, text)` — heurystyka: h1..h6 → nagłówek „Rozdział pierwszy"; p/body/klasy → akapit **z polskimi diakrytykami** („Zażółć gęślą jaźń…" + 2 zdania); blockquote → cytat; code/pre → fragment kodu; inne → akapit domyślny.

2. **Widget — `gui/widgets/css_inspector.py`** (`CssInspector(QWidget)`):
   - konstruktor: `get_source: Callable[[], str]`, `apply_replacement: Callable[[int, int, str], None]`, `theme`;
   - layout (QSplitter pionowy): (1) `QTreeWidget` reguł: Selektor | Deklaracje (skrót) | @media (at-reguły wyszarzone); (2) **edytor reguły** — mały CodeEditor (profil css, ~8 linii) z blokiem `source[span]`; (3) **podgląd** — `QTextEdit` read-only, dokument z próbką HTML + inline style; tło podglądu zawsze „papierowe" (biała karta z ramką), **niezależnie od motywu aplikacji** — żeby dark mode nie fałszował typografii; pod spodem: „Nieobsługiwane w podglądzie: …" + stała adnotacja „Podgląd przybliżony — czytnik może różnić się w szczegółach"; (4) „Zastosuj do arkusza" / „Przywróć";
   - **live**: `textChanged` edytora reguły → `QTimer.singleShot`-debounce 300 ms → `parse_single_rule` → OK: przebudowa HTML podglądu (`setHtml`); błąd: czerwona ramka + komunikat parsera, podgląd na ostatnim poprawnym;
   - **Zastosuj**: walidacja → `apply_replacement(start, end, new_text)` → `refresh()` (re-parse listy, spany przeliczone, zaznaczenie zachowane po selektorze);
   - `refresh()` wołany też po edycji w głównym edytorze (debounce 400 ms na jego `textChanged`).
   - Integracja w `tabs/editor.py`: dla plików css panel w prawym QSplitterze, **domyślnie otwarty** (toggle w toolbarze); `apply_replacement` przez QTextCursor głównego edytora (przeliczenie offsetów na pozycje) — **undo działa**, plik dostaje `*`, dalej standardowy flow Ctrl+S/„Zapisz EPUB".
   - Synergia F11: w sekcji presetów przycisk „Podgląd…" → QDialog z CssInspector w trybie read-only (Zastosuj ukryty).

**Testy:** `css_rules.py` — spany (prosta, wieloselektorowa, komentarze przed/wewnątrz, `content: "}"` i `url("a}b.png")`, @media zagnieżdżone, @font-face previewable=False), replace_rule nie rusza ani bajta poza spanem, `declarations_to_preview` per właściwość + jednostki + kolory hex/rgb()/nazwy + `!important` (adnotacja) + nieznana właściwość → unsupported, sample_for_selector dla h1/p/.quote/blockquote/code/fallback; pytest-qt — panel widoczny dla css, wybór reguły ładuje edytor, edycja „red→blue" + przeskoczenie debounce → HTML podglądu zawiera nowy kolor, „Zastosuj" → `get_text()` głównego edytora zawiera zmianę i undo ją cofa.

**Twoje zadania:** przeklik na arkuszach z prawdziwych książek (zwłaszcza Calibre — ogromne arkusze: oceń wydajność listy reguł), ocena wierności podglądu (line-height, justify), akceptacja auto-otwierania panelu.

---

### F-E · F2 — Walidacja przez EpubCheck

**Projekt:**
- **Detekcja** (`core/detection.py`, wzorzec istniejących Tooli): `Tools.java()` — PATH, `JAVA_HOME/bin`, katalogi Temurin; wersja z `java -version` (**stderr!**), wymagane ≥ 11; `Tools.epubcheck()` — jar wg kolejności: config override `tools.epubcheck_jar` → glob `%ProgramFiles%/epubcheck*/` i `~/epubcheck*/` → `<config>/epubcheck/epubcheck.jar` → obok exe; wersja z `META-INF/MANIFEST.MF` jara (zipfile, bez uruchamiania javy). Oba w `detect_with_cache`.
- `validators/epubcheck.py`: `ValidationMessage(severity, code, message, internal_path, line, column)`, `ValidationReport(valid, epubcheck_version, messages, duration_s, counts())`, `run_epubcheck(epub, java, jar, timeout=300)` — `java -jar epubcheck.jar plik --json tmp.json` (tempfile, CREATE_NO_WINDOW, utf-8/replace, timeout); exit≠0 przy poprawnym JSON = raport `valid=False` (nie wyjątek); brak JSON/timeout = `EpubforgeError` ze stderr; parser defensywny (`get` z defaultami), normalizacja path do ścieżki wewnętrznej (utnij do `*.epub/`).
- CLI `epubforge check book.epub [--json out] [--min-severity warning]`; exit 0 valid / 1 błędy / 2 brak narzędzi (z instrukcją).
- GUI `tabs/validator.py`: FileList + „Sprawdź" (Worker/QThread), pasek podsumowania „✗ N błędów · ⚠ N ostrzeżeń · ℹ N" (**ngettext**), filtry severity (QCheckBox), `QTreeWidget` wyników (ikona koloru wg Theme, kod, plik:linia, komunikat; pełny w tooltipie), **dwuklik → `main_window.open_in_editor(epub, internal_path, line)`**, „Eksport JSON/HTML". Brak java/jar ⇒ panel pomocy: instrukcja (Temurin 17+, epubcheck z W3C GitHub releases) + „Wskaż epubcheck.jar…" (QFileDialog → config → re-detekcja). Auto-pobierania jara **nie** robimy w v1.
- (Opcjonalna synergia, decyzja twoja: przycisk „Waliduj" w toolbarze Edytora po „Zapisz EPUB".)

**Testy:** zero realnej javy — fixture'y JSON (ok/errors/broken), parser+normalizacja+counts, mock subprocess (ok/exit≠0/timeout/brak pliku), parser wersji javy ze stderr („17.0.9" ok, „1.8.0_391" → unavailable), wersja z MANIFEST.MF (mini-jar budowany zipfile w tmp), CLI exit codes, pytest-qt: tabela z podstawionego raportu + dwuklik woła open_in_editor (mock).

**Twoje zadania:** instalacja Temurin JRE 17+ (Windows i WSL), pobranie epubcheck-5.x z W3C GitHub, wskazanie jara; testy na prawdziwych i celowo zepsutych EPUB-ach (zepsuj coś w Edytorze → walidator łapie → dwuklik trafia w linię); decyzja o auto-walidacji po zapisie (rekomendacja: tylko przycisk).

---

### F-F · F10 — Generator i edytor spisu treści

**Projekt:**
- `toc/model.py`: `TocEntry(title, href, children)` + **czysta** `move_entry(entries, src, dst, mode)` (rodzeństwo przed/po, zagnieżdżenie, zakaz przeniesienia do własnego potomka) — z pełnymi testami; to model pod D&D.
- `toc/reader.py`: nav.xhtml (item z `properties~=nav`, `<nav epub:type="toc">`, zagnieżdżone ol/li/a) → fallback toc.ncx (navMap); zwraca też źródło.
- `toc/generator.py`: spine w kolejności, lxml z recover; h1..h{max_level}; drzewo wg poziomów (osierocony h3 → poziom wyżej); tytuł = znormalizowany `itertext()`; nagłówek bez `id` ⇒ wstrzyknięcie `id="efh-NNNN"` (unikalność per plik, **idempotencja** drugiego przebiegu) i zapis XHTML z zachowaniem deklaracji XML i **doctype**; pierwszy nagłówek pliku → href bez fragmentu; plik bez nagłówków pomijany.
- `toc/writer.py`: nav.xhtml — jeśli istnieje, podmiana **tylko** elementu nav-toc; jeśli nie — pełny dokument pod `{opf_dir}/nav.xhtml` + manifest `properties="nav"` (spine nietknięty); toc.ncx — pełna regeneracja (uid z metadanych, playOrder DFS) + manifest + `spine@toc`.
- `toc/repair.py`: `validate_toc` (href istnieje? fragment istnieje? — cache id per plik) → lista problemów; `repair_toc` usuwa martwe (dzieci podciąga), zwraca (entries, removed).
- CLI: `epubforge toc book.epub --show | --generate [--max-level 3] | --repair [--dry-run]`.
- GUI `tabs/toc.py`: wybór EPUB → `QTreeWidget` (Tytuł | Cel); problemy czerwonym kolorem + tooltip; toolbar: Generuj (QSpinBox 1–6), Napraw (dialog z listą → potwierdź), Dodaj/Usuń, ⬆⬇⬅➡, „Zapisz do EPUB"; edycja tytułu: `Qt.ItemIsEditable` na kolumnie tytułu (wbudowane, bez Entry-overlay!); **drag&drop: `setDragDropMode(InternalMove)`** + w `dropEvent` synchronizacja modelu przez `move_entry` (kierunek: zmiana w widoku → przebuduj model → re-render; mapowanie item↔entry słownikiem); wskaźnik niezapisanych zmian + pytania przy zmianie pliku/zamknięciu.

**Testy:** generator na rozbudowanej fixture (poziomy, osierocony h3, `<em>` w nagłówku, polskie znaki, plik bez nagłówków, idempotencja id), writer→reader roundtrip (nav i ncx), manifest/spine poprawne, EPUB po save zdrowy, repair wykrywa martwy href i zły fragment, `move_entry` wszystkie tryby + zakaz cyklu, CLI show/generate/repair --dry-run, pytest-qt: wczytanie/generacja/edycja tytułu/zapis + symulacja przeniesienia przez model.

**Twoje zadania:** testy na książce z usuniętym nav (repair), płaskiej z Calibre i głębokiej; **weryfikacja TOC na Kindle po konwersji KFX**; domyślny max_level (rekomendacja: 3).

---

### F-G · F7 — Konwersja MOBI → EPUB

**Projekt:** wyłącznie **Calibre** (`ebook-convert`); KindleUnpack świadomie pominięty (**GPL/copyleft**). Routing w `converters/to_epub.py`: suffix ∈ {`.mobi`,`.azw3`,`.azw`,`.prc`} ⇒ wymuś Calibre (engine="pandoc" jawnie → czytelny ConversionError). **DRM:** `converters/kindle_drm.py` (~60–80 linii, czysty `struct`): nagłówek PalmDB → rekord 0 → magic „MOBI" → pole encryption type (0 = brak, 1/2 = DRM); DRM ⇒ przyjazny `ConversionError("Plik jest zabezpieczony DRM — konwersja niemożliwa. EpubForge nie usuwa zabezpieczeń.")` **przed** wywołaniem Calibre; dodatkowo mapowanie „DRM" ze stderr Calibre. CLI: `convert` już działa — aktualizacja help/README. GUI ConverterTab: filtry plików + wymuszenie/wyszarzenie silnika na Calibre + `QMessageBox.warning` dla DRM.

**Testy:** syntetyczne nagłówki PalmDB (struct.pack: enc 0/1/2, plik 10-bajtowy, brak magic) — **żadnych prawdziwych mobi w repo**; routing z mockiem subprocess; engine=pandoc → błąd; DRM=True ⇒ subprocess niewywołany; stderr „DRMError" → zmapowany komunikat.

**Twoje zadania:** lokalny legalny plik testowy (roundtrip własnego EPUB przez Calibre), ocena jakości wyniku (TOC, obrazy), **nie commituj plików książek**.

---

### F-H · F8 — Statystyki książki

**Projekt:** `src/epubforge/stats.py`: `ChapterStats`, `BookStats(words, chars, chapters, estimated_pages, reading_time_min, language, language_source, top_words)`, `StatsOptions(words_per_page=250, wpm=200, top_n=50)`, `compute_stats(epub, options)`, `render_report_html(stats, metadata)`. Ekstrakcja: spine w kolejności, lxml recover, `itertext()` z pominięciem script/style; tytuł rozdziału = h1/h2/`<title>`. Tokenizacja `re.findall(r"\w+", …)`, liczby odfiltrowane. Język: `langdetect` (extra `[stats]`, `DetectorFactory.seed=0`, próbka 10 k znaków) → fallback `metadata.language` → None (źródło zapisane). Stop-listy `stats_stopwords/{pl,en,de}.txt` (200–300 słów, generuje AI, **PL przeglądasz ty**). Raport HTML samowystarczalny (inline CSS, paleta jasna ze standardu §5, `html.escape` na wszystkim z książki): metadane, karty liczb, chmurka tagów (font-size log-skala 12–40 px), tabela rozdziałów, wykres słupkowy **inline SVG** generowany własną funkcją (≤60 słupków), stopka „Ctrl+P → PDF". CLI: `epubforge stats book.epub [--report out.html] [--top 50] [--words-per-page] [--wpm]`. GUI `tabs/stats.py`: wybór pliku → Worker → karty (QGroupBox: słowa, strony, czas h:min, język+źródło), lista top-słów, QTreeWidget rozdziałów, „Eksport HTML…"/„Otwórz raport" (webbrowser); adnotacja przy braku langdetect.

**Testy:** deterministyczne liczby na fixture, „Zażółć gęślą jaźń" = 3 słowa, liczby odfiltrowane, stop-lista pl filtruje, fallback języka (monkeypatch ImportError), top_words sort+remis alfabetyczny, raport: tytuł obecny, `<b>złośliwy</b>` w tytule rozdziału zescapowany, liczba `<rect>` = liczba rozdziałów, brak „http" w treści; CLI exit 0 + plik powstaje; pytest-qt smoke.

**Twoje zadania:** przegląd polskiej stop-listy, stałe domyślne (250/200 — możesz wolieć 220/180 dla PL), ocena raportu na ekranie i w druku do PDF, `pip install -e ".[dev,stats]"`.

---

## 4. Aktualizacje przekrojowe (każdy etap pamięta)

- **pyproject.toml:** F-M → `[gui] = PySide6>=6.6, pyqtdarktheme` (wersje z IcoForge), usunięcie tkinterdnd2/darkdetect, dev += `pytest-qt`; F-A → `babel` (dev); F-H → extra `stats = ["langdetect>=1.0.9"]`; dane pakietu (locale, presets, stopwords, assets) w wheel.
- **CI `test.yml`:** F-M — `QT_QPA_PLATFORM: offscreen` + `apt-get install -y libegl1` zamiast xvfb; bez nowych workflow.
- **build/** (`build.bat`, `.spec`, `check_build_env.py`): F-M (PySide6 + excludes Qt), F-A (locale + compile_locales), F-B (presets), F-H (stopwords).
- **README / docs/user-guide / docs/api-reference / CHANGELOG:** per etap; F-M usuwa ostrzeżenie o jasnych dialogach i aktualizuje sekcję GUI.
- **GUI_STANDARD.md:** po F-M zaktualizuj mapę projektów (EpubForge → Qt) — dokument żywy.
- **Wersjonowanie (propozycja):** F-M → **v2.0.0** (zmiana frameworka GUI to dobry powód na major; CLI/API bez zmian — możesz też wybrać v1.1.0, twoja decyzja); dalej: F-A..F-B → +0.1, F-C..F-D → +0.1, F-E → +0.1, F-F → +0.1, F-G..F-H → +0.1.

## 5. Twoja lista zadań — zbiorczo

**Przed startem:**
1. `git pull` na main, CI zielone; rozważ tag `v1.0.x-tkinter`.
2. Wyciągnij z IcoForge wersje PySide6/pyqtdarktheme + ewentualne obejścia (wkleisz do promptu F-M).
3. Decyzja wersjonowania (v2.0.0 po migracji?).

**Rytuał per etap:** prompt z `PROMPTS_FEATURES_v1.1.md` → przegląd diff → lokalnie `pytest`, `ruff check .`, `mypy src/` → **przeklik GUI na Windows w obu motywach** (CI testuje offscreen — realny Windows to twoja działka) → push/PR/CI → `gh pr merge --squash --delete-branch` → co 2–3 etapy `build\build.bat` + smoke exe.

**Specyficzne:** F-M: pełny przeklik parytetu + rozmiar exe + zrzuty README; F-A: przegląd EN/DE; F-E: Java+epubcheck.jar; F-C/F-D: UX na dużych książkach; F-F: TOC na Kindle po KFX; F-G: własny plik testowy poza repo; F-H: polska stop-lista; F-B: presety na czytniku.

## 6. Ryzyka i miny

| Ryzyko | Mitygacja |
|---|---|
| pyqtdarktheme nieutrzymywany / problem na Py 3.12 | te same wersje/obejścia co IcoForge; fallback: pyqtdarktheme-fork; decyzja w F-M |
| „Wyprany" jasny motyw qdarktheme | light = przywrócony natywny styl Qt (zapamiętany przed pierwszą zmianą) — GUI_STANDARD §4 |
| Pasek tytułu jaśnieje po dialogu | `changeEvent(ActivationChange)` re-wymusza DWM — GUI_STANDARD §4 |
| Rozmiar exe po Qt | excludes modułów Qt w .spec; akceptowany budżet 60–110 MB |
| Regresje funkcjonalne przy porcie | parytet jako jawna checklista akceptacji F-M; tag powrotu `v1.0.x-tkinter` |
| Podgląd CSS ≠ czytnik (F3+) | QTextDocument renderuje realny podzbiór CSS (lepszy niż tk), ale nadal: jawna adnotacja „podgląd przybliżony" + lista nieobsługiwanych |
| Podmiana reguły psuje arkusz (F3+) | spany z tokenów tinycss2, testy edge-case (`}` w stringach), zapis przez QTextCursor ⇒ undo |
| EpubCheck JSON zmienia format | parser defensywny + fixture'y + wersja w raporcie |
| `java -version` na stderr | czytamy stderr |
| Wstrzykiwanie id psuje XHTML (F10) | lxml z zachowaniem doctype, idempotencja, roundtrip-testy, backup .bak |
| PL pluralizacja (F1) | wyłącznie ngettext, Plural-Forms nplurals=3, testy 1/2/5 |
| GPL/copyleft (F7) | bez kindleunpack; Calibre tylko jako zewnętrzny subprocess; PySide6 = LGPL (linkowanie dynamiczne, OK z MIT) |
| Minuty GitHub Actions | offscreen zamiast xvfb (taniej), zero nowych workflow, mocki subprocess |
| Wątki Qt | GUI tylko z głównego wątku; workery komunikują się wyłącznie sygnałami |
