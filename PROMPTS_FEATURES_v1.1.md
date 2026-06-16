# 💬 EpubForge — Prompty: migracja Qt + Features v1.1+ (F1, F2, F3+, F7, F8, F10, F11)

| Wersja | Data | Zmiany |
|---|---|---|
| 2.1 | 2026-06-15 | dodano prompt etapu **F-P** (podgląd XHTML); F-S/F-A/F-C/F-D oznaczone ✅ |
| 2.0 | 2026-06-12 | dostosowanie do GUI_STANDARD v2.0: nowy etap **F-S** (własny theme.py, platformdirs, debounce configu, DWM/dialogi, build/CI); F-0 i F-M oznaczone ✅; prompty F-A…F-H zaktualizowane (bez qdarktheme, stany Theme, ścieżki configu) |
| 1.0 | 2026-06-12 | wersja pierwotna |

Gotowe do wklejenia prompty dla etapów z `ROADMAP_FEATURES_v1.1.md`. Kolejność: ~~F-0~~ ✅ → ~~F-M~~ ✅ → ~~F-S~~ ✅ → ~~F-A~~ ✅ → ~~F-C~~ ✅ → ~~F-D~~ ✅ → **F-P** → F-B → F-E → F-F → F-G → F-H. Skopiuj cały blok, wklej do Claude Code, czekaj. **Przed każdym etapem: jesteś na `main` po `git pull`.**

---

## ✅ Etap F-0 — Dokumentacja planu — WYKONANY

Dokumenty planu są w repo. Przy etapie F-S podmienisz `GUI_STANDARD.md` na v2.0 oraz `ROADMAP_FEATURES_v1.1.md` i `PROMPTS_FEATURES_v1.1.md` na bieżące wersje 2.0 (jest to ujęte w prompcie F-S).

## ✅ Etap F-M — Migracja GUI tkinter → PySide6 — WYKONANY

Migracja zrealizowana wg standardu **v1.0** (pyqtdarktheme-fork, light = przywrócony styl natywny, DWM wymuszany zawsze). Standard v2.0 zmienia te trzy rzeczy — domyka je etap F-S poniżej. Promptu F-M nie uruchamiaj ponownie.

---

## 🎛️ Etap F-S — Zgodność z GUI_STANDARD v2.0 (theme.py, platformdirs, DWM, build)

> Przed wklejeniem: sprawdź, czy pdf2md ma już `theme.py` (etap G1). Jeśli TAK — w miejscu `<<<THEME_PY>>>` napisz „WARIANT A: poniżej wklejam theme.py z pdf2md jako punkt startowy — zaadaptuj go" i wklej plik pod promptem. Jeśli NIE — wpisz „WARIANT B: tworzysz pierwszą implementację wg kontraktu; po merge trafi do gui-kit".

