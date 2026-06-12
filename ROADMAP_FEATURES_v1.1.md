# 🗺️ EpubForge — Roadmap v1.1+ (migracja Qt + Features F1, F2, F3+, F7, F8, F10, F11)

| Wersja | Data | Zmiany |
|---|---|---|
| 2.0 | 2026-06-12 | dostosowanie do GUI_STANDARD v2.0: nowy etap **F-S** (własny theme.py zamiast qdarktheme, platformdirs, debounce configu, niuanse DWM/dialogów, build/CI); statusy ✅ dla F-0 i F-M; aktualizacja stacku, ryzyk i promptów |
| 1.0 | 2026-06-12 | wersja pierwotna (migracja PySide6 + plan F1/F2/F3+/F7/F8/F10/F11) |

**Status realizacji:** F-0 ✅ · F-M ✅ (wg standardu v1.0 — stąd F-S) · F-S → F-A → F-B → F-C → F-D → F-E → F-F → F-G → F-H

Plan rozwoju po wydaniu v1.0. Obejmuje wykonaną migrację GUI na **PySide6** oraz funkcje z `FEATURES.md`: **F1** (i18n), **F2** (EpubCheck), **F3** (edytor — **rozszerzony o inspektor reguł CSS z podglądem na żywo**), **F7** (MOBI→EPUB), **F8** (statystyki), **F10** (TOC), **F11** (presety CSS).

Dokument uzupełnia `ROADMAP.md`, `CLAUDE.md` i `GUI_STANDARD.md` **v2.0** (zasady bez zmian: pliki < 500 linii, mypy --strict, coverage ≥ 70%, conventional commits, squash merge, core nie importuje gui; paleta + **stany pochodne** + wzorce układu ze standardu §5–6). Prompty: `PROMPTS_FEATURES_v1.1.md`.

---

## 0. Kolejność realizacji i zależności

```
F-M ✅ (migracja GUI → PySide6, wykonana wg standardu v1.0)
F-S (zgodność ze standardem v2.0: theme.py, platformdirs, DWM, build) ─► fundament wyglądu
F-A (F1 i18n) ──────────────────► wszystkie nowe stringi od razu przez _()
F-B (F11 presety CSS) ──┐
F-C (F3 edytor core) ───┼──► F-D (F3+ inspektor CSS live preview, QTextDocument)
                        │         │
F-C ────────────────────┴──► F-E (F2 EpubCheck — klikalne błędy skaczą do edytora)
F-C ─────────────────────────► F-F (F10 TOC — QTreeWidget z natywnym drag&drop)
F-G (F7 MOBI→EPUB)  — niezależny
F-H (F8 statystyki) — niezależny
```

| Etap | Zakres | Gałąź | Estymacja | Status / zależy od |
|---|---|---|---|---|
| F-0 | dokumenty planu w repo | `docs/features-v1.1-plan` | 0,5 h | ✅ |
| F-M | migracja gui/ na PySide6 (parytet 1:1) | `refactor/gui-pyside6` | 10–14 h | ✅ |
| **F-S** | **zgodność z GUI_STANDARD v2.0** (theme.py, platformdirs, config-debounce, DWM/dialogi, build/CI) | `refactor/gui-standard-v2` | **4–6 h** | po F-M |
| F-A | F1 — i18n (gettext) | `feature/f1-i18n` | 5–7 h | F-S |
| F-B | F11 — presety CSS | `feature/f11-css-presets` | 4–5 h | F-A |
| F-C | F3 — edytor (core) | `feature/f3-editor-core` | 7–9 h | F-A |
| F-D | F3+ — inspektor CSS live | `feature/f3-css-inspector` | 7–9 h | F-C |
| F-E | F2 — EpubCheck | `feature/f2-epubcheck` | 6–8 h | F-C |
| F-F | F10 — TOC | `feature/f10-toc` | 8–10 h | F-C |
| F-G | F7 — MOBI→EPUB | `feature/f7-mobi-to-epub` | 3–4 h | F-S |
| F-H | F8 — statystyki | `feature/f8-stats` | 6–8 h | F-A |

Uzasadnienie wstawienia F-S **przed** funkcjami: (1) standard v2.0 usuwa qdarktheme — im dłużej kod na nim wisi, tym więcej miejsc do poprawy później; (2) nowe zakładki (F-C…F-H) mają od razu korzystać z ról i **stanów** własnego `theme.py` (highlightery, kolory severity, fokus); (3) zmiana ścieżki configu (platformdirs) dotyka miejsc, na których budują F-B (presety użytkownika) i F-E (ścieżka jara) — lepiej ustalić ją raz, przed nimi.

---

## 1. Decyzje architektoniczne (globalne)

### 1.1. Stack GUI po F-S (zgodnie z GUI_STANDARD v2.0 §4)

