# 🎨 GUI Standard — przewodnik budowy aplikacji desktopowych

> Prywatny standard budowy GUI dla projektów (chodzkos).
> Punkt odniesienia dla wszystkich aplikacji i dla Claude Code.
> Dwa tory technologiczne, wspólne zasady wyglądu i zachowania.

---

## 1. Cel dokumentu

Każda aplikacja desktopowa, którą buduję (IcoForge, EpubForge, kolejne), nie powinna wymyślać GUI od nowa. Ten dokument definiuje:

- **kiedy** używać którego frameworka (tkinter vs Qt),
- **jak** ma wyglądać GUI (kolory, układ, typografia) — niezależnie od frameworka,
- **jakie** komponenty i zachowania są wspólne,
- **co** musi się znaleźć w każdej aplikacji (config, motyw, „o programie").

Efekt: aplikacje są rozpoznawalnie „moje", a nowy projekt startuje z gotowych wzorców zamiast od zera.

---

## 2. Wybór frameworka — kryterium decyzyjne

Dwa tory, świadomie utrzymywane oba. Wybór na **starcie** projektu, bo zmiana później jest kosztowna.

### Tabela decyzyjna

| Pytanie | Jeśli TAK → |
|---|---|
| Czy to małe narzędzie (1-3 ekrany, prosta logika)? | tkinter |
| Czy zależy mi na minimalnym rozmiarze .exe (<25 MB)? | tkinter |
| Czy ciemny motyw musi być idealny (dialogi, menu, paski)? | **Qt** |
| Czy potrzebuję bogatych widgetów (tabele, drzewa, podgląd, docki)? | **Qt** |
| Czy aplikacja będzie rosła przez miesiące/lata? | **Qt** |
| Czy ma wyglądać profesjonalnie „od pierwszego dnia"? | **Qt** |
| Czy to szybki prototyp / proof-of-concept? | tkinter |

### Reguła kciuka

> **Domyślnie Qt.** tkinter tylko świadomie — gdy mały rozmiar i zero zależności są ważniejsze niż wygląd.

Powód: największy ból tkinter (jasne natywne dialogi i menu w trybie ciemnym) jest **strukturalny i nie do obejścia**. W Qt nie istnieje. Jeśli aplikacja ma mieć dopracowany ciemny motyw, tkinter jest ślepą uliczką od startu.

### Mapa istniejących projektów

| Projekt | Tor | Uzasadnienie |
|---|---|---|
| IcoForge | Qt | dopracowany motyw, edytor pikseli, bogate UI |
| EpubForge | tkinter (rozważyć migrację po v1.0) | start jako lekkie narzędzie; ciemny motyw okazał się problematyczny |
| Kolejne | domyślnie Qt | spójność, mniej walki z wyglądem |

---

## 3. Tor A — tkinter

### Kiedy
Małe narzędzia, prototypy, sytuacje gdzie liczy się mały `.exe` i zero zależności.

### Stack
- Python 3.10+ (na czas dev używaj 3.12 — najszersza zgodność bibliotek)
- `tkinter` + `ttk` (wbudowane)
- `tkinterdnd2` — drag&drop (opcjonalne)
- `darkdetect` — wykrywanie motywu systemu
- motyw: ręczny słownik kolorów + `apply_theme()` rekurencyjnie

### Mocne strony
- zero instalacji, wbudowany w Pythona
- mały `.exe` (~15-25 MB)
- szybki start

### Ograniczenia (znać przed wyborem!)
| Ograniczenie | Obejście |
|---|---|
| Natywne dialogi plików zawsze jasne | brak prostego — albo akceptujesz, albo piszesz własne Toplevel |
| `tk.Menu` częściowo ignoruje motyw | da się przyciemnić pozycje, obwódka systemowa zostaje |
| Pasek tytułu wymaga ręcznego DWM + refresh | `GetParent(winfo_id())` + WM_NCACTIVATE |
| Siermiężny wygląd domyślny | ttk + ręczna stylizacja |
| `tkinterdnd2` w PyInstaller gubi tkdnd | jawny hook w `.spec` |

### Pułapki techniczne
- **HWND paska tytułu:** `winfo_id()` zwraca uchwyt *dziecka*. Prawdziwa ramka: `ctypes.windll.user32.GetParent(window.winfo_id())`.
- **Refresh paska na Win10:** sam atrybut DWM nie wystarcza — wyślij `WM_NCACTIVATE` (0→1) + `SetWindowPos(SWP_FRAMECHANGED)`.
- **Timing:** stosuj ciemny pasek po pełnym zmapowaniu okna (`after(10, ...)` lub przed pierwszym `deiconify`).
- **Pozostałości motywu:** `apply_theme` musi rekurencyjnie kolorować KAŻDY widget (Listbox, Text, Canvas), inaczej zostają plamy starego motywu.

---

## 4. Tor B — PySide6/Qt

### Kiedy
Aplikacje docelowe, większe projekty, wszystko gdzie ciemny motyw i wygląd mają znaczenie. **Domyślny wybór.**

### Stack
- Python 3.10+
- `PySide6` (LGPL — zgodne z MIT)
- `pyqtdarktheme` (`qdarktheme`) — motyw jedną linią
- DWM titlebar przez `ctypes` (jak w tkinter, ale HWND z `window.winId()` działa wprost)
- motyw: `qdarktheme.setup_theme("auto"|"dark"|"light")`

### Mocne strony
- natywny, nowoczesny wygląd
- ciemny motyw bezproblemowy (też dialogi przez `DontUseNativeDialog`)
- bogate widgety (QTableWidget, QTreeView, QDockWidget, QWebEngineView)
- system sygnałów/slotów — czysty event handling
- menedżery layoutów — responsywne UI

### Ograniczenia
- większy `.exe` (~50-120 MB)
- stromsza krzywa nauki
- dodatkowa zależność (~100 MB przy instalacji)

### Pułapki techniczne (z IcoForge)
- **Jasny motyw qdarktheme** jest „wyprany" — dla trybu jasnego przywróć natywny styl Qt zamiast `qdarktheme("light")` (zapamiętaj `app.style()`, `app.palette()`, `app.styleSheet()` przed pierwszą zmianą).
- **Pasek tytułu Win10:** `DwmSetWindowAttribute(20)` + `WM_NCACTIVATE` + `RedrawWindow(RDW_FRAME)`. `winId()` woła w `showEvent`, nie `__init__`.
- **Dialog odbiera focus → główny pasek jaśnieje:** nadpisz `changeEvent` na `ActivationChange` i ponownie wymuś ciemny pasek.
- **Repaint pozostałości motywu:** `style.unpolish()/polish()` na `app.allWidgets()`.
- **Hardcoded kolory:** używaj ról palety (`palette(base)`, `palette(text)`), nie sztywnych hexów — inaczej nie zmieniają się z motywem.

---

## 5. Wspólne zasady wyglądu (oba tory)

Niezależnie od frameworka — to definiuje „mój styl".

### Paleta kolorów

**Ciemny motyw (podstawowy):**
```
bg       #1e2028   tło główne
bg2      #252830   tło sekcji / paneli
bg3      #2d3040   tło pól / inputów
fg       #dde1ec   tekst główny
fg2      #8b90a7   tekst drugorzędny
fg3      #555a70   tekst wyciszony / hinty
accent   #5DCAA5   akcent (główny, jasny)
accent2  #1D9E75   akcent (ciemniejszy, przyciski)
border   #383c50   ramki / separatory
red      #e25454   błędy / akcje destrukcyjne
amber    #EF9F27   ostrzeżenia
```

**Jasny motyw:**
```
bg       #ffffff
bg2      #f5f5f7
bg3      #e8e8ed
fg       #1d1d1f
fg2      #515154
fg3      #86868b
accent   #1D9E75
accent2  #0F7C5B
border   #d1d1d6
red      #d70015
amber    #b25000
```

> Akcent `#5DCAA5 / #1D9E75` (zielony) to znak rozpoznawczy — używaj go we wszystkich aplikacjach dla spójności marki.

### Typografia
- **Font UI:** systemowy domyślny (TkDefaultFont / Qt default) — natywny wygląd
- **Font monospace** (kod, ścieżki, logi): Consolas / Menlo / DejaVu Sans Mono
- **Rozmiary:** tytuł ~13pt bold, sekcje ~9pt bold, treść ~9pt, hinty ~7-8pt
- **Nie** mieszać wielu krojów — UI font + mono font wystarczą

### Odstępy i kształty
- padding sekcji: 10-12px
- odstęp między elementami: 6-8px
- zaokrąglenia: subtelne (Qt: border-radius 4-8px; tkinter: brak natywnych, flat)
- ramki: cienkie (0.5-1px), kolor `border`
- relief: `flat` wszędzie gdzie się da (unikać wytłoczeń „3D")

### Ikonografia
- akcent destrukcyjny (usuń) → `red`
- ostrzeżenia → `amber`
- sukces/akcja główna → `accent`
- ikony spójne w obrębie aplikacji (jeden zestaw)

---

## 6. Wspólne wzorce układu

Gdzie co się znajduje — żeby każda aplikacja była rozpoznawalna.

### Górny pasek (lekki)
```
┌─────────────────────────────────────────────────────────┐
│ [logo] NazwaApp          [przełącznik motywu] [ⓘ About]  │
└─────────────────────────────────────────────────────────┘
```
- po lewej: logo + nazwa aplikacji
- po prawej: dyskretny przełącznik motywu (auto/jasny/ciemny) + mała ikona „O programie"
- **meta-rzeczy (motyw, info) NIE są dużymi zakładkami** — siedzą w lekkim górnym pasku

### Zakładki funkcji (Notebook / QTabWidget)
- TYLKO dla funkcji roboczych (np. Metadane, Konwerter, Fixer)
- nie mieszać z meta-funkcjami (motyw, about)

### Panel dolny / status
- pasek statusu z wykrytymi narzędziami / stanem
- log z kolorowaniem (ok/warn/err) przy operacjach długich
- pasek postępu dla operacji wsadowych
- przyciski akcji (Uruchom / Zatrzymaj) w stałym miejscu

### Listy plików
- toolbar: Dodaj pliki / Dodaj folder / Usuń / Wyczyść
- licznik plików
- drag&drop jeśli dostępny (z fallbackiem gdy brak)

### Pola ścieżek
- pole tekstowe + przycisk „…" otwierający dialog
- placeholder podpowiadający format

---

## 7. Komponenty wielokrotnego użytku

Biblioteka widgetów do reużycia w każdym projekcie. Docelowo: prywatny pakiet `chodzkos-gui-kit` (osobno dla tkinter i Qt).

| Komponent | Rola | tkinter | Qt |
|---|---|---|---|
| `ThemeManager` | motyw auto/jasny/ciemny + persist | słownik + apply_theme | qdarktheme + native light |
| `set_titlebar_dark` | ciemny pasek tytułu Windows | GetParent(winfo_id) | winId() |
| `PathEntry` | pole + przycisk wyboru | tk.Frame | QWidget |
| `FileList` | lista plików z toolbar + D&D | tk.Listbox | QListWidget |
| `Toggle` | stylizowany checkbox | tk.Checkbutton | QCheckBox |
| `Tooltip` | podpowiedź reagująca na motyw | Toplevel | QToolTip / custom |
| `Section` | sekcja z tytułem | ttk.LabelFrame | QGroupBox |
| `LogStreamer` | strumień subprocess → log | kolejka + after | QThread + signal |
| `AboutPanel` | logo, wersja, linki | Frame | QWidget |

> Zasada: komponent piszesz RAZ, potem importujesz. Nie przepisywać między projektami.

---

## 8. Wspólne zachowania

Każda aplikacja MUSI mieć:

### Konfiguracja
- `config.json` (lub `.toml`) w `~/.config/<app>/` (dev) lub obok exe (portable)
- zapis atomowy (tmp + replace)
- zapamiętuje: motyw, ostatnie katalogi, presety, ustawienia okna
- wczytywany przy starcie, zapisywany przy zamknięciu

### Motyw
- tryb auto/jasny/ciemny, wybór zapamiętany
- auto = śledzi system (`darkdetect` lub `styleHints`)
- ciemny pasek tytułu na Windows
- wszystkie okna (główne + dialogi) spójne

### Domyślne ścieżki
- katalog wyjściowy domyślnie = katalog pliku źródłowego
- ostatni użyty katalog jako fallback (z config)
- nie nadpisywać ręcznego wyboru użytkownika

### Obsługa błędów
- błędy w okienku (nie ciche zniknięcie)
- przy aplikacji bez konsoli: zapis błędu do pliku (`error.txt`)
- `logging` zamiast `print` w kodzie biblioteki

### Subprocess (jeśli woła zewnętrzne narzędzia)
- `CREATE_NO_WINDOW` na Windows (brak migającego CMD)
- timeout na wywołaniach
- streaming output do logu w GUI
- encoding utf-8 + errors="replace"

### „O programie"
- logo (ładowane warunkowo, placeholder gdy brak)
- nazwa + wersja (czytana z `__version__`, nie hardcoded)
- link do GitHub + link do pomocy (przez `webbrowser.open`)
- licencja

---

## 9. Build i dystrybucja

### Oba tory: PyInstaller
- **portable:** `--onefile` → jeden `.exe`, zero instalacji
- **instalator:** `--onedir` + Inno Setup → setup.exe ze skrótami
- ikona z `assets/icon.ico`
- `console=False` (aplikacja GUI)

### Pułapki
- tkinter: hook `tkdnd` dla tkinterdnd2 w `.spec`
- Qt: PySide6 plugins (platforms, styles) zwykle wykrywane automatycznie, ale sprawdź rozmiar
- DLL conflict (python3xx.dll) — izolacja przy wywołaniach subprocess
- assets (logo, ikona) w `datas`, ładowane przez `sys._MEIPASS` w bundlu

### CI/CD
- GitHub Actions: build na `windows-latest` przy tagu `v*`
- Release z oboma plikami (portable + instalator)
- testy + lint + mypy na każdym push

---

## 10. Checklista nowego projektu GUI

Przy starcie nowej aplikacji:

```
[ ] Wybrano tor (tkinter / Qt) wg tabeli decyzyjnej z sekcji 2
[ ] Struktura: core/ (logika, bez GUI) + gui/ + cli/ + tests/
[ ] pyproject.toml + ruff + mypy + pytest
[ ] config.json mechanism (sekcja 8)
[ ] ThemeManager z auto/jasny/ciemny (paleta z sekcji 5)
[ ] Ciemny pasek tytułu Windows
[ ] Górny pasek wg układu z sekcji 6 (logo + motyw + about)
[ ] Komponenty z gui-kit (sekcja 7) zamiast pisać od zera
[ ] Tooltipy na wszystkich interaktywnych elementach
[ ] Domyślne katalogi = katalog źródłowy
[ ] Obsługa błędów w okienku + error.txt
[ ] Zakładka/panel "O programie" z wersją i linkami
[ ] Build: portable + instalator
[ ] CI/CD: testy + build przy tagu
[ ] CLAUDE.md z zasadami projektu + pułapkami
```

---

## 11. Decyzja o migracji istniejącego projektu

Kiedy przenosić tkinter → Qt:

**Migruj, gdy:**
- ciemny motyw musi być dopracowany (dialogi, menu)
- aplikacja będzie się rozwijać długoterminowo
- użytkownicy zgłaszają wygląd jako problem

**Zostaw w tkinter, gdy:**
- aplikacja działa i jest „skończona"
- mały rozmiar .exe to atut
- jasne dialogi to akceptowalna kosmetyka

**Jak migrować (jeśli decyzja na TAK):**
- TYLKO po osiągnięciu działającej wersji (nie w trakcie budowy funkcji)
- warstwa `core/` zostaje bez zmian (dlatego rozdzielamy core od gui!)
- przepisujesz tylko `gui/`, `cli/` i `core/` działają dalej
- osobny, świadomy refactor — nie miesza się z nowymi funkcjami

> To główny powód, dla którego **zawsze** trzymamy logikę w `core/` oddzielonej od GUI: migracja frameworka dotyka tylko warstwy prezentacji.

---

*Dokument żywy — aktualizuj w miarę jak wypracowujesz kolejne wzorce.*