```
Pracujemy nad EpubForge (GUI już w PySide6 po migracji F-M). Przeczytaj CLAUDE.md oraz NOWY GUI_STANDARD.md v2.0, który wkleję/wskażę — sekcje 4 (kontrakt theme.py, pułapki DWM/dialogów), 5 (paleta + STANY POCHODNE + nota WCAG + typografia pt), 8 (config przez platformdirs + debounce), 9 (build: upx, onedir; CI) są WIĄŻĄCE. Przeczytaj AKTUALNY stan: gui/theme.py, gui/window_theme.py, gui/app.py, core/config.py, pyproject.toml, build/ (spec + check_build_env.py), .github/workflows/test.yml.

ZADANIE: doprowadzenie projektu do zgodności ze standardem v2.0. Sześć obszarów, zero nowych funkcji.

<<<THEME_PY>>>

1. main + pull. Gałąź: refactor/gui-standard-v2

2. Podmień w repo GUI_STANDARD.md na v2.0 (wkleję) oraz ROADMAP_FEATURES_v1.1.md i PROMPTS_FEATURES_v1.1.md na wersje 2.0 (wkleję).

3. gui/theme.py — WŁASNY motyw zamiast qdarktheme, kontrakt §4 standardu:
   - dwie palety jako dict ról wg §5 (dark i light) + STANY POCHODNE z tabeli §5: hover, pressed, selection_bg/fg, disabled_fg/bg, placeholder, focus_border — dokładne hexy ze standardu
   - apply(app, mode): NAJPIERW app.setStyle("Fusion"), POTEM setPalette(zbudowana QPalette):
     Window/Button=bg, Base=bg3, AlternateBase=bg2, Text/WindowText/ButtonText=fg, PlaceholderText=fg3, Highlight=selection_bg (=accent2), HighlightedText=#ffffff, Link=accent (dark) / accent2 (light — nota WCAG §5!), ToolTipBase=bg2, ToolTipText=fg; grupa Disabled: WindowText/Text/ButtonText=disabled_fg, Button/Base=disabled_bg
   - QSS generowany z palety — WYŁĄCZNIE akcenty (zero dublowania kolorów bazowych z QPalette!): border-radius 4-8px, ramki 1px {border}, :hover={hover}, :pressed={pressed}, focus ramka {focus_border}, QToolTip, ewentualne poprawki paddingów po Fusion
   - tryb auto: QGuiApplication.styleHints().colorScheme() — Dark→dark, Light→light, Unknown→dark (fallback); sygnał colorSchemeChanged PODŁĄCZANY tylko gdy mode=="auto", ODŁĄCZANY przy wymuszeniu
   - po każdej zmianie: style().unpolish()/polish() po app.allWidgets()
   - publiczna dataclass Theme (wszystkie role + stany) — jedyne źródło hexów dla customowych widgetów; ZERO hexów poza theme.py (sprawdź grepem po gui/)
   - rozmiary fontów w QSS/kodzie w pt (nie px); hinty min. 8pt
   - API zachowaj zgodne z obecnym ThemeManagerem (setting, apply, theme, sygnał theme_changed) — minimalizuj zmiany w tabach

4. Usuń qdarktheme: pyproject (wylatuje pyqtdarktheme-fork), wszystkie importy qdarktheme, mypy overrides, check_build_env.py (zamiast tego: import PySide6 + smoke importu epubforge.gui.theme).

5. gui/window_theme.py — niuans Qt 6.5+ (§4):
   - wymuszanie DWM (DwmSetWindowAttribute(20) + WM_NCACTIVATE + RedrawWindow) TYLKO gdy efektywny motyw aplikacji ≠ motyw systemu; przy zgodzie motywów NIC nie rób (Qt 6.5+ sam prowadzi pasek)
   - changeEvent(ActivationChange) ponawia tylko w trybie wymuszonego rozjazdu
   - funkcja sync_titlebar(window, effective_mode, system_scheme) wołana przy starcie, zmianie motywu aplikacji i sygnale colorSchemeChanged

6. Dialogi plików (§4): helper gui/file_dialogs.py (open_file/open_files/save_file/pick_dir) decydujący o QFileDialog.DontUseNativeDialog WYŁĄCZNIE przy rozjeździe app-dark + system-light; wszystkie wywołania QFileDialog w tabach i widgetach przepnij na helper.

7. core/config.py — §8 standardu (UWAGA: core, więc ZERO Qt). STAN OBECNY (przeczytaj default_config_path!): frozen → ZAWSZE obok exe; Windows → %APPDATA%/epubforge; inne → XDG/~/.config/epubforge. Zmiany:
   - pyproject: dodaj platformdirs do dependencies core
   - ścieżka: platformdirs.user_config_dir("epubforge", appauthor=False, roaming=True) — DOKŁADNIE z tymi parametrami i małą literą! Daje to %APPDATA%\epubforge na Windows i ~/.config/epubforge na Linux, czyli ŚCIEŻKI IDENTYCZNE z obecnymi → dla wersji niezamrożonej ZERO migracji (zyskujemy poprawny macOS i przyszłą przenośność). NIE używaj gołego user_config_dir("EpubForge") — dałoby %LOCALAPPDATA%\EpubForge\EpubForge (Local zamiast Roaming + zdublowany katalog) i wymusiło niepotrzebną wędrówkę configu
   - tryb FROZEN — zmiana zachowania: dotąd frozen=zawsze obok exe; od teraz config obok exe TYLKO gdy obok exe istnieje plik-marker "portable.flag" (build portable ma go tworzyć w pakiecie — dopisz do .spec/build.bat wariantu portable); bez markera frozen używa platformdirs jak wersja deweloperska (naprawia to utajony bug zapisu configu w Program Files dla wersji instalowanej)
   - MIGRACJA (tylko scenariusz frozen-bez-markera): jeśli platformdirs-owy config nie istnieje, a obok exe leży stary config.json — skopiuj go do nowej lokalizacji (z logiem; starego nie usuwaj — to może być czyjś świadomy układ portable)
   - zapis: zostaje atomowy (tmp+replace); DODAJ mark_dirty() i flush() — mark_dirty tylko ustawia flagę, flush pisze jeśli flaga; zapis natychmiastowy w CLI i przy zamknięciu
   - GUI: w app.py QTimer (singleShot, restartowany) ~1000 ms po każdym mark_dirty → flush; closeEvent robi flush bezwarunkowo; wszystkie miejsca zapisujące config w tabach przepnij na mark_dirty
   - zaktualizuj miejsca pochodne od ścieżki configu (default_config_path().parent itd.) — od teraz JEDNA funkcja config_dir() w core/config.py i wszyscy liczą od niej

8. Audyt typografii/kształtów (§5): przejdź gui/ — rozmiary w pt, hinty ≥ 8pt, ramki 1px; nazewnictwo komponentu „Checkbox" (nie Toggle) jeśli gdzieś zostało.

9. Build (§9): w .spec upx=False (oba warianty); README — sekcja pobierania: rekomendowany instalator (onedir), portable z adnotacją o wolniejszym starcie (rozpakowanie do temp) i możliwych false-positives AV; check_build_env.py jw.

10. CI (§9): w test.yml ZWERYFIKUJ i uzupełnij brakujące: concurrency (group: ${{ github.ref }}, cancel-in-progress: true) oraz paths-ignore: ['**.md', 'docs/**'] dla jobów testowych. Jeśli już są — nie ruszaj. Build Windows ma być tylko przy tagu (sprawdź).

11. Dokumentacja: CLAUDE.md — pułapki Qt zaktualizuj (dodaj: Fusion PRZED setPalette; QPalette=baza/QSS=akcenty bez dublowania; DWM tylko przy motywie ≠ system; upx=False dla Qt; usuń wzmianki o qdarktheme); README (motyw — własny, bez zależności); CHANGELOG ("Changed: replace qdarktheme with in-house theme.py per GUI standard v2.0; config via platformdirs with debounced saves").

12. Testy (pytest-qt + czyste):
    - apply("dark"): styl Fusion aktywny; QPalette: Window==bg dark, Base==bg3, Highlight==accent2, Disabled WindowText==disabled_fg, PlaceholderText==fg3; apply("light"): Window==#ffffff, Link==accent2 (#0F7C5B — WCAG)
    - QSS nie zawiera hexów bazowych (bg/fg z palety) — test stringowy na wygenerowanym stylesheet
    - auto: monkeypatch colorScheme → Dark/Light/Unknown(→dark); colorSchemeChanged podłączony tylko w auto (sprawdź receivers/flagę)
    - config: ścieżka = %APPDATA%\epubforge / ~/.config/epubforge (monkeypatch platformdirs i env — assert zgodności z DOTYCHCZASOWĄ ścieżką, to test regresji „zero migracji dla dev"); frozen+marker → obok exe (tmp z portable.flag i monkeypatch sys.frozen/sys.executable); frozen bez markera → platformdirs + jednorazowa KOPIA starego configu spod exe (utwórz stary plik w tmp, load, assert skopiowany i oryginał nietknięty); mark_dirty nie pisze / flush pisze / dwa mark_dirty = jeden zapis
    - file_dialogs: 4 kombinacje (app dark/light × system dark/light) → DontUseNativeDialog tylko dla dark+light
    - sync_titlebar: wołany z zgodnymi motywami nie dotyka ctypes (mock), z rozjazdem dotyka
    - smoke: MainWindow startuje w obu motywach, przełączenie motywu nie sypie

13. pytest, ruff check . --fix, mypy src/ — zielone.
14. Commit: "refactor(gui): in-house theme engine and standard v2.0 compliance (platformdirs, DWM, build)"
15. Podsumuj różnice względem stanu po F-M jako checklistę. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- setStyle("Fusion") PRZED setPalette — odwrotna kolejność = paleta częściowo zignorowana.
- QPalette grupy: Disabled ustawiaj jawnie (QPalette.ColorGroup.Disabled), inaczej Qt wyliczy własne.
- colorSchemeChanged: trzymaj referencję do połączenia, żeby móc odłączyć przy wymuszeniu.
- platformdirs w core — NIE importuj nic z Qt do config.py; debounce żyje w GUI.
- platformdirs: TYLKO user_config_dir("epubforge", appauthor=False, roaming=True) — inne parametry zmieniają ścieżkę na Windows i psują kompatybilność z istniejącymi configami.
```