| Element | Wybór |
|---|---|
| Framework | PySide6 ≥ 6.8, < 6.9 (LGPL — zgodne z MIT) |
| Motyw | **własny `gui/theme.py`** wg kontraktu standardu §4: `app.setStyle("Fusion")` **przed** `setPalette()`; QPalette = baza kolorów (paleta §5 + stany pochodne §5), QSS = wyłącznie akcenty (radius 4–8 px, hover/pressed, focus `accent`, QToolTip); **żadnej zewnętrznej biblioteki motywów** — `pyqtdarktheme-fork` wylatuje |
| Auto-motyw | `QGuiApplication.styleHints().colorScheme()`; `Unknown` → dark; sygnał `colorSchemeChanged` podłączony **tylko w trybie auto** |
| Kontrast (WCAG) | w jasnym motywie tekst/linki akcentowe = `accent2 #0F7C5B` (accent `#5DCAA5`/`#1D9E75` tylko wypełnienia/ikony/ramki) |
| Pasek tytułu | DWM przez `ctypes` **tylko gdy motyw aplikacji ≠ motyw systemu** (Qt 6.5+ sam podąża za systemem); `winId()` w `showEvent`; re-wymuszenie w `changeEvent(ActivationChange)` tylko w trybie wymuszonym |
| Dialogi plików | natywne; `DontUseNativeDialog` **tylko przy rozjeździe** (app dark + system light) — koszt: brak Szybkiego dostępu |
| Config | `platformdirs.user_config_dir("epubforge", appauthor=False, roaming=True)` — daje **dokładnie dotychczasowe ścieżki** (`%APPDATA%\epubforge`, `~/.config/epubforge`), więc dev/CLI bez migracji; zmiana zachowania tylko dla **frozen exe**: portable przez marker `portable.flag` obok exe, bez markera → platformdirs (+ jednorazowa kopia starego configu spod exe); zapis atomowy; **zapis przy zmianie z debounce ~1 s**, nie tylko przy zamknięciu |
| D&D | natywny Qt |
| Wątki | QThread + sygnały (Worker/log_view z F-M) |
| Testy GUI | pytest-qt + `QT_QPA_PLATFORM=offscreen` |
| Typografia/kształty | rozmiary fontów w **pt** (nie px), hinty min. 8 pt, ramki **1 px** kolorem `border` |

Zależności: `[gui] = PySide6>=6.8,<6.9` (bez pyqtdarktheme-fork po F-S); core += `platformdirs` (mały, czysty, bez Qt). Dev: `pytest-qt`, `babel` (od F-A).

> **theme.py a gui-kit:** standard notuje „pierwsza implementacja theme.py powstaje w pdf2md (G1) i trafia do gui-kit". Reguła praktyczna dla F-S: **jeśli theme.py z pdf2md już istnieje — wklejasz go jako punkt startowy i tylko adaptujesz; jeśli nie — EpubForge tworzy pierwszą implementację wg kontraktu §4 i to ona zasila gui-kit** (potem pdf2md ją przejmuje). Decyzję, który wariant zachodzi, podejmujesz przed wklejeniem promptu F-S.

### 1.2. Nowe moduły — mapa docelowa

```
src/epubforge/
├── i18n.py                      ← F1: gettext wrapper, _(), ngettext
├── locale/{pl,en,de}/LC_MESSAGES/epubforge.{po,mo}
├── validators/epubcheck.py      ← F2
├── toc/{model,reader,generator,writer,repair}.py   ← F10
├── stats.py + stats_stopwords/  ← F8
├── fixers/css_presets.py + presets/                 ← F11
├── fixers/css_rules.py          ← F3+: parse_rules/replace_rule/spany (czysta logika)
├── converters/{to_epub.py, kindle_drm.py}           ← F7
├── cli/{check,toc,stats,presets}.py
└── gui/                         ← PySide6 (po F-M), motyw własny (po F-S)
    ├── app.py                   ← MainWindow + open_in_editor (kontrakt F-C)
    ├── theme.py                 ← F-S: Fusion + QPalette + QSS, role i STANY z §5
    ├── window_theme.py          ← F-S: DWM tylko przy motywie ≠ system
    ├── workers.py  widgets/  tabs/   (jak po F-M)
    │   widgets += code_editor, syntax_highlight (F-C), css_inspector (F-D)
    │   tabs    += editor (F-C), validator (F-E), toc (F-F), stats (F-H)
```

Zasada bez zmian: wszystko poza `gui/` — zero importów z gui i PySide6.

### 1.3. i18n — gettext, nie Qt Linguist

Bez zmian względem v1.0 planu: jeden system dla GUI **i** CLI, msgid = polski, tłumaczenia en/de wypełnia Claude Code, `.mo` w repo, `build/compile_locales.py`. Zmiana języka wymaga restartu (komunikat).

### 1.4. PyInstaller / build — skutki (standard v2.0 §9)

