# 💬 EpubForge — Prompty: migracja Qt + Features v1.1+ (F1, F2, F3+, F7, F8, F10, F11)

Gotowe do wklejenia prompty dla etapów z `ROADMAP_FEATURES_v1.1.md`. Kolejność: F-0 → **F-M** → F-A → F-B → F-C → F-D → F-E → F-F → F-G → F-H. Skopiuj cały blok, wklej do Claude Code, czekaj. **Przed każdym etapem: jesteś na `main` po `git pull`.**

---

## 🧱 Etap F-0 — Dokumentacja planu (5 min)

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md.

ZADANIE: dodanie dokumentów planistycznych do repo.

1. Utwórz gałąź: docs/features-v1.1-plan
2. Dodaj do repo pliki: ROADMAP_FEATURES_v1.1.md, PROMPTS_FEATURES_v1.1.md oraz GUI_STANDARD.md (wkleję/wskażę).
3. W FEATURES.md przy F1, F2, F3, F7, F8, F10, F11 dopisz: "→ zaplanowane, zob. ROADMAP_FEATURES_v1.1.md".
4. W CLAUDE.md w sekcji "Pliki, które ZAWSZE czytaj" dopisz GUI_STANDARD.md i ROADMAP_FEATURES_v1.1.md.
5. Commit: "docs: add v1.1 feature plan, coding prompts and GUI standard"
6. Zaproponuj push i PR. NIE pushuj automatycznie.
```

---

## 🖼️ Etap F-M — Migracja GUI: tkinter → PySide6

> Przed wklejeniem uzupełnij w miejscu `<<<WERSJE>>>` wersje PySide6 i pyqtdarktheme z pyproject IcoForge (+ ewentualne znane obejścia stamtąd).

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, GUI_STANDARD.md (CAŁY — sekcje 4, 5, 6, 7 są wiążące) oraz ROADMAP_FEATURES_v1.1.md sekcja 2 (F-M). Przeczytaj AKTUALNY stan WSZYSTKICH plików w src/epubforge/gui/ oraz core/config.py, core/detection.py — port ma używać prawdziwych sygnatur core, bez mocków i duplikatów.

ZADANIE: migracja całej warstwy gui/ z tkinter na PySide6 z parytetem funkcjonalnym 1:1 względem v1.0. core/, converters/, fixers/, cli/ NIE DOTYKAMY (poza pyproject). Wygląd wg GUI_STANDARD §5-6, paleta i akcent #5DCAA5/#1D9E75.

Wersje (z IcoForge): <<<WERSJE>>>

Wykonaj kolejno:

1. main + pull. Gałąź: refactor/gui-pyside6

2. pyproject.toml:
   - [gui]: PySide6, pyqtdarktheme (wersje jw.); USUŃ tkinterdnd2 i darkdetect
   - [dev]: dodaj pytest-qt
   - mypy: PySide6 ma stuby — usuń zbędne overrides tkinterdnd2/darkdetect

3. gui/theme.py — ThemeManager:
   - dataclass Theme z rolami palety DOKŁADNIE wg GUI_STANDARD §5 (bg, bg2, bg3, fg, fg2, fg3, accent, accent2, border, red, amber) — wartości ciemne i jasne ze standardu
   - przed PIERWSZĄ zmianą zapamiętaj app.style().objectName(), QPalette i styleSheet
   - dark / auto-w-trybie-dark: qdarktheme.setup_theme("dark", custom_colors={"primary": "#5DCAA5"})
   - light / auto-w-trybie-light: PRZYWRÓĆ zapamiętany natywny styl (NIE qdarktheme("light") — pułapka "wyprany light" z GUI_STANDARD §4) + minimalny stylesheet z akcentem
   - auto: detekcja systemu (mechanizm qdarktheme lub QStyleHints.colorScheme) + reakcja na zmianę w locie jeśli tania
   - po każdej zmianie: style.unpolish()/polish() na app.allWidgets()
   - API: ThemeManager(app, config) z .setting ("auto"/"light"/"dark"), .apply(setting), .theme -> Theme, sygnał theme_changed

4. gui/window_theme.py — ciemny pasek tytułu Windows wg GUI_STANDARD §4:
   - DwmSetWindowAttribute(20) na int(window.winId()); wołane z showEvent, NIE z __init__
   - Win10: WM_NCACTIVATE (0→1) + RedrawWindow(RDW_FRAME)
   - changeEvent na ActivationChange ponawia wymuszenie (pułapka: dialog odbiera focus → pasek jaśnieje)
   - na nie-Windows: no-op; całość w try/except z logger.warning

5. gui/workers.py — zastępuje streaming.py:
   - class Worker(QThread): przyjmuje callable; sygnały: line(str, str) [tekst, poziom ok/warn/err], finished(object), failed(str)
   - pomocnik run_subprocess_streaming(cmd, on_line, ...) z CREATE_NO_WINDOW, timeout, encoding="utf-8", errors="replace"
   - ŻELAZNA ZASADA: z wątku NIGDY nie dotykamy widgetów — tylko emit; podłączenia przez sygnały (auto queued connection)
   - widget logu: gui/widgets/log_view.py — QPlainTextEdit read-only, appendLine(text, level) z QTextCharFormat w kolorach ról Theme (fg/amber/red), maximumBlockCount żeby log nie puchł

6. gui/widgets/ — gui-kit wg GUI_STANDARD §7 (każdy plik mały, reużywalny):
   - path_entry.py: PathEntry(QWidget) = QLineEdit + QToolButton "…" (QFileDialog otwarty/zapis/katalog wg trybu), placeholder, sygnał path_changed; pamięta ostatni katalog przez przekazany config (GUI_STANDARD §8: domyślny katalog = katalog źródła, fallback ostatni użyty)
   - file_list.py: FileList(QWidget) = toolbar (Dodaj pliki / Dodaj folder / Usuń / Wyczyść) + QListWidget + licznik ("N plików"); natywny D&D: setAcceptDrops(True), dragEnterEvent akceptuje urls z pasującym rozszerzeniem, dropEvent dodaje (folder → rekurencyjnie po wzorcu); API jak dotychczasowy FileList (paths(), add_paths(), sygnał selection_changed) — sprawdź użycia w tabach i zachowaj kontrakt
   - section.py: Section = QGroupBox z tytułem (style spójne, padding 10-12 px wg §5)
   - about_panel.py: logo ładowane warunkowo z gui/assets (placeholder gdy brak), nazwa + __version__ (NIE hardcoded), linki GitHub/pomoc przez webbrowser.open, licencja
   - Toggle: zwykły QCheckBox (osobna klasa tylko jeśli taby wymagają wspólnego API)
   - Tooltipy: setToolTip wszędzie tam, gdzie stary kod miał Tooltip(...) — customowa klasa Tooltip ZNIKA
   - widgets/__init__.py: eksporty

7. gui/app.py — MainWindow(QMainWindow) + main():
   - main(): QApplication, load_config, detect_with_cache (jak dotąd), ThemeManager.apply z config, MainWindow, exec()
   - układ centralny wg GUI_STANDARD §6: górny pasek (QHBoxLayout: logo+QLabel "EpubForge" po lewej; po prawej QToolButton "Motyw" z QMenu auto/jasny/ciemny [QActionGroup, checkable] + QToolButton "ⓘ" otwierający About w QDialog) → QTabWidget (TYLKO zakładki robocze) → statusBar() z wykrytymi narzędziami (tekst jak dotąd)
   - geometria okna z/do config (restoreGeometry/saveGeometry przez QByteArray hex w configu albo prosty "WxH+X+Y" — wybierz jedno i udokumentuj), minsize 760x520
   - closeEvent: zapis configu (motyw, geometria)
   - obsługa błędów wg GUI_STANDARD §8: sys.excepthook → QMessageBox.critical + zapis tracebacku do error.txt obok configu (w trybie frozen obok exe)

8. Port zakładek 1:1 → gui/tabs/{metadata,converter,fixer,kfx}.py:
   - PRZED portem każdej zakładki przeczytaj jej obecny plik tkinter W CAŁOŚCI i wypisz listę funkcji do parytetu; potem implementuj w Qt
   - layouty: QFormLayout/QGridLayout w Section; długie operacje przez Worker + log_view + QProgressBar (nieokreślony tam, gdzie dziś brak postępu); przyciski akcji w stałym miejscu (§6)
   - QFileDialog: jeśli aktywny motyw ciemny → opcja DontUseNativeDialog (spójność — główny powód migracji); jasny → natywne
   - QMessageBox zamiast messagebox; walidacje i komunikaty zachowaj treściowo
   - tabs/__init__.py zaktualizuj
   - about.py przenieś do widgets/about_panel.py + QDialog w app.py (About to meta-funkcja, nie zakładka — §6)

9. Usuń martwe pliki tkinter: theme.py (stare wnętrze), window_theme.py (stare), streaming.py, widgets/{toggle,tooltip,...}.py wg tego co zastąpione. ZERO importów tkinter w repo po tym etapie (sprawdź grepem).

10. Testy — przepisz tests/gui/ na pytest-qt (qtbot):
    - conftest: fixture qapp; w CI działa offscreen
    - smoke MainWindow (buduje się, ma 4 zakładki, statusbar z tekstem)
    - ThemeManager: apply("dark") zmienia paletę aplikacji; apply("light") przywraca zapamiętany styl (porównaj objectName/palette z zapisanym)
    - PathEntry: ustawienie ścieżki emituje sygnał; FileList: add_paths aktualizuje licznik, Usuń/Wyczyść działają; D&D przez bezpośrednie wywołanie handlera dropEvent z spreparowanym QMimeData(urls)
    - Worker: callable wykonuje się, sygnały finished/failed emitowane (qtbot.waitSignal), z mockiem subprocess
    - po jednym teście konstrukcyjnym na każdą zakładkę + jeden test flow z mockiem (np. fixer: dodaj fixture sample.epub, odpal, czekaj na finished, sprawdź status)
    - test "zero tkinter": import wszystkich modułów gui nie ciągnie tkinter (sprawdź sys.modules)

11. CI .github/workflows/test.yml: usuń xvfb; dodaj env QT_QPA_PLATFORM: offscreen i apt-get install -y libegl1 (Ubuntu). Bez nowych jobów.

12. Build: przepisz .spec/argumenty — bez tkdnd; PyInstaller dla PySide6 (zwykle auto), DODAJ excludes: PySide6.QtWebEngineCore, QtWebEngineWidgets, Qt3D*, QtQuick*, QtQml, QtMultimedia*, QtCharts, QtDataVisualization (sprawdź, że aplikacja ich nie używa); datas: gui/assets; zaktualizuj build/check_build_env.py (import PySide6, qdarktheme; bez tkdnd).

13. Dokumentacja: README (sekcja GUI — usuń ostrzeżenie o jasnych natywnych dialogach, zaktualizuj wymagania), docs/user-guide.md, CHANGELOG ("Changed: GUI migrated from tkinter to PySide6..."), GUI_STANDARD.md — mapa projektów: EpubForge → Qt, CLAUDE.md — tabela stacku (tkinter→PySide6, tkinterdnd2/darkdetect out, pytest-qt in) i pułapki: usuń tkinterowe 6 i 8, dodaj Qt-owe z GUI_STANDARD §4.

14. pytest, ruff check . --fix, mypy src/ — zielone.
15. Commit: "refactor(gui)!: migrate GUI from tkinter to PySide6 per GUI standard"
16. Podsumuj parytet funkcjonalny jako checklistę (co było → gdzie jest teraz). Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- winId() dopiero w showEvent; int(winId()) do ctypes.
- Sygnały z QThread do GUI: nie wywołuj metod widgetów wprost z run().
- QFileDialog.getOpenFileNames zwraca (lista, filtr) — krotka.
- Trzymaj referencje do QAction/QMenu jako atrybuty (GC).
- Style: ŻADNYCH hardcoded hexów w tabach — wyłącznie role Theme (GUI_STANDARD §4).
- Pliki < 500 linii: app.py i większe taby pilnuj rozmiaru, wydzielaj widgety.
```