---

## 🌍 Etap F-A — F1: Wielojęzyczność (i18n)

```
Pracujemy nad EpubForge (GUI: PySide6 z własnym theme.py po F-S). Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcje 1.3 i F-A) i pyproject.toml.

ZADANIE: internacjonalizacja GUI i CLI przez gettext (NIE Qt Linguist — uzasadnienie w ROADMAP §1.3). Języki: pl (msgid = polski, obecne stringi), en, de.

1. main + pull. Gałąź: feature/f1-i18n

2. pyproject.toml: "babel>=2.14" do [dev]; dane src/epubforge/locale/** do wheel (hatchling).

3. src/epubforge/i18n.py:
   - init_i18n(language: str = "auto"), _(msgid), ngettext(s, p, n)
   - detect_system_language(): QLocale.system().name() jeśli PySide6 importowalne, fallback locale.getlocale(); mapuj na {"pl","en","de"}, default "pl" — moduł MUSI działać bez PySide6 (CLI bez [gui]): import PySide6 w try/except wewnątrz funkcji
   - available_languages() — skan locale/
   - localedir: frozen → Path(sys._MEIPASS)/"epubforge"/"locale", inaczej Path(__file__).parent/"locale"
   - globalny translator ustawiany w init_i18n; _() czyta go W CZASIE WYWOŁANIA (nie binduj przy imporcie)

4. Refactor stringów:
   - WSZYSTKIE stringi widoczne dla użytkownika w gui/ i cli/ (etykiety, tytuły zakładek, tooltips, QMessageBox, statusy, help argparse, printy CLI) przez _() — tłumaczone W MOMENCIE budowy widgetu (po init_i18n), nie w stałych modułowych
   - NIE tłumacz: docstringów, logger.*, wyjątków wewnętrznych, nazw technicznych (EPUB, KFX, Calibre), wzorców filtrów plików
   - liczebniki ZAWSZE przez ngettext (PL: 3 formy — "1 plik / 2 pliki / 5 plików"); zero f-stringów wewnątrz _() — _("...{n}...").format(n=n) (pybabel nie wyciąga f-stringów)
   - init_i18n() na początku gui/app.py main() i cli/main.py main(), z config.get("language", "auto"), PRZED budową UI/parsera

5. Babel: babel.cfg ([python: src/epubforge/**.py]); pybabel extract → locale/epubforge.pot; init en i de; PRZETŁUMACZ samodzielnie wszystkie wpisy en.po i de.po (naturalny, zwięzły język UI; w DE pilnuj długości etykiet); nagłówek pl: Plural-Forms nplurals=3. Utwórz build/compile_locales.py (babel.messages, wszystkie .po → .mo). Uruchom. .mo COMMITUJEMY. Wywołanie dopisz do build/build.bat przed PyInstallerem.

6. GUI: w górnym pasku obok "Motyw" QToolButton "Język" z QMenu (QActionGroup checkable: Auto/Polski/English/Deutsch); zmiana → config["language"] przez mark_dirty (mechanizm z F-S) + QMessageBox.information(_("Zmiana języka zadziała po ponownym uruchomieniu aplikacji.")).

7. Build: datas locale → epubforge/locale w .spec; check_build_env.py sprawdza ≥1 plik .mo.

8. Testy (tests/test_i18n.py + smoke):
   - init_i18n("en") → _() zwraca angielskie tłumaczenie realnego wpisu; fallback nieznanego msgid; language="xx" nie wybucha
   - ngettext pl dla n=1,2,5 → trzy formy
   - spójność: każdy msgid z .pot ma niepusty, nie-fuzzy odpowiednik w en.po i de.po (babel.messages.pofile)
   - .mo w repo aktualne względem .po (kompilacja do tmp + porównanie)
   - i18n działa bez PySide6 (monkeypatch ImportError)
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
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-B). Przeczytaj AKTUALNY stan: core/epub.py (manifest, write_file, delete_file, opf_dir), core/config.py (config_dir z F-S), fixers/css_fixer.py (wzorce lxml/manifest), gui/tabs/fixer.py. Nowe stringi przez _() + uzupełnij en/de .po + przekompiluj .mo (build/compile_locales.py).

ZADANIE: biblioteka presetów CSS (F11) — wbudowane szablony + import własnych; API + CLI + GUI.

1. main + pull. Gałąź: feature/f11-css-presets

2. fixers/presets/: presets.json ({id, name:{pl,en,de}, description:{pl,en,de}, file}) + reader-friendly.css, print-like.css, dark-oled.css, manga-rtl.css — treści wg ROADMAP §F-B, każdy z polskim komentarzem nagłówkowym (przeznaczenie + ograniczenia czytników).

3. fixers/css_presets.py — API wg ROADMAP §F-B:
   - CssPreset (frozen), list_presets(user_dir=None), get_preset(), apply_preset(epub, preset, mode="append"|"replace"), import_user_preset()
   - append: zapis {opf_dir}/styles/epubforge-preset.css; <item> w manifeście OPF (lxml, id "efpreset-css", media-type text/css) jeśli brak; w KAŻDYM pliku spine <link rel="stylesheet" ...> jako OSTATNIE dziecko <head> (XHTML ma namespace — szukaj head z ns!) jeśli brak; href względne: manifest względem opf_dir, link względem pliku XHTML — RÓŻNE bazy, posixpath.relpath. Ponowna aplikacja = podmiana zawartości arkusza (idempotencja).
   - replace: usuń z manifestu wszystkie itemy text/css (poza naszym) + odpowiadające <link> + pliki (epub.delete_file); potem jak append.
   - user_dir default: config_dir() / "presets" (funkcja z F-S); import waliduje tinycss2 (odrzuć pusty/sam błąd).
   - serializacja XHTML: zachowaj deklarację XML i doctype.
   - eksport w fixers/__init__.py.

4. CLI: cli/presets.py ("presets list" — tabela id/nazwa/opis w bieżącym języku); cli/fix.py: --preset ID, --preset-mode {append,replace}; rejestracja w main.py.

5. GUI (FixerTab): Section "Preset CSS": QComboBox ("nazwa — opis"), QRadioButton Dołącz/Zastąp, "Importuj własny…" (helper file_dialogs z F-S → import_user_preset → odśwież combo), QCheckBox "Zastosuj preset" włączający krok w pipeline. Tooltipy.

6. Build: fixers/presets w datas .spec + check_build_env.py; wheel zawiera presets.

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
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-C). Przeczytaj AKTUALNY stan: core/epub.py (read_file/write_file/save/list_files/manifest/opf_dir), gui/app.py (MainWindow, QTabWidget), gui/theme.py (Theme — role i STANY z F-S), gui/widgets/, gui/file_dialogs.py. Stringi przez _() + en/de + .mo.

ZADANIE: zakładka "Edytor" — przegląd i szybka edycja plików wewnątrz EPUB z syntax highlightingiem (F3, część 1). Quick fix, nie Sigil.

1. main + pull. Gałąź: feature/f3-editor-core

2. gui/widgets/syntax_highlight.py:
   - XmlHighlighter(QSyntaxHighlighter) i CssHighlighter(QSyntaxHighlighter)
   - reguły (QRegularExpression, QTextCharFormat): xml — komentarz <!-- --> (wieloliniowy przez block state), tag, atrybut, wartość, encja; css — komentarz /* */ (block state), selektor, @-reguła, właściwość, wartość, !important
   - kolory WYŁĄCZNIE z ról/stanów Theme (theme.py = jedyne źródło hexów); rehighlight na sygnał theme_changed
   - logika dopasowań w funkcjach czystych tam, gdzie się da (testy bez Qt)

3. gui/widgets/code_editor.py — CodeEditor(QWidget):
   - QPlainTextEdit + line number area (kanoniczny wzorzec Qt: blockCountChanged + updateRequest + lineNumberAreaPaintEvent; kolory z Theme)
   - pasek wyszukiwania (Ctrl+F/Esc): QLineEdit + Następny/Poprzedni (F3/Shift+F3), trafienia przez setExtraSelections (kolor selection_bg z Theme), licznik "3/17"
   - status wiersz:kolumna (cursorPositionChanged); font mono w pt
   - API: load(text, profile: "xml"|"css"|None), get_text(), goto_line(n) (QTextCursor + centerCursor), property read_only, sygnał modified_changed
   - undo/redo natywne (load przez setPlainText + document().setModified(False))

4. gui/tabs/editor.py — EditorTab(QWidget):
   - toolbar: "Otwórz EPUB…" (file_dialogs), QLabel ścieżki, "Zapisz EPUB" (enabled przy zmianach), toggle "Tryb edycji" — DOMYŚLNIE WYŁĄCZONY (start read-only)
   - QSplitter: lewo QTreeWidget — grupy Tekst/Style/Obrazy/Fonty/Inne (media_type z epub.manifest; pliki z list_files() spoza manifestu po rozszerzeniu); "*" przy zmodyfikowanych; prawo QStackedWidget: CodeEditor (profil xml dla opf/ncx/xhtml, css dla css) / podgląd obrazu (QLabel + QPixmap, KeepAspectRatio w resizeEvent z debounce QTimer) / panel info (nazwa, rozmiar, media-type)
   - stan: self._epub: Epub|None (jeden na życie zakładki), self._dirty: dict[str, str], self._current: str|None
   - zmiana pliku przy niezapisanych zmianach: QMessageBox Zapisz/Porzuć/Anuluj
   - Ctrl+S (QShortcut, kontekst WidgetWithChildrenShortcut): dla XHTML/OPF próba lxml.etree.fromstring → błąd ⇒ "Plik nie jest poprawnym XML: …\nZapisać mimo to?"; zapis = epub.write_file(path, text.encode("utf-8")); usuń z _dirty; osobny wskaźnik "EPUB ma niezapisane zmiany"
   - "Zapisz EPUB" = epub.save() (backup .bak jak dotąd), reset wskaźników
   - dekodowanie utf-8 errors="replace"; "\ufffd" ⇒ pasek informacyjny + wymuszony read-only pliku
   - has_unsaved_changes() → MainWindow.closeEvent pyta

5. gui/app.py:
   - EditorTab w QTabWidget (tytuł przez _()), eksport w tabs/__init__.py
   - NOWA METODA MainWindow.open_in_editor(epub_path: Path, internal_path: str|None=None, line: int|None=None) — setCurrentWidget na Edytor + editor_tab.open_external(...) (otwiera EPUB jeśli inny — z obsługą niezapisanych; zaznacza plik; goto_line). PUBLICZNY KONTRAKT dla F-E.

6. Testy:
   - czyste: klasyfikacja plików, helper offset↔(linia,kolumna)
   - pytest-qt: load/get_text roundtrip z polskimi znakami; goto_line; read_only blokuje qtbot.keyClicks; search liczy trafienia; flow: otwórz fixtures/sample.epub → drzewo ma grupy/pliki → edycja xhtml → Ctrl+S → "Zapisz EPUB" → reopen przez Epub → treść zmieniona; plik nie-UTF8 (zbuduj w tmp) → read-only; open_in_editor zaznacza plik i ustawia linię; highlighter nadaje formaty

7. README/user-guide/CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(gui): internal EPUB editor with syntax highlighting (F3 core)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- editor.py < 500 linii: klasyfikację/IO do funkcji modułowych, podgląd obrazu do osobnego widgetu jeśli puchnie.
- QPixmap trzymaj jako atrybut (GC).
- Żadnych hexów w tym etapie — tylko Theme.
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
      - INLINE style="..." z deklaracji przefiltrowanych whitelist'ą podzbioru CSS silnika rich text Qt ("Supported HTML Subset"): font-family, font-size, font-weight, font-style, color, background-color, text-align (justify DZIAŁA), text-indent, line-height, margin-*, padding-*, text-decoration, text-transform; jednostki px/pt/em/% normalizowane; spoza whitelisty → lista nieobsługiwanych
      - celowo inline style, NIE setDefaultStyleSheet z selektorem — omijamy ograniczenia dopasowania selektorów Qt
   e) sample_for_selector(selector) -> (tag_html, text) — h1..h6 → "Rozdział pierwszy"; p/body/klasy → akapit Z POLSKIMI DIAKRYTYKAMI ("Zażółć gęślą jaźń…" + 2 zdania); blockquote/.quote → cytat; code/pre → fragment kodu; inne → akapit
   f) build_preview_html(rule) -> tuple[str, list[str]] — <tag style="...">tekst</tag> w minimalnym dokumencie (escapuj tekst!)

3. gui/widgets/css_inspector.py — CssInspector(QWidget):
   - konstruktor: get_source: Callable[[], str], apply_replacement: Callable[[int,int,str], None] | None (None = read-only, Zastosuj ukryty), theme
   - QSplitter pionowy: (1) QTreeWidget reguł: Selektor | Deklaracje (skrót ~60 zn.) | @media; previewable=False kolorem disabled_fg z Theme; (2) edytor reguły = CodeEditor (css, ~8 linii) z source[span]; (3) podgląd: QTextEdit read-only na "papierowej" białej karcie z ramką 1px {border} — tło NIEZALEŻNE od motywu aplikacji (dark mode nie może fałszować typografii) + QLabel "Nieobsługiwane w podglądzie: …" i stała adnotacja "Podgląd przybliżony — czytnik może różnić się w szczegółach"; (4) "Zastosuj do arkusza" / "Przywróć"
   - LIVE: textChanged edytora reguły → QTimer debounce 300 ms → parse_single_rule → OK: setHtml(build_preview_html(...)) + aktualizacja listy nieobsługiwanych; błąd: ramka {red} + komunikat parsera, podgląd na ostatnim poprawnym
   - Zastosuj: walidacja → apply_replacement(start, end, new_text) → refresh() (re-parse, spany przeliczone, zaznaczenie po selektorze)
   - refresh() także po edycji w GŁÓWNYM edytorze (textChanged + debounce 400 ms)

4. Integracja w gui/tabs/editor.py:
   - dla text/css: CssInspector w prawym QSplitterze, DOMYŚLNIE otwarty, toggle "Inspektor CSS" w toolbarze; dla innych ukryty
   - apply_replacement przez QTextCursor głównego edytora: setPosition(start), setPosition(end, KeepAnchor), insertText(new_text) — JEDNA operacja kursora ⇒ undo cofa całość; plik dostaje "*", standardowy flow Ctrl+S/"Zapisz EPUB"

5. Synergia F11: w sekcji presetów (FixerTab) przycisk "Podgląd…" → QDialog z CssInspector(get_source=lambda: preset.css, apply_replacement=None).

6. Testy — NAJWAŻNIEJSZA część etapu:
   tests/test_css_rules.py (bez Qt):
   - parse_rules: prosta; "h1, h2"; dwie reguły — source[span] zaczyna się selektorem i kończy '}', spany rozłączne; komentarz przed i wewnątrz; content: "}" oraz url("a}b.png") — span poprawny; @media → media!=None; @font-face → previewable=False
   - replace_rule: podmiana środkowej z trzech — tekst poza spanem IDENTYCZNY bajt w bajt
   - declarations_to_preview: test na każdą właściwość whitelisty; jednostki 16px/1.2em/120%; kolory #abc/#aabbcc/rgb()/nazwa; font-weight 700→bold; text-align: justify PRZECHODZI; letter-spacing/hyphens → unsupported; !important → wartość przechodzi + adnotacja
   - sample_for_selector: h1, p, .quote, blockquote, code, "div#x>span" (fallback)
   - build_preview_html: escapuje tekst, zawiera style
   - parse_single_rule: poprawna → CssRuleInfo; "p { color: }" → błędy
   tests/gui/test_css_inspector.py (pytest-qt):
   - otwarcie css w EditorTab → panel widoczny; wybór reguły ładuje edytor reguły
   - edycja "color: red"→"color: blue" + przeskoczenie debounce (qtbot.wait) → toHtml() podglądu zawiera blue
   - "Zastosuj" → get_text() głównego edytora zawiera zmianę; undo (QKeySequence.Undo) ją cofa

7. README/user-guide (opis ograniczeń podglądu!), CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(gui): live CSS rule inspector with QTextDocument preview (F3+)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- tinycss2: source_line/source_column wskazują POCZĄTEK tokenu, 1-indeksowane.
- Nie re-serializuj arkusza tinycss2 — replace_rule po spanie to jedyna ścieżka zapisu.
- Przy ogromnych arkuszach (Calibre) lista reguł może mieć tysiące pozycji — buduj itemy hurtowo (setUpdatesEnabled(False) na czas wypełniania).
```