- **`upx=False` w .spec** — UPX uszkadza DLL-e Qt.
- **Preferowana dystrybucja Qt: `--onedir` + Inno Setup**; portable `--onefile` zostaje **świadomie** (wolny start przez rozpakowanie ~150 MB do temp + ryzyko false-positives AV) — adnotacja w README przy linku portable.
- Excludes zbędnych modułów Qt (z F-M) zostają; datas: locale (F-A), presets (F-B), stopwords (F-H), assets.
- Drzewo licencji czyste (MIT/LGPL/BSD) → binarki PyInstaller OK (checklista §10 standardu).
- `build/check_build_env.py`: **usunąć import qdarktheme** (F-S), sprawdzać zasoby per etap.

### 1.5. CI (standard v2.0 §9)

W `test.yml` zweryfikować/uzupełnić: `concurrency: group: ${{ github.ref }}, cancel-in-progress: true` oraz `paths-ignore: ['**.md', 'docs/**']` dla jobów testowych (część z tego była już wdrożona przy wcześniejszej optymalizacji minut — prompt F-S każe sprawdzić i dopiąć braki). Ciężki build Windows tylko przy tagu. GUI testowane offscreen (po F-M). Zero nowych workflow.

---

## 2. Etap F-S — zgodność z GUI_STANDARD v2.0 *(naprawczy po F-M)*

**Cel:** doprowadzenie wykonanej migracji do litery standardu v2.0. Sześć obszarów:

1. **Własny `theme.py` (zamiast qdarktheme).** Kontrakt §4 standardu:
   - `apply(app, mode)` wymusza `app.setStyle("Fusion")` **przed** `setPalette()`;
   - dwie palety z §5 (dark/light) + **stany pochodne** z tabeli §5: `Highlight=selection_bg (accent2)`, `HighlightedText=#ffffff`, grupa `Disabled` (fg→disabled_fg, bg→disabled_bg), `PlaceholderText=fg3`, hover/pressed/focus_border w QSS;
   - QSS generowany z palety: wyłącznie akcenty — border-radius 4–8 px, ramki 1 px `border`, hover/pressed na przyciskach/listach, focus ramka `accent`, stylizacja QToolTip; **zero dublowania kolorów bazowych** między QPalette a QSS;
   - WCAG: w jasnym motywie kolory tekstowe akcentu = `accent2 #0F7C5B`;
   - auto: `styleHints().colorScheme()` (`Unknown`→dark), `colorSchemeChanged` podłączany tylko w auto, odłączany przy wymuszeniu;
   - po zmianie: `unpolish/polish` po `app.allWidgets()`;
   - publiczna dataclass `Theme` (role + stany) dla customowych widgetów (highlightery F-C, severity F-E, drzewo F-F) — **hexy żyją wyłącznie w theme.py**;
   - usunięcie `pyqtdarktheme-fork` z pyproject i całego kodu z `import qdarktheme`.
2. **`window_theme.py` — niuans Qt 6.5+:** wymuszanie DWM **tylko** gdy efektywny motyw aplikacji ≠ motyw systemu; w zgodzie motywów nic nie ruszamy (Qt sam). `changeEvent(ActivationChange)` ponawia tylko w trybie wymuszonym.
3. **Dialogi plików:** helper w gui (np. `file_dialogs.py` lub metoda ThemeManagera) decydujący o `DontUseNativeDialog` wyłącznie przy rozjeździe app-dark/system-light; wszystkie wywołania QFileDialog przez ten helper.
4. **Config wg §8:** `core/config.py` → `platformdirs.user_config_dir("epubforge", appauthor=False, roaming=True)`. Dobór parametrów jest istotny: ta sygnatura odwzorowuje **dokładnie obecne ścieżki** (`%APPDATA%\epubforge` na Windows, `~/.config/epubforge` na Linux), więc wersja deweloperska/CLI nie wymaga żadnej migracji; gołe `user_config_dir("EpubForge")` dałoby `%LOCALAPPDATA%\EpubForge\EpubForge` i wymusiło przeprowadzkę configów. Zmiana zachowania dotyczy wyłącznie **frozen exe** (dotąd: zawsze obok exe — utajony bug przy instalacji do Program Files): od teraz obok exe **tylko z markerem** `portable.flag` (build portable tworzy go w pakiecie); bez markera frozen używa platformdirs, z jednorazową **kopią** starego `config.json` spod exe (oryginał zostaje). Zapis atomowy zostaje; **`mark_dirty()`/`flush()`** w core + debounce ~1 s po stronie GUI (QTimer) i natychmiastowy flush w CLI/przy zamknięciu. Jedna funkcja `config_dir()` — od niej liczą się katalogi pochodne (presety F-B, jar F-E).
5. **Audyt typografii/kształtów:** rozmiary fontów w pt, hinty ≥ 8 pt, ramki 1 px, „Checkbox, nie switch" (nazewnictwo komponentu w gui-kit).
6. **Build/CI:** `upx=False`; README: rekomendacja instalatora (onedir) z adnotacją o wolnym starcie portable; `check_build_env.py` bez qdarktheme; weryfikacja `concurrency`/`paths-ignore` w test.yml; aktualizacja `GUI_STANDARD.md` w repo do v2.0 oraz pułapek w `CLAUDE.md`.