---

## 🌍 Etap F-A — F1: Wielojęzyczność (i18n)

```
Pracujemy nad EpubForge (GUI już w PySide6). Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcje 1.3 i F-A) i pyproject.toml.

ZADANIE: internacjonalizacja GUI i CLI przez gettext (NIE Qt Linguist — uzasadnienie w ROADMAP §1.3). Języki: pl (msgid = polski, obecne stringi), en, de.

1. main + pull. Gałąź: feature/f1-i18n

2. pyproject.toml: "babel>=2.14" do [dev]; dane src/epubforge/locale/** do wheel (hatchling).

3. src/epubforge/i18n.py:
   - init_i18n(language: str = "auto"), _(msgid), ngettext(s, p, n)
   - detect_system_language(): QLocale.system().name() jeśli PySide6 importowalne, fallback locale.getlocale(); mapuj na {"pl","en","de"}, default "pl" — ale moduł MUSI działać też bez PySide6 (CLI bez [gui]): import PySide6 w try/except wewnątrz funkcji
   - available_languages() — skan locale/
   - localedir: frozen → Path(sys._MEIPASS)/"epubforge"/"locale", inaczej Path(__file__).parent/"locale"
   - implementacja przez globalny translator ustawiany w init_i18n; _() czyta go w czasie wywołania (NIE binduj tłumaczenia w czasie importu)

4. Refactor stringów:
   - WSZYSTKIE stringi widoczne dla użytkownika w gui/ i cli/ (etykiety, tytuły zakładek, tooltips, QMessageBox, statusy, help argparse, printy CLI) przez _() — i tłumaczone W MOMENCIE budowy widgetu (po init_i18n), nie w stałych modułowych
   - NIE tłumacz: docstringów, logger.*, wyjątków wewnętrznych, nazw technicznych (EPUB, KFX, Calibre), wzorców filtrów plików
   - liczebniki ZAWSZE przez ngettext (PL: 3 formy — "1 plik / 2 pliki / 5 plików"); zero f-stringów wewnątrz _() — użyj _("...{n}...").format(n=n) (pybabel nie wyciąga f-stringów)
   - init_i18n() wywołaj na początku gui/app.py main() i cli/main.py main(), z config.get("language", "auto"), PRZED budową UI/parsera

5. Babel: babel.cfg ([python: src/epubforge/**.py]); pybabel extract → locale/epubforge.pot; init en i de; PRZETŁUMACZ samodzielnie wszystkie wpisy en.po i de.po (naturalny, zwięzły język UI; w DE pilnuj długości etykiet); nagłówek pl: Plural-Forms nplurals=3. Utwórz build/compile_locales.py (babel.messages, kompiluje wszystkie .po → .mo). Uruchom. .mo COMMITUJEMY. Wywołanie skryptu dopisz do build/build.bat przed PyInstallerem.

6. GUI: w górnym pasku obok "Motyw" QToolButton "Język" z QMenu (QActionGroup checkable: Auto/Polski/English/Deutsch); zmiana → config["language"] + QMessageBox.information(_("Zmiana języka zadziała po ponownym uruchomieniu aplikacji.")).

7. Build: datas locale → epubforge/locale w .spec; check_build_env.py sprawdza ≥1 plik .mo.

8. Testy (tests/test_i18n.py + smoke):
   - init_i18n("en") → _() zwraca angielskie tłumaczenie realnego wpisu; fallback nieznanego msgid; language="xx" nie wybucha
   - ngettext pl dla n=1,2,5 → trzy formy
   - spójność: każdy msgid z .pot ma niepusty, nie-fuzzy odpowiednik w en.po i de.po (babel.messages.pofile)
   - .mo w repo aktualne względem .po (kompilacja do tmp + porównanie katalogów tłumaczeń)
   - i18n importuje się i działa bez PySide6 (monkeypatch ImportError)
   - pytest-qt: MainWindow startuje z config {"language": "en"} i tytuł zakładki jest po angielsku

9. README (sekcja języków + jak dodać nowy), CHANGELOG.
10. pytest, ruff --fix, mypy. Commit: "feat(i18n): gettext-based PL/EN/DE localization with GUI language switcher"
11. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- locale.getlocale() na Windows umie zwrócić ("Polish_Poland", "1250") — normalizuj.
- Sprawdź grepem, że żadne _() nie zawiera f-stringa.
```