---

## 👁️ Etap F-P — Podgląd XHTML w edytorze + handoff do Sigil/Calibre

```
EpubForge, rozszerzenie edytora (po F-D): podgląd plików HTML/XHTML w prawym panelu. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-P), gui/tabs/editor.py, gui/widgets/css_inspector.py (funkcja renderująca QTextDocument / build_preview_html + lista nieobsługiwanych), oraz miejsce, gdzie wołane są akcje Sigil/Calibre Editor dla bieżącego EPUB (poszukaj w gui/tabs/). Stringi przez _() + en/de + .mo.

ZADANIE: dla plików HTML/XHTML prawy panel edytora dostaje przełączalny podgląd (Kod ⇄ Podgląd) renderowany silnikiem QTextDocument, z adnotacją o ograniczeniach i przyciskami do pełnego podglądu w Sigil/Calibre. CSS dalej ma inspektor jak teraz — NIE rozpychamy inspektora CSS.

1. main + pull. Gałąź: feature/xhtml-preview

2. gui/widgets/html_preview.py — HtmlPreview(QWidget):
   - QTextBrowser (lub QTextEdit) read-only renderujący XHTML przez QTextDocument.setHtml
   - OBRAZKI: względne src rozwiązywane z otwartego Epub. Preferuj przepisanie <img src> na data: URI z bajtów Epub (bezstanowe, odporne); pliki > ~3 MB → placeholder z nazwą pliku zamiast base64 (żeby dokument nie puchł). Alternatywa (jeśli wolisz): QTextDocument z nadpisanym loadResource czytającym z Epub — wybierz prostsze, data: URI jest OK.
   - pasek adnotacji na górze: _("Podgląd przybliżony (silnik Qt) — nie pokazuje pełnego CSS, fontów osadzonych ani układu czytnika. Pełny podgląd:") + przyciski [Sigil] [Calibre Editor] reużywające istniejące akcje (przekaż bieżący plik/EPUB); tooltipy
   - opcjonalnie pod podglądem lista nieobsługiwanych aspektów (reużyj z css_inspector jeśli tanie); jeśli niełatwe — sama ogólna adnotacja wystarczy
   - tło "papierowe" białe NIEZALEŻNE od motywu aplikacji (jak podgląd inspektora), 1px ramka border z Theme
   - API: set_content(xhtml_text: str, epub, internal_path) + set_epub_context(...) — tak, by obrazki i przyciski znały bieżący plik

3. gui/tabs/editor.py:
   - dla media_type text/html i application/xhtml+xml: w prawym panelu przełącznik "Kod / Podgląd" (QTabBar albo dwa toggle-buttony), DOMYŚLNIE Kod (duch quick-fix)
   - podgląd odświeżany z BIEŻĄCEJ treści edytora: po przełączeniu na Podgląd oraz z debounce ~400 ms gdy Podgląd aktywny i tekst się zmienia → pokazuje niezapisane zmiany
   - podgląd zawsze read-only, spójny z trybem edycji (gdy tryb podglądu/edycji z F-C — podgląd HTML nie zależy od niego, ale nie może pozwalać na edycję)
   - przyciski Sigil/Calibre w pasku podglądu działają na AKTUALNYM pliku/EPUB
   - CSS bez zmian (inspektor), inne typy bez zmian

4. Reużycie: jeśli renderowanie/escaping da się wyciągnąć ze css_inspector do wspólnego modułu (gui/widgets/preview_common.py lub w fixers/) bez rozdmuchania zmian — zrób to; inaczej zostaw osobno.

5. Testy (pytest-qt + czyste):
   - render XHTML z <img src="rel.png"> → wynikowy HTML zawiera obrazek jako data: URI z bajtów Epub (fixture); obraz > 3 MB → placeholder, nie base64
   - przełącznik Kod/Podgląd zmienia widok; edycja kodu + przełączenie na Podgląd odświeża treść
   - przyciski Sigil/Calibre wołane z właściwą ścieżką (mock akcji)
   - tło podglądu niezależne od motywu (sprawdź po apply dark/light)

6. README/user-guide (sekcja edytora: podgląd + jego ograniczenia + handoff), CHANGELOG (Added). pytest, ruff --fix, mypy.
7. Commit: "feat(gui): approximate XHTML preview with handoff to Sigil/Calibre"
8. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- QTextDocument nie wykona JS ani złożonego CSS — to świadome; adnotacja ma to jasno mówić.
- data: URI dla dużych PNG puchnie — limit rozmiaru + placeholder.
- Przyciski Sigil/Calibre: reużyj ISTNIEJĄCE akcje, nie duplikuj logiki uruchamiania narzędzi.
```