**Testy:** apply("dark")/apply("light") ustawiają oczekiwane role QPalette (Window=bg, Base=bg3, Highlight=accent2, Disabled.WindowText=disabled_fg, PlaceholderText=fg3) i styl Fusion; auto z mockiem colorScheme (Dark/Light/Unknown→dark); zmiana motywu nie zostawia QSS-owych kolorów bazowych (sprawdzenie, że styleSheet nie zawiera hexów bg/fg); config: ścieżka z platformdirs (monkeypatch), migracja stary→nowy, marker portable, debounce (mark_dirty nie pisze od razu, flush pisze, dwa mark_dirty = jeden zapis po flushu); helper dialogów zwraca właściwe opcje dla 4 kombinacji motywów.

**Twoje zadania (człowiek):**
1. Przed promptem: sprawdź, czy pdf2md ma już `theme.py` (etap G1) — jeśli tak, przygotuj plik do wklejenia; wpisz w prompt wariant A (adaptacja) lub B (pierwsza implementacja).
2. Po merge: przeklik obu motywów + **auto** (przełącz motyw Windows w trakcie działania aplikacji — pasek tytułu i paleta mają nadążyć); sprawdź dialogi plików w kombinacji app-dark/system-light.
3. Weryfikacja configu: w trybie dev sprawdź, że ścieżka się **nie** zmieniła (`%APPDATA%\epubforge\config.json` — motyw/ostatnie katalogi bez przerwy); w exe instalowanym sprawdź, że config wylądował w %APPDATA% i przejął ustawienia spod starego exe; w portable — że marker trzyma config obok exe.
4. `build\build.bat` → smoke obu wariantów; potwierdź `upx=False` nie zepsuł niczego i porównaj czas startu portable vs instalator (do adnotacji w README).
5. Jeśli to EpubForge tworzy pierwszą implementację theme.py — po merge skopiuj ją do notatek gui-kit / pdf2md.

---

## 3. Projekty szczegółowe funkcji

*(GUI — PySide6 z motywem z F-S; kolory wyłącznie przez role/stany `Theme`; stringi przez `_()` od F-A.)*

### F-A · F1 — Wielojęzyczność (i18n)

**Projekt:** `src/epubforge/i18n.py` (`init_i18n`, `_`, `ngettext` — PL: 3 formy mnogie, `detect_system_language` przez `QLocale.system().name()` z fallbackiem `locale` — moduł musi działać bez PySide6, `available_languages`, localedir odporny na `sys._MEIPASS`). Refactor: wszystkie stringi użytkownika w `gui/` i `cli/` przez `_()` (tłumaczone w momencie budowy widżetu, nie w stałych modułowych); docstringi/logi/wyjątki wewnętrzne — nie. Babel: extract → pot, init en/de, **tłumaczenia wypełnia Claude Code**, `build/compile_locales.py`, `.mo` w repo, wywołanie w build.bat. GUI: w pasku górnym obok „Motyw" QToolButton „Język" (Auto/Polski/English/Deutsch), zapis `config["language"]` (przez mark_dirty z F-S), QMessageBox o restarcie.

**Testy:** `_()` pod wymuszonym en, fallback, ngettext 1/2/5 PL, spójność .pot↔.po (bez pustych/fuzzy), aktualność .mo, działa bez PySide6, smoke pytest-qt z `language=en`.

**Twoje zadania:** przegląd EN/DE (kalki, długość etykiet DE), test exe z locale, akceptacja domyślnego „auto".

---

### F-B · F11 — Biblioteka presetów CSS

**Projekt (logika niezależna od GUI):** `CssPreset` (frozen), `list_presets(user_dir=None)`, `get_preset`, `apply_preset(epub, preset, mode="append"|"replace")`, `import_user_preset`. `append` (domyślny): zapis `{opf_dir}/styles/epubforge-preset.css`, `<item>` w manifeście OPF, `<link>` jako **ostatnie** dziecko `<head>` każdego pliku spine (XHTML ma namespace; bazy ścieżek manifestu i linków są RÓŻNE — posixpath.relpath); idempotencja = podmiana zawartości arkusza. `replace`: usunięcie istniejących arkuszy (manifest+linki+pliki) → append. Wbudowane (`fixers/presets/` + `presets.json` z nazwami/opisami pl/en/de): `reader-friendly`, `print-like`, `dark-oled` (komentarz: e-ink nadpisuje kolory), `manga-rtl` (komentarz: ograniczone wsparcie czytników). Presety użytkownika: `<config(platformdirs)>/presets/*.css`, import walidowany tinycss2.

CLI: `epubforge presets list`, `epubforge fix --preset ID [--preset-mode replace]`. GUI (FixerTab): Section „Preset CSS" — QComboBox (nazwa — opis), QRadioButton append/replace, „Importuj własny…", QCheckBox włączający krok w pipeline. Po F-D dojdzie „Podgląd".