---

## 🎨 Etap F-B — F11: Biblioteka presetów CSS

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-B). Przeczytaj AKTUALNY stan: core/epub.py (manifest, write_file, delete_file, opf_dir), fixers/css_fixer.py (wzorce lxml/manifest), gui/tabs/fixer.py (już PySide6), core/config.py. Nowe stringi przez _() + uzupełnij en/de .po + przekompiluj .mo (build/compile_locales.py).

ZADANIE: biblioteka presetów CSS (F11) — wbudowane szablony + import własnych; API + CLI + GUI.

1. main + pull. Gałąź: feature/f11-css-presets

2. fixers/presets/: presets.json ({id, name:{pl,en,de}, description:{pl,en,de}, file}) + reader-friendly.css, print-like.css, dark-oled.css, manga-rtl.css — treści wg ROADMAP §F-B, każdy z polskim komentarzem nagłówkowym (przeznaczenie + ograniczenia czytników).

3. fixers/css_presets.py — API wg ROADMAP §F-B:
   - CssPreset (frozen), list_presets(user_dir=None), get_preset(), apply_preset(epub, preset, mode="append"|"replace"), import_user_preset()
   - append: zapis {opf_dir}/styles/epubforge-preset.css; <item> w manifeście OPF (lxml, id "efpreset-css", media-type text/css) jeśli brak; w KAŻDYM pliku spine <link rel="stylesheet" ...> jako OSTATNIE dziecko <head> (XHTML ma namespace — szukaj head z ns!) jeśli brak; href względne: manifest względem opf_dir, link względem pliku XHTML — RÓŻNE bazy, licz posixpath.relpath. Ponowna aplikacja = tylko podmiana zawartości arkusza (idempotencja).
   - replace: usuń z manifestu wszystkie itemy text/css (poza naszym) + odpowiadające <link> + pliki (epub.delete_file); potem jak append.
   - user_dir default: default_config_path().parent / "presets"; import waliduje tinycss2 (odrzuć pusty/sam błąd).
   - serializacja XHTML: zachowaj deklarację XML i doctype.
   - eksport w fixers/__init__.py.

4. CLI: cli/presets.py ("presets list" — tabela id/nazwa/opis w bieżącym języku); cli/fix.py: --preset ID, --preset-mode {append,replace}; rejestracja w main.py.

5. GUI (FixerTab): Section "Preset CSS": QComboBox ("nazwa — opis"), QRadioButton Dołącz/Zastąp, "Importuj własny…" (QFileDialog → import_user_preset → odśwież combo), QCheckBox "Zastosuj preset" włączający krok w pipeline. Tooltipy (setToolTip).

6. Build: fixers/presets w datas .spec + check_build_env.py; wheel zawiera presets (hatchling).

7. Testy (tests/test_css_presets.py):
   - list_presets ≥ 4; get_preset nieznany → wyjątek
   - append na fixtures/sample.epub: plik istnieje, jest w manifeście, link OSTATNI w head każdego spine
   - idempotencja (bez dubli), replace usuwa stare arkusze i linki
   - po save(): EPUB otwiera się, mimetype pierwszy i ZIP_STORED
   - import: kopiuje + widoczny w list_presets(user_dir=tmp); śmieć → wyjątek
   - CLI list (capsys) i fix --preset na kopii fixture