---

## ✅ Etap F-E — F2: Walidacja EpubCheck

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-E). Przeczytaj AKTUALNY stan: core/detection.py (Tool/Tools/cache/overrides), core/config.py (config_dir z F-S), gui/workers.py, gui/widgets/file_list.py, gui/tabs/fixer.py (wzorzec taba), gui/app.py (open_in_editor z F-C). Stringi przez _() + en/de + .mo.

ZADANIE: walidacja EPUB przez EpubCheck 5.x (java -jar): detekcja narzędzi, parser raportu JSON, CLI `epubforge check`, zakładka GUI z klikalnymi błędami skaczącymi do edytora.

1. main + pull. Gałąź: feature/f2-epubcheck

2. core/detection.py — dwa narzędzia wg wzorca istniejących:
   - Tools.java(): PATH, JAVA_HOME/bin, %ProgramFiles%/Eclipse Adoptium/*/bin, /usr/bin; wersja: `java -version` pisze na STDERR — parsuj stderr, wyciągnij major (formaty "17.0.x" i "1.8.0_xx"); available wymaga major >= 11
   - Tools.epubcheck(): ścieżka do epubcheck.jar w kolejności: (1) config override tools.epubcheck_jar, (2) glob %ProgramFiles%/epubcheck*/epubcheck*.jar i ~/epubcheck*/, (3) config_dir()/"epubcheck"/"epubcheck.jar", (4) katalog exe (frozen); wersja z META-INF/MANIFEST.MF jara (zipfile, Implementation-Version) — bez uruchamiania javy
   - oba w detect_with_cache i _apply_overrides