**Testy:** apply/idempotencja/replace na fixture, link ostatni w head każdego spine, EPUB po save zdrowy (mimetype pierwszy, ZIP_STORED), import waliduje/odrzuca, CLI.

**Twoje zadania:** ocena presetów na czytniku (dark-oled na Kindle!), finalna typografia, ewentualny własny preset.

---

### F-C · F3 — Edytor wewnętrzny (core)

**Cel:** przegląd + szybka edycja HTML/CSS w EPUB; quick fix, nie Sigil.

**Projekt:**
- `widgets/syntax_highlight.py`: `XmlHighlighter`/`CssHighlighter` (QSyntaxHighlighter; reguły QRegularExpression + QTextCharFormat; komentarze wieloliniowe przez block state; kolory z ról/stanów `Theme`, rehighlight na sygnał zmiany motywu; logika dopasowań w funkcjach czystych, testowalna bez Qt).
- `widgets/code_editor.py`: QPlainTextEdit + line number area (kanoniczny wzorzec Qt) + pasek wyszukiwania (Ctrl+F, F3/Shift+F3, `setExtraSelections`, licznik „3/17") + status wiersz:kolumna. API: `load(text, profile)`, `get_text()`, `goto_line(n)`, `read_only`, sygnał `modified_changed`. Undo/redo natywne.
- `tabs/editor.py` — zakładka „Edytor": toolbar (Otwórz EPUB / ścieżka / **Zapisz EPUB** / toggle „Tryb edycji" — **domyślnie wyłączony**); QSplitter: lewo QTreeWidget (grupy Tekst/Style/Obrazy/Fonty/Inne wg media-type z manifestu, fallback po rozszerzeniu dla `list_files()`; `*` przy zmodyfikowanych), prawo QStackedWidget: CodeEditor / podgląd obrazu (QLabel+QPixmap, KeepAspectRatio) / panel info dla binariów. Stan: jeden `Epub` na życie zakładki + `_dirty: dict[str, str]`; zmiana pliku przy zmianach → Zapisz/Porzuć/Anuluj; Ctrl+S: dla XHTML/OPF próba lxml → błąd ⇒ „Zapisać mimo to?"; zapis = `write_file`; „Zapisz EPUB" = `save()` (backup .bak); dekodowanie utf-8/replace, znaki zastępcze ⇒ read-only pliku; `closeEvent` pyta o niezapisane.
- **Kontrakt:** `MainWindow.open_in_editor(epub_path, internal_path=None, line=None)` — konsumenci F-E, F-D.

**Testy:** czyste (klasyfikacja, offset↔linia/kolumna); pytest-qt: roundtrip z polskimi znakami, goto_line, read_only, search, pełny flow edycji→save→reopen, plik nie-UTF8, open_in_editor, highlighter nadaje formaty.

**Twoje zadania:** UX na dużej książce (50+ MB), akceptacja „read-only domyślnie", skróty.

---

### F-D · F3+ — Inspektor reguł CSS z podglądem na żywo *(rozszerzenie spoza FEATURES.md)*

**Cel:** przy otwartym `.css` — lista reguł; każda z **podglądem przykładowego tekstu sformatowanego zgodnie z regułą**; edycja reguły aktualizuje podgląd **na żywo**; „Zastosuj" wpisuje zmianę do arkusza.

**Warstwa logiki — `fixers/css_rules.py`** (czyste funkcje, zero Qt):
- `parse_rules(source) -> list[CssRuleInfo(selector, declarations, span, media, previewable, parse_errors)]` — **span = offsety znakowe `[start, end)`** z `source_line/source_column` tokenów tinycss2 (1-indeksowane!) + tabeli offsetów linii; koniec = `}` wyznaczana od pozycji końca ostatniego tokenu content (odporność na `}` w stringach/komentarzach); `@media` rekurencyjnie; `@font-face/@page/@import` → previewable=False.
- `replace_rule(source, span, new_text)` — **jedyna** modyfikacja źródła (zero re-serializacji — formatowanie użytkownika nietykalne).
- `parse_single_rule(text)`; `declarations_to_preview(decls) -> (inline_style, unsupported)` — whitelist podzbioru CSS silnika rich text Qt („Supported HTML Subset"): font-family/-size/-weight/-style, color, background-color, text-align (**justify działa**), text-indent, line-height, margin-*, padding-*, text-decoration, text-transform; jednostki px/pt/em/% normalizowane; reszta → lista nieobsługiwanych. Celowo **inline style** zamiast selektorów w setDefaultStyleSheet — omijamy ograniczenia dopasowania selektorów Qt.
- `sample_for_selector(selector)` — h1..h6 → „Rozdział pierwszy"; p/body/klasy → akapit **z polskimi diakrytykami** („Zażółć gęślą jaźń…"); blockquote → cytat; code/pre → kod; inne → akapit. `build_preview_html(rule)` składa dokument (escapowanie!).