8. README (tabela + przykłady CLI), user-guide, CHANGELOG.
9. pytest, ruff --fix, mypy. Commit: "feat(fixers): built-in and user CSS preset library (F11)"
10. Zaproponuj push i PR. NIE pushuj automatycznie.
```

---

## ✏️ Etap F-C — F3: Edytor wewnętrzny (core)

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-C). Przeczytaj AKTUALNY stan: core/epub.py (read_file/write_file/save/list_files/manifest/opf_dir), gui/app.py (MainWindow, QTabWidget, ThemeManager), gui/theme.py, gui/widgets/. Stringi przez _() + en/de + .mo.

ZADANIE: zakładka "Edytor" — przegląd i szybka edycja plików wewnątrz EPUB z syntax highlightingiem (F3, część 1). Quick fix, nie Sigil.

1. main + pull. Gałąź: feature/f3-editor-core

2. gui/widgets/syntax_highlight.py:
   - XmlHighlighter(QSyntaxHighlighter) i CssHighlighter(QSyntaxHighlighter)
   - reguły jako lista (QRegularExpression, QTextCharFormat): xml — komentarz <!-- --> (wieloliniowy przez block state), tag, atrybut, wartość w cudzysłowie, encja &..;; css — komentarz /* */ (block state), selektor, @-reguła, właściwość, wartość, !important
   - kolory WYŁĄCZNIE z ról Theme (warianty jasny/ciemny); metoda rehighlight przy zmianie motywu (podepnij do sygnału theme_changed)
   - logika dopasowań wydzielona do funkcji czystych tam, gdzie się da (testy bez Qt)

3. gui/widgets/code_editor.py — CodeEditor(QWidget):
   - QPlainTextEdit + line number area (kanoniczny wzorzec Qt: widget-rynna, blockCountChanged + updateRequest + lineNumberAreaPaintEvent; kolory z Theme)
   - pasek wyszukiwania (Ctrl+F pokazuje, Esc chowa): QLineEdit + Następny/Poprzedni (F3/Shift+F3), wszystkie trafienia przez setExtraSelections, licznik "3/17"
   - status wiersz:kolumna (cursorPositionChanged)
   - API: load(text, profile: "xml"|"css"|None), get_text(), goto_line(n) (QTextCursor + centerCursor), property read_only, sygnał modified_changed (document().modificationChanged)
   - undo/redo natywne (nic nie rób, tylko nie psuj: load przez setPlainText + document().setModified(False))

4. gui/tabs/editor.py — EditorTab(QWidget):
   - toolbar: "Otwórz EPUB…", QLabel ścieżki, "Zapisz EPUB" (enabled przy zmianach), QCheckBox/QToolButton "Tryb edycji" — DOMYŚLNIE WYŁĄCZONY (start read-only)
   - QSplitter: lewo QTreeWidget — grupy Tekst/Style/Obrazy/Fonty/Inne (media_type z epub.manifest; pliki z list_files() spoza manifestu po rozszerzeniu); "*" przy zmodyfikowanych; prawo QStackedWidget: CodeEditor (text/css/xml/xhtml/opf/ncx — profil xml dla opf/ncx/xhtml) / podgląd obrazu (QLabel + QPixmap, skalowanie KeepAspectRatio w resizeEvent z debounce QTimer) / panel info (nazwa, rozmiar, media-type) dla binariów
   - stan: self._epub: Epub|None (jeden na życie zakładki), self._dirty: dict[str, str], self._current: str|None
   - zmiana pliku przy niezapisanych zmianach: QMessageBox Zapisz/Porzuć/Anuluj
   - Ctrl+S (QShortcut): dla XHTML/OPF próba lxml.etree.fromstring → błąd ⇒ "Plik nie jest poprawnym XML: …\nZapisać mimo to?"; zapis = epub.write_file(path, text.encode("utf-8")); usuń z _dirty; osobny wskaźnik "EPUB ma niezapisane zmiany" przy przycisku Zapisz EPUB
   - "Zapisz EPUB" = epub.save() (backup .bak jak dotąd), reset wskaźników
   - dekodowanie utf-8 errors="replace"; "\ufffd" w wyniku ⇒ pasek informacyjny + wymuszony read-only pliku
   - has_unsaved_changes() → MainWindow.closeEvent pyta i pokazuje QMessageBox

5. gui/app.py:
   - dodaj EditorTab do QTabWidget (tytuł przez _()), eksport w tabs/__init__.py
   - NOWA METODA MainWindow.open_in_editor(epub_path: Path, internal_path: str|None=None, line: int|None=None) — setCurrentWidget na Edytor + delegacja do editor_tab.open_external(...) (otwiera EPUB jeśli inny niż bieżący — z obsługą niezapisanych zmian; zaznacza plik w drzewie; goto_line). PUBLICZNY KONTRAKT dla etapu F-E.

6. Testy:
   - czyste: klasyfikacja plików (media-type/rozszerzenie), helper offset↔(linia,kolumna)
   - pytest-qt: load/get_text roundtrip z polskimi znakami; goto_line; read_only blokuje qtbot.keyClicks; search liczy trafienia; flow: otwórz fixtures/sample.epub → drzewo ma grupy/pliki → edycja xhtml → Ctrl+S → "Zapisz EPUB" → reopen przez Epub → treść zmieniona; plik nie-UTF8 (zbuduj w tmp na bazie fixture) → read-only; open_in_editor zaznacza plik i ustawia linię; highlighter nadaje formaty (sprawdź QTextDocument formats)

7. README/user-guide/CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(gui): internal EPUB editor with syntax highlighting (F3 core)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- editor.py < 500 linii: klasyfikację/IO wynieś do funkcji modułowych, podgląd obrazu do osobnego widgetu jeśli puchnie.
- QPixmap trzymaj jako atrybut (GC).
- QShortcut z kontekstem WidgetWithChildrenShortcut, żeby Ctrl+S nie strzelał z innych zakładek.
```

---

## 🔬 Etap F-D — F3+: Inspektor reguł CSS z podglądem na żywo

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md i ROADMAP_FEATURES_v1.1.md sekcja F-D — wiążąca (warstwy, spany, podzbiór CSS). Przeczytaj AKTUALNY stan: gui/widgets/code_editor.py, gui/tabs/editor.py, gui/theme.py, fixers/css_fixer.py (użycie tinycss2). Stringi przez _() + en/de + .mo.

ZADANIE: panel "Inspektor CSS" w edytorze — lista reguł arkusza; dla każdej podgląd przykładowego tekstu sformatowanego zgodnie z regułą (QTextDocument); edycja reguły aktualizuje podgląd NA ŻYWO; "Zastosuj" wpisuje zmianę do arkusza.