3. validators/__init__.py + validators/epubcheck.py — wg ROADMAP §F-E:
   - Severity, ValidationMessage(severity, code, message, internal_path, line, column), ValidationReport(epub_path, valid, epubcheck_version, messages, duration_s, counts())
   - run_epubcheck(epub_path, java, jar, timeout=300): [java.path, "-jar", jar, str(epub_path), "--json", tmp_json] w tempfile.TemporaryDirectory, CREATE_NO_WINDOW, text=True, encoding="utf-8", errors="replace", timeout
   - exit != 0 przy istniejącym poprawnym JSON = raport valid=False (NIE wyjątek); brak/zepsuty JSON lub timeout = EpubforgeError ze stderr
   - parser defensywny: messages[] → severity (lower; mapuj USAGE/SUPPRESSED), ID, message, locations[0].{path,line,column} przez get(); path normalizuj do ścieżki WEWNĘTRZNEJ (utnij wszystko do "*.epub/" włącznie); brak locations → internal_path=None
   - epubcheck_version z checker.checkerVersion

4. cli/check.py: `epubforge check book.epub [--json out.json] [--min-severity warning]`; wypis: liczby per severity + lista "ścieżka:linia [KOD] treść"; exit 0 valid / 1 błędy / 2 brak narzędzi (z instrukcją jak w pkt 5). Rejestracja w main.py.