**Widget — `gui/widgets/css_inspector.py`** (`CssInspector(QWidget)`): konstruktor `get_source`, `apply_replacement | None` (None = read-only, Zastosuj ukryty), `theme`. QSplitter pionowy: (1) QTreeWidget reguł (Selektor | skrót deklaracji | @media; nie-previewable wyszarzone stanem disabled_fg); (2) edytor reguły = CodeEditor css ~8 linii z `source[span]`; (3) podgląd QTextEdit read-only na „papierowej" białej karcie (1 px ramka `border`) — tło **niezależne od motywu aplikacji**, pod spodem „Nieobsługiwane w podglądzie: …" + stała adnotacja „Podgląd przybliżony — czytnik może różnić się w szczegółach"; (4) „Zastosuj do arkusza" / „Przywróć". **Live:** textChanged → QTimer-debounce 300 ms → parse_single_rule → OK: `setHtml(build_preview_html)`; błąd: ramka `red` + komunikat, podgląd na ostatnim poprawnym. **Zastosuj:** `apply_replacement(start, end, text)` → refresh (spany przeliczone, zaznaczenie po selektorze). Refresh także po edycji w głównym edytorze (debounce 400 ms). Integracja w EditorTab: panel dla text/css **domyślnie otwarty** (toggle); apply_replacement przez **jedną operację QTextCursor** głównego edytora ⇒ undo cofa całość, plik dostaje `*`. Synergia F11: „Podgląd…" presetu = QDialog z CssInspector(read-only).

**Testy:** spany (prosta/wieloselektorowa/komentarze/`content:"}"`/`url("a}b.png")`/@media/@font-face), replace_rule bajt-w-bajt poza spanem, declarations_to_preview per właściwość + jednostki + kolory + justify przechodzi + letter-spacing→unsupported + !important, sample_for_selector, build_preview_html escapuje; pytest-qt: panel widoczny, edycja red→blue po debounce zmienia podgląd, Zastosuj trafia do edytora i undo cofa.

**Twoje zadania:** przeklik na arkuszach z prawdziwych książek (Calibre — tysiące reguł: wydajność listy), ocena wierności podglądu, akceptacja auto-otwierania panelu.

---

### F-E · F2 — Walidacja przez EpubCheck

**Projekt:** detekcja w `core/detection.py` wg wzorca Tooli: `Tools.java()` (PATH/JAVA_HOME/Temurin; wersja z `java -version` — **stderr**; wymagane ≥ 11) i `Tools.epubcheck()` (jar: config override `tools.epubcheck_jar` → glob ProgramFiles/`~` → `<config(platformdirs)>/epubcheck/epubcheck.jar` → obok exe; wersja z `META-INF/MANIFEST.MF` bez uruchamiania javy). `validators/epubcheck.py`: `ValidationMessage/ValidationReport(counts())`, `run_epubcheck` — `java -jar … --json tmp.json` (tempfile, CREATE_NO_WINDOW, utf-8/replace, timeout); exit≠0 z poprawnym JSON = raport `valid=False`; brak JSON/timeout = `EpubforgeError`; parser defensywny, normalizacja ścieżek do wewnętrznych. CLI `epubforge check` (exit 0/1/2). GUI `tabs/validator.py`: FileList + Worker, podsumowanie z **ngettext**, filtry severity, QTreeWidget (kolory `red`/`amber`/`fg2` z Theme; dane w `Qt.UserRole`), **dwuklik → `open_in_editor(epub, internal_path, line)`**, eksport JSON/HTML; brak narzędzi ⇒ panel pomocy (Temurin 17+, epubcheck z W3C GitHub) + „Wskaż epubcheck.jar…" (config → re-detekcja). Bez auto-pobierania jara w v1.

**Testy:** zero realnej javy — fixture'y JSON (ok/errors/broken), parser+normalizacja+counts, mock subprocess (ok/exit≠0/timeout/brak pliku), parser wersji javy ze stderr („17.0.9" ok, „1.8.0_391" → unavailable), MANIFEST.MF z mini-jara, CLI exit codes, pytest-qt: tabela + dwuklik woła open_in_editor (mock).

**Twoje zadania:** Temurin JRE 17+ (Windows i WSL), epubcheck-5.x z W3C GitHub, wskazanie jara; testy na prawdziwych i celowo zepsutych EPUB-ach (dwuklik trafia w linię); decyzja o auto-walidacji po zapisie (rekomendacja: tylko przycisk).

---

### F-F · F10 — Generator i edytor spisu treści