1. main + pull. Gałąź: feature/f3-css-inspector

2. WARSTWA LOGIKI — src/epubforge/fixers/css_rules.py (czyste funkcje, ZERO importów Qt/gui):
   a) parse_rules(source: str) -> list[CssRuleInfo]
      - CssRuleInfo: selector, declarations: list[CssDecl(name, value, important)], span: tuple[int,int] (offsety ZNAKOWE [start, end) od selektora do '}' włącznie), media: str|None, previewable: bool, parse_errors: list[str]
      - tinycss2.parse_stylesheet; offsety z source_line/source_column (1-indeksowane!) + zbudowana raz tabela offsetów początków linii; koniec reguły: od pozycji końca OSTATNIEGO tokenu content skan do '}' (odporność na '}' w stringach/komentarzach — dlatego od tokenu, nie regexem po źródle)
      - @media: parse_blocks_contents rekurencyjnie, media=serializowany prelude; @font-face/@page/@import → previewable=False
   b) replace_rule(source, span, new_text) -> str — JEDYNA modyfikacja źródła (zero re-serializacji tinycss2)
   c) parse_single_rule(text) -> CssRuleInfo | list[str]
   d) declarations_to_preview(decls) -> tuple[str, list[str]]
      - buduje INLINE style="..." z deklaracji przefiltrowanych whitelist'ą podzbioru CSS silnika rich text Qt (dokument "Supported HTML Subset"): font-family, font-size, font-weight, font-style, color, background-color, text-align (justify DZIAŁA), text-indent, line-height, margin-*, padding-*, text-decoration, text-transform; jednostki px/pt/em/% przepuszczane/normalizowane; wszystko spoza whitelisty → druga wartość (lista nieobsługiwanych)
      - celowo inline style, NIE setDefaultStyleSheet z selektorem — omijamy ograniczenia dopasowania selektorów Qt
   e) sample_for_selector(selector) -> (tag_html, text) — h1..h6 → "Rozdział pierwszy"; p/body/klasy → akapit Z POLSKIMI DIAKRYTYKAMI ("Zażółć gęślą jaźń…" + 2 zdania); blockquote/.quote → cytat; code/pre → fragment kodu; inne → akapit domyślny
   f) build_preview_html(rule) -> tuple[str, list[str]] — składa <tag style="...">tekst</tag> w minimalny dokument (escapuj tekst!)

3. gui/widgets/css_inspector.py — CssInspector(QWidget):
   - konstruktor: get_source: Callable[[], str], apply_replacement: Callable[[int,int,str], None] | None (None = tryb read-only, przycisk Zastosuj ukryty), theme
   - QSplitter pionowy: (1) QTreeWidget reguł: Selektor | Deklaracje (skrót ~60 zn.) | @media; previewable=False wyszarzone; (2) edytor reguły = CodeEditor (profil css, ~8 linii) z source[span]; (3) podgląd: QTextEdit read-only na "papierowej" białej karcie z ramką — tło NIEZALEŻNE od motywu aplikacji (dark mode nie może fałszować typografii) + pod spodem QLabel "Nieobsługiwane w podglądzie: …" i stała adnotacja "Podgląd przybliżony — czytnik może różnić się w szczegółach"; (4) przyciski "Zastosuj do arkusza" / "Przywróć"
   - LIVE: textChanged edytora reguły → QTimer debounce 300 ms → parse_single_rule → OK: setHtml(build_preview_html(...)) + aktualizacja listy nieobsługiwanych; błąd: czerwona ramka pola + komunikat parsera, podgląd zostaje na ostatnim poprawnym
   - Zastosuj: walidacja → apply_replacement(start, end, new_text) → refresh() (re-parse, spany przeliczone, zaznaczenie zachowane po selektorze)
   - refresh() wołany też po edycji w GŁÓWNYM edytorze (textChanged + debounce 400 ms)

4. Integracja w gui/tabs/editor.py:
   - dla plików text/css: CssInspector w prawym QSplitterze, DOMYŚLNIE otwarty, toggle "Inspektor CSS" w toolbarze; dla innych plików ukryty
   - apply_replacement przez QTextCursor głównego edytora: setPosition(start), setPosition(end, KeepAnchor), insertText(new_text) — JEDNA operacja kursora ⇒ undo cofa całość; plik dostaje "*", dalej standardowy flow Ctrl+S/"Zapisz EPUB"

5. Synergia F11: w sekcji presetów (FixerTab) przycisk "Podgląd…" → QDialog z CssInspector(get_source=lambda: preset.css, apply_replacement=None).

6. Testy — NAJWAŻNIEJSZA część etapu:
   tests/test_css_rules.py (bez Qt):
   - parse_rules: prosta; "h1, h2"; dwie reguły — source[span] zaczyna się selektorem i kończy '}', spany rozłączne; komentarz przed i wewnątrz; content: "}" oraz url("a}b.png") — span poprawny; @media → media!=None; @font-face → previewable=False
   - replace_rule: podmiana środkowej z trzech — tekst poza spanem IDENTYCZNY bajt w bajt
   - declarations_to_preview: po teście na każdą właściwość whitelisty; jednostki 16px/1.2em/120%; kolory #abc/#aabbcc/rgb()/nazwa; font-weight 700→bold w stylu; text-align: justify PRZECHODZI; letter-spacing/hyphens → unsupported; !important → wartość przechodzi + adnotacja
   - sample_for_selector: h1, p, .quote, blockquote, code, "div#x>span" (fallback)
   - build_preview_html: escapuje tekst, zawiera style
   - parse_single_rule: poprawna → CssRuleInfo; "p { color: }" → błędy
   tests/gui/test_css_inspector.py (pytest-qt):
   - otwarcie css w EditorTab → panel widoczny; wybór reguły ładuje edytor reguły
   - edycja "color: red"→"color: blue" + przeskoczenie debounce (qtbot.wait / wymuszenie timera) → toHtml() podglądu zawiera blue
   - "Zastosuj" → get_text() głównego edytora zawiera zmianę; undo (QKeySequence.Undo) ją cofa