5. gui/tabs/validator.py — zakładka "Walidacja":
   - FileList (D&D), "Sprawdź zaznaczony" → Worker (QThread), status
   - pasek podsumowania "✗ N błędów · ⚠ N ostrzeżeń · ℹ N informacji" (ngettext!)
   - filtry severity (QCheckBox x3) + QTreeWidget: Poziom | Kod | Plik:linia | Komunikat (kolory wierszy z ról Theme: red/amber/fg2; pełny komunikat w setToolTip; dane internal_path/line w setData(Qt.UserRole), nie parsowane z tekstu)
   - DWUKLIK wiersza z internal_path → main_window.open_in_editor(epub_path, internal_path, line) — referencję main_window przekaż przy konstrukcji
   - "Eksport…" → JSON (dataclasses.asdict) lub HTML (samowystarczalna tabela)
   - gdy java/jar niedostępne: panel pomocy zamiast wyników — instrukcja (Temurin 17+, epubcheck z W3C GitHub releases) + "Wskaż epubcheck.jar…" (file_dialogs → config["tools"]["epubcheck_jar"] przez mark_dirty → re-detekcja → odśwież)
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
```

---

## 📑 Etap F-F — F10: Generator i edytor spisu treści

```
Pracujemy nad EpubForge. Przeczytaj CLAUDE.md, ROADMAP_FEATURES_v1.1.md (sekcja F-F). Przeczytaj AKTUALNY stan: core/epub.py, core/metadata.py (identifier do NCX), fixers/css_fixer.py (OPF przez lxml). Stringi przez _() + en/de + .mo.

ZADANIE: pakiet toc/ (model, reader, generator, writer, repair) + CLI `epubforge toc` + zakładka GUI z edycją drzewa (natywny drag&drop QTreeWidget).

1. main + pull. Gałąź: feature/f10-toc

2. src/epubforge/toc/ wg ROADMAP §F-F:
   - model.py: TocEntry(title, href, children) + CZYSTA funkcja move_entry(entries, src, dst, mode: "before"|"after"|"into") — w tym zakaz przeniesienia do własnego potomka; model pod D&D, z pełnymi testami
   - reader.py: read_toc(epub) → (entries, source) — nav.xhtml (item z properties zawierającym "nav", <nav epub:type="toc">, zagnieżdżone ol/li/a) z fallbackiem do toc.ncx (navMap/navPoint)
   - generator.py: generate_toc(epub, max_level=3) — spine W KOLEJNOŚCI, lxml z recover; h1..h{max_level}; drzewo wg poziomów (osierocony h3 bez h2 → poziom wyżej); tytuł = " ".join(itertext()).split() joined; nagłówek bez id → wstrzyknij id="efh-NNNN" (licznik per plik, sprawdź kolizje) i zapisz przez epub.write_file Z ZACHOWANIEM deklaracji XML i doctype; PIERWSZY nagłówek pliku → href bez fragmentu; plik bez nagłówków pomijany; IDEMPOTENCJA drugiego przebiegu
   - writer.py: write_toc(epub, entries, write_nav=True, write_ncx=True) — nav.xhtml: jeśli istnieje, podmień TYLKO <nav epub:type="toc">; jeśli nie, pełny dokument pod {opf_dir}/nav.xhtml (xmlns + xmlns:epub="http://www.idpf.org/2007/ops") + manifest properties="nav" (spine NIETKNIĘTY); toc.ncx: pełna regeneracja (uid z metadata, playOrder DFS) + manifest + atrybut toc= w <spine> jeśli brak; href w nav względne do nav.xhtml, w ncx do ncx — posixpath.relpath, nie zakładaj wspólnej bazy
   - repair.py: validate_toc(epub, entries) → list[TocProblem(href, reason)] (href nie istnieje / fragment nie istnieje — cache zbioru id per plik); repair_toc usuwa martwe (dzieci podciąga), zwraca (entries, removed)

3. cli/toc.py: `epubforge toc book.epub --show | --generate [--max-level 3] [--output out.epub] | --repair [--dry-run]`; --show drukuje drzewo z wcięciami; rejestracja w main.py.

4. gui/tabs/toc.py — zakładka "Spis treści":
   - PathEntry → read_toc → QTreeWidget (Tytuł | Cel); wpisy z problemami (validate_toc przy wczytaniu) kolorem red z Theme + tooltip z powodem
   - toolbar: Generuj (QSpinBox max-level 1–6 + potwierdzenie nadpisania), Napraw (QDialog z listą problemów → potwierdź), Dodaj, Usuń, ⬆ ⬇ (rodzeństwo), ⬅ ➡ (outdent/indent), "Zapisz do EPUB"
   - edycja tytułu: Qt.ItemIsEditable TYLKO na kolumnie tytułu; itemChanged aktualizuje model (blockSignals(True) podczas programowej przebudowy!)
   - drag&drop: setDragDropMode(QAbstractItemView.InternalMove), setDefaultDropAction(MoveAction); w dropEvent ZSYNCHRONIZUJ model: wyznacz src/dst/tryb (dropIndicatorPosition: OnItem→"into", AboveItem→"before", BelowItem→"after"), wywołaj move_entry na modelu i PRZEBUDUJ widok z modelu (mapowanie item↔entry słownikiem); wydziel handler przyjmujący (src, dst, tryb) — testowalny bez symulacji DnD
   - "Zapisz do EPUB": write_toc + epub.save(); wskaźnik niezapisanych zmian; pytania przy zmianie pliku/zamknięciu
   - rejestracja w app.py i tabs/__init__.py