**Projekt:** pakiet `toc/`: `model.py` (`TocEntry` + **czysta** `move_entry(entries, src, dst, mode before/after/into)` z zakazem przeniesienia do potomka — model pod D&D), `reader.py` (nav.xhtml z fallbackiem ncx, zwraca źródło), `generator.py` (spine w kolejności, lxml recover, h1..h{max_level}, drzewo wg poziomów z podciąganiem osieroconych, tytuł = znormalizowany itertext, wstrzykiwanie brakujących `id="efh-NNNN"` z idempotencją i zachowaniem deklaracji XML + **doctype**, pierwszy nagłówek pliku bez fragmentu, pliki bez nagłówków pomijane), `writer.py` (nav: podmiana **tylko** `<nav epub:type="toc">` lub nowy dokument + manifest `properties="nav"`, spine nietknięty; ncx: pełna regeneracja + manifest + `spine@toc`; href względne — RÓŻNE bazy, posixpath.relpath), `repair.py` (`validate_toc` — martwy href / brak fragmentu, cache id per plik; `repair_toc` usuwa i podciąga dzieci). CLI `epubforge toc --show | --generate [--max-level 3] | --repair [--dry-run]`. GUI `tabs/toc.py`: QTreeWidget (Tytuł | Cel; problemy kolorem `red` + tooltip), toolbar (Generuj/Napraw/Dodaj/Usuń/⬆⬇⬅➡/Zapisz), edycja tytułu przez `Qt.ItemIsEditable` na kolumnie tytułu, **D&D: `InternalMove`** + synchronizacja modelu w dropEvent (dropIndicatorPosition → before/after/into → `move_entry` → przebudowa widoku; `blockSignals` podczas przebudowy), wskaźnik niezapisanych zmian.

**Testy:** generator na rozbudowanej fixture (poziomy, osierocony h3, `<em>` w nagłówku, polskie znaki, idempotencja id, plik bez nagłówków), writer→reader roundtrip (nav i ncx), manifest/spine, EPUB zdrowy po save, repair, move_entry wszystkie tryby + zakaz cyklu, CLI, pytest-qt (wczytanie/generacja/edycja tytułu/zapis; przeniesienie przez wydzielony handler (src,dst,tryb)).

**Twoje zadania:** test na książce z usuniętym nav, płaskiej z Calibre i głębokiej; **weryfikacja TOC na Kindle po konwersji KFX**; domyślny max_level (rekomendacja: 3).

---

### F-G · F7 — Konwersja MOBI → EPUB

**Projekt:** wyłącznie **Calibre**; KindleUnpack pominięty (**GPL/copyleft**). Routing w `converters/to_epub.py`: suffix ∈ {`.mobi`,`.azw3`,`.azw`,`.prc`} ⇒ wymuś Calibre (engine="pandoc" jawnie → czytelny błąd). **DRM:** `converters/kindle_drm.py` (~60–80 linii czystego `struct`): PalmDB → rekord 0 → magic „MOBI" → encryption type (0 brak / 1–2 DRM); DRM ⇒ przyjazny `ConversionError` **przed** Calibre; dodatkowo mapowanie „DRM" ze stderr Calibre. CLI: `convert` działa od razu — aktualizacja help/README. GUI ConverterTab: filtry plików, wymuszenie silnika Calibre dla Kindle, DRM jako `QMessageBox.warning`.

**Testy:** syntetyczne nagłówki PalmDB (struct.pack; enc 0/1/2, plik 10-bajtowy, brak magic) — **żadnych prawdziwych mobi w repo**; routing z mockiem subprocess; pandoc → błąd; DRM=True ⇒ subprocess niewywołany; stderr „DRMError" → zmapowany.

**Twoje zadania:** lokalny legalny plik testowy (roundtrip własnego EPUB przez Calibre), ocena jakości (TOC, obrazy), nic do repo.

---

### F-H · F8 — Statystyki książki

**Projekt:** `stats.py`: `ChapterStats`, `BookStats(words, chars, chapters, estimated_pages, reading_time_min, language, language_source, top_words)`, `StatsOptions(250/200/50)`, `compute_stats`, `render_report_html`. Ekstrakcja: spine w kolejności, lxml recover, itertext bez script/style; tytuł = h1/h2/`<title>`. Tokenizacja `\w+` unicode, liczby odfiltrowane. Język: `langdetect` (extra `[stats]`, `DetectorFactory.seed=0`, próbka 10 k znaków) → fallback `metadata.language` → None (źródło zapisane). Stop-listy `stats_stopwords/{pl,en,de}.txt` (200–300 słów; PL przeglądasz ty). Raport HTML samowystarczalny (inline CSS w **jasnej palecie §5 z accent2 dla tekstu — nota WCAG**, `html.escape` na wszystkim z książki): metadane, karty, chmurka tagów (font-size log 12–40 px), tabela rozdziałów, wykres słupkowy **inline SVG** własną funkcją (≤60 słupków), stopka „Ctrl+P → PDF". CLI `epubforge stats`. GUI `tabs/stats.py`: PathEntry → Worker → karty + top-słowa + rozdziały + „Eksport HTML…"/„Otwórz raport"; adnotacja przy braku langdetect.