7. README/user-guide (opis ograniczeń podglądu!), CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(gui): live CSS rule inspector with QTextDocument preview (F3+)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- tinycss2: source_line/source_column wskazują POCZĄTEK tokenu, 1-indeksowane.
- Nie re-serializuj arkusza tinycss2 — replace_rule po spanie to jedyna ścieżka zapisu.
- QTextEdit.setHtml resetuje dokument — ustawiaj read-only i tło przez stylesheet kontenera, nie dokumentu.
- Przy ogromnych arkuszach (Calibre) lista reguł może mieć tysiące pozycji — buduj itemy hurtowo (setUpdatesEnabled(False) na czas wypełniania).
```

---

## ✅ Etap F-E — F2: Walidacja EpubCheck

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-E). Przeczytaj AKTUALNY stan: core/detection.py (Tool/Tools/cache/overrides), gui/workers.py, gui/widgets/file_list.py, gui/tabs/fixer.py (wzorzec taba), gui/app.py (open_in_editor z F-C). Stringi przez _() + en/de + .mo.

ZADANIE: walidacja EPUB przez EpubCheck 5.x (java -jar): detekcja narzędzi, parser raportu JSON, CLI `epubforge check`, zakładka GUI z klikalnymi błędami skaczącymi do edytora.

1. main + pull. Gałąź: feature/f2-epubcheck

2. core/detection.py — dwa narzędzia wg wzorca istniejących:
   - Tools.java(): PATH, JAVA_HOME/bin, %ProgramFiles%/Eclipse Adoptium/*/bin, /usr/bin; wersja: `java -version` pisze na STDERR — parsuj stderr, wyciągnij major (formaty "17.0.x" i "1.8.0_xx"); available wymaga major >= 11
   - Tools.epubcheck(): ścieżka do epubcheck.jar w kolejności: (1) config override tools.epubcheck_jar, (2) glob %ProgramFiles%/epubcheck*/epubcheck*.jar i ~/epubcheck*/, (3) default_config_path().parent/"epubcheck"/"epubcheck.jar", (4) katalog exe (frozen); wersja z META-INF/MANIFEST.MF jara (zipfile, Implementation-Version) — bez uruchamiania javy
   - oba w detect_with_cache i _apply_overrides

3. validators/__init__.py + validators/epubcheck.py — wg ROADMAP §F-E:
   - Severity, ValidationMessage(severity, code, message, internal_path, line, column), ValidationReport(epub_path, valid, epubcheck_version, messages, duration_s, counts())
   - run_epubcheck(epub_path, java, jar, timeout=300): [java.path, "-jar", jar, str(epub_path), "--json", tmp_json] w tempfile.TemporaryDirectory, CREATE_NO_WINDOW, text=True, encoding="utf-8", errors="replace", timeout
   - exit != 0 przy istniejącym poprawnym JSON = raport valid=False (NIE wyjątek); brak/zepsuty JSON lub timeout = EpubforgeError ze stderr
   - parser defensywny: messages[] → severity (lower; mapuj USAGE/SUPPRESSED), ID, message, locations[0].{path,line,column} przez get(); path normalizuj do ścieżki WEWNĘTRZNEJ (utnij wszystko do "*.epub/" włącznie); brak locations → internal_path=None
   - epubcheck_version z checker.checkerVersion

4. cli/check.py: `epubforge check book.epub [--json out.json] [--min-severity warning]`; wypis: liczby per severity + lista "ścieżka:linia [KOD] treść"; exit 0 valid / 1 błędy / 2 brak narzędzi (z instrukcją instalacji jak w pkt 5). Rejestracja w main.py.

5. gui/tabs/validator.py — zakładka "Walidacja":
   - FileList (D&D), "Sprawdź zaznaczony" → Worker (QThread), status
   - pasek podsumowania "✗ N błędów · ⚠ N ostrzeżeń · ℹ N informacji" (ngettext!)
   - filtry severity (QCheckBox x3) + QTreeWidget: Poziom | Kod | Plik:linia | Komunikat (kolor wiersza wg ról Theme: red/amber/fg2; pełny komunikat w setToolTip)
   - DWUKLIK wiersza z internal_path → main_window.open_in_editor(epub_path, internal_path, line) — referencję main_window przekaż przy konstrukcji
   - "Eksport…" → JSON (dataclasses.asdict) lub HTML (samowystarczalna tabela)
   - gdy java/jar niedostępne: panel pomocy zamiast wyników — instrukcja (Temurin 17+, epubcheck z W3C GitHub releases) + przycisk "Wskaż epubcheck.jar…" (QFileDialog → config["tools"]["epubcheck_jar"] → re-detekcja → odśwież)
   - rejestracja w app.py i tabs/__init__.py

6. Testy — ZERO prawdziwej javy (mock subprocess wszędzie):
   - tests/fixtures/epubcheck/: report_ok.json, report_errors.json (fatal + 2x error z locations + warning bez locations), report_broken.json
   - parser: counts, normalizacja "book.epub/OEBPS/ch1.xhtml" → "OEBPS/ch1.xhtml", brak locations → None, valid flag
   - run_epubcheck z mockiem: OK; exit!=0 + dobry JSON → raport; timeout → EpubforgeError; brak pliku JSON → EpubforgeError
   - parser wersji javy: "openjdk version \"17.0.9\"" OK, "java version \"1.8.0_391\"" → unavailable
   - wersja epubcheck z MANIFEST.MF (mini-jar zbudowany zipfile w tmp)
   - CLI exit codes (mock run_epubcheck)
   - pytest-qt: tabela wypełnia się z podstawionego raportu; dwuklik woła open_in_editor (mock/flaga)

7. README (Walidacja + wymagania Java/epubcheck), user-guide, CHANGELOG.
8. pytest, ruff --fix, mypy. Commit: "feat(validators): EpubCheck integration with clickable GUI report (F2)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- `java -version` → STDERR.
- Subprocess argumenty listą (polskie znaki w ścieżkach).
- QTreeWidgetItem: dane (internal_path, line) trzymaj w setData(Qt.UserRole), nie parsuj z tekstu kolumny.
```

---

## 📑 Etap F-F — F10: Generator i edytor spisu treści

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-F). Przeczytaj AKTUALNY stan: core/epub.py, core/metadata.py (identifier do NCX), fixers/css_fixer.py (OPF przez lxml). Stringi przez _() + en/de + .mo.

ZADANIE: pakiet toc/ (model, reader, generator, writer, repair) + CLI `epubforge toc` + zakładka GUI z edycją drzewa (natywny drag&drop QTreeWidget).

1. main + pull. Gałąź: feature/f10-toc