5. Fixtures: rozbuduj tests/fixtures/make_sample_epub.py o make_toc_epub(tmp): ch1 (h1 + dwa h2, jeden h2 z <em> w środku, bez id), ch2 (h1 bez id + osierocony h3), ch3 (bez nagłówków, z <title>); prosty nav.xhtml z jednym MARTWYM wpisem.

6. Testy:
   - generator: struktura drzewa (poziomy, osierocony h3), tytuł z <em> sklejony, polskie znaki, pierwszy nagłówek bez fragmentu, id unikalne, idempotencja, plik bez nagłówków pominięty
   - writer→reader roundtrip (nav i ncx); nav w manifeście z properties="nav"; ncx w spine@toc; EPUB po save zdrowy (mimetype pierwszy, ZIP_STORED)
   - repair: martwy href i zły fragment wykryte; usunięcie podciąga dzieci
   - move_entry: before/after/into + zakaz przeniesienia do potomka
   - CLI --show/--generate/--repair --dry-run (capsys, kopie fixture w tmp)
   - pytest-qt: wczytanie, generacja podmienia drzewo, edycja tytułu przez itemChanged trafia do modelu, zapis; przeniesienie przez wydzielony handler

7. README/user-guide/CHANGELOG. pytest, ruff --fix, mypy.
8. Commit: "feat(toc): TOC generator, repair and tree editor (F10)"
9. Zaproponuj push i PR. NIE pushuj automatycznie.

PUŁAPKI:
- lxml.etree.tostring gubi doctype bez doctype= z parsera — XHTML w EPUB często ma DOCTYPE.
- epub:type wymaga xmlns:epub.
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

5. GUI ConverterTab: rozszerz filtry (helper file_dialogs) i walidację rozszerzeń; plik Kindle → wybór silnika zablokowany na Calibre + etykieta informacyjna; DRM → QMessageBox.warning (nie traceback w logu).

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
   - tokenizacja: re.findall(r"\w+", text, re.UNICODE); odfiltruj czyste liczby
   - język: try-import langdetect wewnątrz funkcji (DetectorFactory.seed = 0 — bez seeda niedeterministyczny; próbka 10000 znaków) → fallback metadata.language (kod 2-literowy) → None; zapisz language_source
   - top-słowa: lower(), stop-lista wg języka, Counter.most_common z tie-breakiem alfabetycznym
   - stop-listy: src/epubforge/stats_stopwords/{pl,en,de}.txt (200-300 słów funkcyjnych, po jednym na linię, lowercase, UTF-8); loader z cache
   - render_report_html: samowystarczalny HTML (inline CSS w JASNEJ palecie z GUI_STANDARD §5; kolory tekstowe akcentu = accent2 #0F7C5B — nota WCAG; ZERO zasobów sieciowych), html.escape NA KAŻDEJ wartości z książki; sekcje: nagłówek (tytuł/autor z Metadata), karty liczb, chmurka top-słów (span, font-size log-skala 12-40 px), tabela rozdziałów, wykres słupkowy jako inline SVG własną funkcją _bar_chart_svg(values, labels) (max 60 słupków, powyżej agreguj), stopka "Wydrukuj do PDF: Ctrl+P" + wersja EpubForge

4. cli/stats.py: `epubforge stats book.epub [--report out.html] [--top 50] [--words-per-page 250] [--wpm 200]` — podsumowanie + top 20; rejestracja w main.py.

5. gui/tabs/stats.py — zakładka "Statystyki": PathEntry → "Oblicz" → Worker → karty (Section: słowa, szac. strony, czas h:min, język + źródło), QListWidget top-słów, QTreeWidget rozdziałów (tytuł, słowa), "Eksport HTML…" (file_dialogs) i "Otwórz raport" (zapis tmp + webbrowser.open). Brak langdetect → adnotacja "język z metadanych (zainstaluj epubforge[stats])". Rejestracja w app.py i tabs/__init__.py.

6. Build/packaging: stats_stopwords do wheel i datas .spec + check_build_env.py.

7. Testy (tests/test_stats.py):
   - compute_stats na fixtures/sample.epub: deterministyczne liczby (oczekiwane policz w teście z treści fixture)
   - "Zażółć gęślą jaźń" = 3 słowa; liczby odfiltrowane; stop-lista pl filtruje "i", "w", "się"
   - fallback języka: monkeypatch importu langdetect na ImportError → language_source="metadata"
   - top_words: sort malejąco, remis alfabetycznie, top_n respektowane
   - raport: zawiera tytuł książki; "<b>złośliwy</b>" w tytule rozdziału zescapowany; liczba <rect> w SVG = liczba rozdziałów (≤60); brak "http" w treści
   - CLI: exit 0 + plik raportu powstaje (tmp)
   - pytest-qt: smoke — zakładka liczy na fixture (logika synchronicznie) i wypełnia karty

8. README (Statystyki + extra [stats]), user-guide, CHANGELOG.
9. pytest, ruff --fix, mypy. Commit: "feat(stats): book statistics with HTML report (F8)"
10. Zaproponuj push i PR. NIE pushuj automatycznie.
```

---

## 📌 Przypomnienie globalne (dotyczy każdego promptu)

- Komentarze i docstringi po polsku, identyfikatory po angielsku, mypy --strict, pliki < 500 linii.
- GUI: wyłącznie PySide6; kolory TYLKO przez role i stany `Theme` z theme.py (hexy żyją wyłącznie tam — GUI_STANDARD v2.0 §4); rozmiary fontów w pt; długie operacje przez Worker/QThread + sygnały; dialogi plików przez helper file_dialogs; zapis configu przez mark_dirty (debounce w GUI); tooltipy na elementach interaktywnych.
- Od etapu F-A każdy nowy string użytkownika przez `_()` + aktualizacja `.po` en/de + `build/compile_locales.py`.
- Po etapie: podsumowanie, `git status`, propozycja `git push -u origin HEAD` i `gh pr create` — **bez wykonywania**.
- Merge zawsze: `gh pr merge --squash --delete-branch`.