**Testy:** deterministyczne liczby na fixture, „Zażółć gęślą jaźń"=3 słowa, stop-lista, fallback języka (monkeypatch ImportError), top_words sort/remis, raport (tytuł, escapowanie `<b>złośliwy</b>`, liczba `<rect>` = rozdziały, brak „http"), CLI, smoke pytest-qt.

**Twoje zadania:** przegląd polskiej stop-listy, stałe (250/200 vs 220/180 dla PL), ocena raportu na ekranie i w druku, `pip install -e ".[dev,stats]"`.

---

## 4. Aktualizacje przekrojowe (każdy etap pamięta)

- **pyproject.toml:** F-S → `platformdirs` (core), **usunięcie pyqtdarktheme-fork**; F-A → `babel` (dev); F-H → extra `stats=["langdetect>=1.0.9"]`; dane pakietu (locale, presets, stopwords, assets) w wheel.
- **build/**: F-S (`upx=False`, bez qdarktheme w check_build_env), F-A (locale+compile_locales), F-B (presets), F-H (stopwords).
- **CI test.yml:** F-S weryfikuje `concurrency` + `paths-ignore`; offscreen z F-M zostaje.
- **README / docs / CHANGELOG:** per etap; F-S dodaje adnotację o portable vs instalator.
- **GUI_STANDARD.md w repo:** F-S podmienia na v2.0; **CLAUDE.md:** pułapki Qt zaktualizowane (Fusion przed setPalette; DWM tylko przy motywie ≠ system; QPalette vs QSS bez dublowania; upx=False).
- **Wersjonowanie (przypomnienie):** F-M+F-S → v2.0.0; dalej F-A..F-B → 2.1, F-C..F-D → 2.2, F-E → 2.3, F-F → 2.4, F-G..F-H → 2.5 (lub wedle twojej decyzji per merge).

## 5. Twoja lista zadań — zbiorczo

**Przed F-S:** status theme.py w pdf2md (wariant A/B do promptu); `git pull`, CI zielone.
**Rytuał per etap:** prompt → przegląd diff → lokalnie pytest/ruff/mypy → **przeklik GUI na Windows w obu motywach + auto** → push/PR/CI → squash merge → co 2–3 etapy build + smoke exe.
**Specyficzne:** F-S: test auto-motywu w locie, migracja configu, czas startu portable vs instalator; F-A: przegląd EN/DE; F-E: Java+epubcheck.jar; F-C/F-D: UX na dużych książkach; F-F: TOC na Kindle po KFX; F-G: plik testowy poza repo; F-H: polska stop-lista; F-B: presety na czytniku.
**Po wszystkim:** zrzuty README, release notes + tag.

## 6. Ryzyka i miny

| Ryzyko | Mitygacja |
|---|---|
| theme.py pisany równolegle w EpubForge i pdf2md → rozjazd | reguła z §1.1: istniejący wygrywa, drugi adaptuje; docelowo gui-kit |
| Fusion zmienia metryki widgetów względem stylu natywnego | przeklik po F-S; ewentualne korekty paddingów w QSS, nie w tabach |
| Dublowanie kolorów QPalette/QSS → plamy przy zmianie motywu | kontrakt §4 standardu (QSS = tylko akcenty) + test na hexy bazowe w QSS |
| DWM wymuszany niepotrzebnie (Qt 6.5+) | wymuszenie tylko przy motywie ≠ system; test 4 kombinacji |
| Zmiana ścieżki configu gubi ustawienia | parametry platformdirs odwzorowują obecne ścieżki (zero migracji dev/CLI); frozen: kopia spod exe + test regresji ścieżek + twoja weryfikacja ręczna |
| Crash = utrata configu | zapis z debounce ~1 s (mark_dirty/flush), nie tylko przy zamknięciu |
| Kontrast akcentu w jasnym motywie | nota WCAG: tekst/linki = accent2 #0F7C5B (theme.py + raport F-H) |
| UPX psuje DLL-e Qt; wolny start onefile | upx=False; rekomendacja instalatora w README |
| Podgląd CSS ≠ czytnik (F3+) | QTextDocument + jawna adnotacja + lista nieobsługiwanych |
| Podmiana reguły psuje arkusz (F3+) | spany z tokenów tinycss2, testy edge-case, jedna operacja QTextCursor ⇒ undo |
| EpubCheck JSON zmienia format / `java -version` na stderr | parser defensywny + fixture'y; czytamy stderr |
| Wstrzykiwanie id psuje XHTML (F10) | lxml z doctype, idempotencja, roundtrip, backup .bak |
| PL pluralizacja (F1) | ngettext, nplurals=3, testy 1/2/5 |
| GPL/copyleft (F7) | bez kindleunpack; Calibre tylko subprocess; PySide6 = LGPL |
| Minuty GitHub Actions | offscreen, concurrency+paths-ignore (F-S weryfikuje), mocki subprocess |
| Wątki Qt | GUI tylko z głównego wątku; workery przez sygnały |