2. src/epubforge/toc/ wg ROADMAP §F-F:
   - model.py: TocEntry(title, href, children) + CZYSTA funkcja move_entry(entries, src, dst, mode: "before"|"after"|"into") — w tym zakaz przeniesienia do własnego potomka; to model pod D&D, z pełnymi testami
   - reader.py: read_toc(epub) → (entries, source) — nav.xhtml (item z properties zawierającym "nav", <nav epub:type="toc">, zagnieżdżone ol/li/a) z fallbackiem do toc.ncx (navMap/navPoint)
   - generator.py: generate_toc(epub, max_level=3) — spine W KOLEJNOŚCI, lxml z recover; h1..h{max_level}; drzewo wg poziomów (osierocony h3 bez h2 → poziom wyżej); tytuł = znormalizowany " ".join(itertext().split()); nagłówek bez id → wstrzyknij id="efh-NNNN" (licznik per plik, sprawdź kolizje z istniejącymi id) i zapisz przez epub.write_file Z ZACHOWANIEM deklaracji XML i doctype; PIERWSZY nagłówek pliku → href bez fragmentu; plik bez nagłówków pomijany; IDEMPOTENCJA drugiego przebiegu (nie dodaje nowych id)
   - writer.py: write_toc(epub, entries, write_nav=True, write_ncx=True) — nav.xhtml: jeśli istnieje, podmień TYLKO <nav epub:type="toc">; jeśli nie, pełny dokument pod {opf_dir}/nav.xhtml (xmlns + xmlns:epub="http://www.idpf.org/2007/ops") + manifest properties="nav" (spine NIETKNIĘTY); toc.ncx: pełna regeneracja (uid z metadata, playOrder DFS) + manifest + atrybut toc= w <spine> jeśli brak; href w nav względne do nav.xhtml, w ncx do ncx — licz posixpath.relpath, nie zakładaj wspólnej bazy
   - repair.py: validate_toc(epub, entries) → list[TocProblem(href, reason)] (href nie istnieje / fragment nie istnieje — cache zbioru id per plik); repair_toc usuwa martwe (dzieci podciąga do rodzica), zwraca (entries, removed)

3. cli/toc.py: `epubforge toc book.epub --show | --generate [--max-level 3] [--output out.epub] | --repair [--dry-run]`; --show drukuje drzewo z wcięciami; rejestracja w main.py.

4. gui/tabs/toc.py — zakładka "Spis treści":
   - PathEntry/przycisk wyboru EPUB → read_toc → QTreeWidget (Tytuł | Cel); wpisy z problemami (validate_toc przy wczytaniu) czerwonym kolorem (rola red z Theme) + tooltip z powodem
   - toolbar: Generuj (QSpinBox max-level 1–6 + potwierdzenie nadpisania), Napraw (QDialog z listą problemów → potwierdź), Dodaj, Usuń, ⬆ ⬇ (rodzeństwo), ⬅ ➡ (outdent/indent), "Zapisz do EPUB"
   - edycja tytułu: flaga Qt.ItemIsEditable TYLKO na kolumnie tytułu (openPersistentEditor nie potrzebny — domyślny edytor po dwukliku/F2); itemChanged aktualizuje model
   - drag&drop: setDragDropMode(QAbstractItemView.InternalMove), setDefaultDropAction(MoveAction); w dropEvent ZSYNCHRONIZUJ model: wyznacz src/dst/tryb (dropIndicatorPosition: OnItem→"into", AboveItem→"before", BelowItem→"after"), wywołaj move_entry na modelu i PRZEBUDUJ widok z modelu (mapowanie item↔entry przez słownik id(entry)); nie pozwól rozjechać się widoku z modelem
   - "Zapisz do EPUB": write_toc + epub.save(); wskaźnik niezapisanych zmian; pytania przy zmianie pliku/zamknięciu
   - rejestracja w app.py i tabs/__init__.py

5. Fixtures: rozbuduj tests/fixtures/make_sample_epub.py o make_toc_epub(tmp): ch1 (h1 + dwa h2, jeden h2 z <em> w środku, bez id), ch2 (h1 bez id + osierocony h3), ch3 (bez nagłówków, z <title>); prosty nav.xhtml z jednym MARTWYM wpisem.

6. Testy:
   - generator: struktura drzewa (poziomy, osierocony h3), tytuł z <em> sklejony, polskie znaki, pierwszy nagłówek bez fragmentu, id wstrzyknięte unikalne, idempotencja, plik bez nagłówków pominięty
   - writer→reader roundtrip (nav i ncx); nav w manifeście z properties="nav"; ncx w spine@toc; EPUB po save zdrowy (mimetype pierwszy, ZIP_STORED)
   - repair: martwy href i zły fragment wykryte; usunięcie podciąga dzieci
   - move_entry: before/after/into + zakaz przeniesienia do potomka
   - CLI --show/--generate/--repair --dry-run (capsys, kopie fixture w tmp)
   - pytest-qt: wczytanie, generacja podmienia drzewo, edycja tytułu przez itemChanged trafia do modelu, zapis; przeniesienie testuj przez bezpośrednie wywołanie logiki synchronizacji (symulacja dropEvent jest krucha — wydziel handler przyjmujący (src, dst, tryb))

7. README/user-guide/CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(toc): TOC generator, repair and tree editor (F10)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- lxml.etree.tostring gubi doctype bez doctype= z parsera — XHTML w EPUB często ma DOCTYPE.
- epub:type wymaga xmlns:epub.
- itemChanged strzela też przy programowych zmianach — blockSignals(True) podczas przebudowy drzewa.
```

---

## 📲 Etap F-G — F7: Konwersja MOBI → EPUB

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-G). Przeczytaj AKTUALNY stan: converters/to_epub.py (routing silników, fallback PDF→Calibre, ConversionResult), gui/tabs/converter.py, cli/convert.py. Stringi przez _() + en/de + .mo.

ZADANIE: formaty Kindle (.mobi/.azw3/.azw/.prc) jako wejście konwersji do EPUB — wyłącznie Calibre, z przyjazną obsługą DRM. KindleUnpack NIE używamy (GPL — copyleft).

1. main + pull. Gałąź: feature/f7-mobi-to-epub

2. converters/to_epub.py:
   - _KINDLE_SUFFIXES = {".mobi", ".azw3", ".azw", ".prc"}
   - routing: te rozszerzenia ⇒ wymuś Calibre niezależnie od engine="auto"; engine="pandoc" jawnie → ConversionError ("Pandoc nie obsługuje formatów Kindle")
   - PRZED konwersją wywołaj has_kindle_drm (pkt 3); DRM → ConversionError(_("Plik jest zabezpieczony DRM — konwersja niemożliwa. EpubForge nie usuwa zabezpieczeń.")); dodatkowo mapuj "DRM" ze stderr Calibre na ten sam komunikat

3. converters/kindle_drm.py — lekki detektor (~60-80 linii, czysty struct, pełne docstringi z layoutem nagłówka):
   - has_kindle_drm(path: Path) -> bool
   - PalmDB: liczba rekordów (offset 76, >H), lista rekordów od 78 (8 bajtów: >I offset + 4 bajty atrybuty/uid) → offset rekordu 0; w rekordzie 0: magic "MOBI" na offsecie 16; encryption type na offsecie 12 rekordu (>H): 0 = brak DRM, 1/2 = DRM
   - plik za krótki / brak magic → False (niech Calibre się wypowie)

4. CLI: bez nowych komend (convert przyjmie .mobi); zaktualizuj help o formaty Kindle i uwagę o DRM.

5. GUI ConverterTab: rozszerz filtry QFileDialog i walidację rozszerzeń; plik Kindle → wybór silnika zablokowany na Calibre + etykieta informacyjna; DRM → QMessageBox.warning (nie traceback w logu).

6. Testy:
   - kindle_drm: syntetyczne bajty (struct.pack) dla encryption 0/1/2; plik 10-bajtowy → False; brak magic → False. ŻADNYCH prawdziwych mobi w repo.
   - routing z mockiem subprocess: dla input.mobi poleciał ebook-convert z poprawnymi argumentami; engine="pandoc" → ConversionError; brak Calibre → ConverterNotFoundError
   - monkeypatch has_kindle_drm=True → ConversionError, subprocess NIE wywołany
   - stderr z "DRMError" → zmapowany komunikat

7. README (tabela formatów + MOBI/AZW3/AZW/PRC, silnik Calibre, uwaga DRM), user-guide, CHANGELOG.
8. pytest, ruff --fix, mypy. Commit: "feat(converters): Kindle MOBI/AZW3 to EPUB via Calibre with DRM detection (F7)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.
```

---

## 📊 Etap F-H — F8: Statystyki książki

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-H). Przeczytaj AKTUALNY stan: core/epub.py, core/metadata.py, gui/workers.py, toc/generator.py jeśli istnieje (reużyj ekstrakcję tytułu rozdziału). Stringi przez _() + en/de + .mo.

ZADANIE: statystyki książki (słowa, strony, czas czytania, język, top-słowa) + samowystarczalny raport HTML + CLI + zakładka GUI.

1. main + pull. Gałąź: feature/f8-stats

2. pyproject.toml: [project.optional-dependencies] stats = ["langdetect>=1.0.9"]; mypy override ignore_missing_imports dla langdetect.

3. src/epubforge/stats.py wg ROADMAP §F-H (ChapterStats, BookStats, StatsOptions(words_per_page=250, wpm=200, top_n=50), compute_stats, render_report_html):
   - ekstrakcja: spine w kolejności, lxml recover, itertext() z pominięciem poddrzew script/style; tytuł rozdziału = pierwszy h1/h2 albo <title> albo None
   - tokenizacja: re.findall(r"\w+", text, re.UNICODE); odfiltruj tokeny będące czystymi liczbami
   - język: try-import langdetect wewnątrz funkcji (DetectorFactory.seed = 0 — bez seeda jest niedeterministyczny; próbka pierwszych 10000 znaków) → fallback metadata.language (przytnij do kodu 2-literowego) → None; zapisz language_source ("langdetect"/"metadata"/None)
   - top-słowa: lower(), filtr stop-listy wg języka, Counter.most_common z deterministycznym tie-breakiem (alfabetycznie)
   - stop-listy: src/epubforge/stats_stopwords/{pl,en,de}.txt — wygeneruj po 200-300 najczęstszych słów funkcyjnych (po jednym na linię, lowercase, UTF-8); loader z cache
   - render_report_html: samowystarczalny HTML (inline CSS w jasnej palecie z GUI_STANDARD §5, ZERO zasobów sieciowych), html.escape NA KAŻDEJ wartości pochodzącej z książki; sekcje: nagłówek (tytuł/autor z Metadata), karty liczb, chmurka top-słów (span, font-size log-skala 12-40 px), tabela rozdziałów, wykres słupkowy słowa/rozdział jako inline SVG własną funkcją _bar_chart_svg(values, labels) (max 60 słupków, powyżej agreguj), stopka "Wydrukuj do PDF: Ctrl+P" + wersja EpubForge

4. cli/stats.py: `epubforge stats book.epub [--report out.html] [--top 50] [--words-per-page 250] [--wpm 200]` — podsumowanie + top 20; rejestracja w main.py.

5. gui/tabs/stats.py — zakładka "Statystyki": PathEntry → "Oblicz" → Worker → karty (QGroupBox: słowa, szac. strony, czas h:min, język + źródło), lista top-słów (QListWidget), QTreeWidget rozdziałów (tytuł, słowa), "Eksport HTML…" (QFileDialog) i "Otwórz raport" (zapis tmp + webbrowser.open). Brak langdetect → adnotacja "język z metadanych (zainstaluj epubforge[stats])". Rejestracja w app.py i tabs/__init__.py.

6. Build/packaging: stats_stopwords do wheel i datas .spec + check_build_env.py.

7. Testy (tests/test_stats.py):
   - compute_stats na fixtures/sample.epub: deterministyczne liczby (oczekiwane policz w teście z tej samej treści fixture)
   - "Zażółć gęślą jaźń" = 3 słowa; liczby odfiltrowane; stop-lista pl filtruje "i", "w", "się"
   - fallback języka: monkeypatch importu langdetect na ImportError → language_source="metadata"
   - top_words: sort malejąco, remis alfabetycznie, top_n respektowane
   - raport: zawiera tytuł książki; "<b>złośliwy</b>" w tytule rozdziału zescapowany; liczba <rect> w SVG = liczba rozdziałów (≤60); brak "http" w treści
   - CLI: exit 0 + plik raportu powstaje (tmp)
   - pytest-qt: smoke — zakładka liczy na fixture (wywołaj logikę synchronicznie) i wypełnia karty

8. README (Statystyki + extra [stats]), user-guide, CHANGELOG.
9. pytest, ruff --fix, mypy. Commit: "feat(stats): book statistics with HTML report (F8)"
10. Zaproponuj push i PR. NIE pushuj automatycznie.
```

---

## 📌 Przypomnienie globalne (dotyczy każdego promptu)

- Komentarze i docstringi po polsku, identyfikatory po angielsku, mypy --strict, pliki < 500 linii.
- GUI: wyłącznie PySide6, kolory tylko przez role Theme (GUI_STANDARD §5), długie operacje przez Worker/QThread + sygnały, tooltipy na elementach interaktywnych.
- Od etapu F-A każdy nowy string użytkownika przez `_()` + aktualizacja `.po` en/de + `build/compile_locales.py`.
- Po etapie: podsumowanie, `git status`, propozycja `git push -u origin HEAD` i `gh pr create` — **bez wykonywania**.
- Merge zawsze: `gh pr merge --squash --delete-branch`.
