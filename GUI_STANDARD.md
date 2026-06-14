# 🎨 GUI Standard — przewodnik budowy aplikacji desktopowych

> Prywatny standard budowy GUI dla projektów (chodzkos).
> Punkt odniesienia dla wszystkich aplikacji i dla Claude Code.
> Dwa tory technologiczne, wspólne zasady wyglądu i zachowania.

**Ostatnia rewizja:** 2026-06-14 · **Wersja:** 2.7
*(wersje 2.0–2.7 powstały w jednej sesji przeglądowej 2026-06-14; przyszłe edycje datować per zmiana)*

| Wersja | Zmiany |
|---|---|
| 2.7 | sekcja Ikonografia rozszerzona: zestaw Lucide (ISC) / Tabler (MIT) kopiowany do repo; mechanizm przebarwialnych SVG `get_icon()` z podmianą currentColor wg palety + cache + clear na theme_changed (powód: NIE statyczne PNG); ICON_MAP; zasada „nazwa→tooltip+setText"; audyt tooltipów. Komponent IconProvider w §7 (z IcoForge feat/icon-system) |
| 2.6 | KOREKTA fallbacku toolbara: prawdziwa przyczyna pustych przycisków to przeciekający app-QSS `QToolButton{padding/border}` przycinający przypięty ~22px przycisk — NIE brak ikon. Fix: per-widget QSS zdejmujący padding/border (wyższa specyficzność) + standardIcon gdy pusta; PORZUCONO wymuszanie etykiet (nie mieszczą się w 22px). Test geometryczny size vs sizeHint (działa offscreen) |
| 2.5 | KOREKTA reguły belki: DWM ustawiany BEZWARUNKOWO = motyw app przy każdym apply() (atrybut DWM jest stanowy — „nic nie rób przy zgodności" zostawiało starą wartość → belka zamrożona; usterka po F-C); nota o timingu labelingu toolbara (po setOption, przed exec) |
| 2.4 | fallback QFileDialog: wymuszenie ikon+etykiet na przyciskach toolbara (back/forward/toParent/newFolder przez objectName) — przy custom QSS bywają puste, zostaje sam tooltip |
| 2.3 | zmiana motywu w locie: QSS regenerowany przy każdym apply() (zakaz cache'owania stringa z hexami), jawne QToolTip.setPalette() — elementy statyczne Qt nie podążają za app.setPalette() (usterka z EpubForge F-A) |
| 2.2 | dialog fallback: jawny binarny trade-off przy rozjeździe + standard konfiguracji nienatywnego QFileDialog (sidebar, Detail, rozmiar, instancyjne API); odrzucona opcja „zawsze natywne" z warunkiem rewizji |
| 2.1 | symetryczna reguła rozjazdu motywów (dialogi natywne I pasek tytułu — oba kierunki, nie tylko app dark + system light); odczyt motywu systemu przy otwarciu dialogu; update() po re-aplikacji motywu (usterka z EpubForge F-S) |
| 2.0 | usunięcie qdarktheme (projekt porzucony) → własny theme.py; platformdirs; stany palety; pułapki PyInstaller+Qt; niuanse DWM/Qt 6.5+ |
| 1.0 | wersja pierwotna (przed sesją przeglądową) |

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
| EpubForge | Qt (migracja z tkinter po v1.0) | start jako lekkie narzędzie; ciemny motyw wymusił migrację na PySide6 |
| Kolejne | domyślnie Qt | spójność, mniej walki z wyglądem |

---

## 3. Tor A — tkinter

### Kiedy
Małe narzędzia, prototypy, sytuacje gdzie liczy się mały `.exe` i zero zależności.

### Stack
- Python 3.10+ (na czas dev używaj 3.12 — najszersza zgodność bibliotek)
- `tkinter` + `ttk` (wbudowane)
- `tkinterdnd2` — drag&drop (opcjonalne)
- `darkdetect` — wykrywanie motywu systemu (tkinter nie ma styleHints)
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
- **darkdetect.listener:** blokuje wątek — uruchamiaj jako wątek daemon, inaczej aplikacja nie zamknie się czysto.

---

## 4. Tor B — PySide6/Qt

### Kiedy
Aplikacje docelowe, większe projekty, wszystko gdzie ciemny motyw i wygląd mają znaczenie. **Domyślny wybór.**

### Stack
- Python 3.10+
- `PySide6` (LGPL — zgodne z MIT)
- motyw: własny `theme.py` z gui-kit (paleta z sekcji 5 → QPalette + generowany QSS)
  — żadnej zewnętrznej biblioteki motywów
- auto-detekcja motywu systemu: `QGuiApplication.styleHints().colorScheme()`
  + sygnał `colorSchemeChanged` (Qt 6.5+; darkdetect zbędny w torze Qt)
- DWM titlebar przez `ctypes` (HWND z `window.winId()`) — tylko gdy motyw aplikacji ≠ motyw systemu (szczegóły w pułapkach)

> ⚠️ Historycznie standard wskazywał `pyqtdarktheme` — projekt porzucony
> (archived, pin Pythona <3.12, nie instaluje się na 3.12/3.13). Do prototypów
> dopuszczalny `pyqtdarktheme-fork` (import nadal `qdarktheme`), ale to mały
> projekt jednej osoby — aplikacje docelowe używają własnego theme.py;
> tylko on daje realny akcent #5DCAA5 i pełną kontrolę.

### Zasady theme.py (kontrakt komponentu w gui-kit)
1. **`app.setStyle("Fusion")` PRZED `setPalette()`** — natywne style Windows
   (`windowsvista`/`windows11`) ignorują większość ról QPalette; bez Fusion
   przyciski, menu i scrollbary zostaną jasne mimo ciemnej palety.
2. **QPalette = baza kolorów, QSS = tylko akcenty** (border-radius, hover,
   accent #5DCAA5, tooltips). Nie dublować kolorów w obu miejscach — QSS
   nadpisuje paletę i przy zmianie motywu zostają plamy. **QSS jest
   FUNKCJĄ palety, nie stałą:** generowany od zera przy KAŻDYM `apply()`
   z bieżących kolorów — nigdy cache'owany string z hexami (zamraża
   motyw startowy przy przełączeniu w locie).
3. **Auto-motyw:** `colorScheme()` → `Dark`/`Light`; wartość `Unknown`
   (Linux bez portalu XDG) traktuj jako fallback → dark.
4. **Reakcja na zmianę systemu:** podłącz `styleHints().colorSchemeChanged`
   tylko w trybie auto; w trybie wymuszonym ignoruj sygnał. **Kanoniczna
   sekwencja `apply()`** (zawsze w tej kolejności):
   `setPalette(nowa)` → `setStyleSheet(QSS wygenerowany z nowej palety)` →
   `QToolTip.setPalette(...)` (ToolTipBase=bg2, ToolTipText=fg) →
   `unpolish()/polish()` + `update()` po `app.allWidgets()`.
   Bez jawnego kroku QToolTip dymki zostają w motywie startowym —
   elementy statyczne/singletonowe Qt (QToolTip, QWhatsThis) NIE podążają
   za `app.setPalette()` przy zmianie w locie. Bez `update()` okna
   częściowo zasłonięte / w tle nie przerysują się aż do ekspozycji.
5. **Pojęcie ROZJAZDU motywów** (dotyczy WYŁĄCZNIE wyboru dialogu
   natywny/nienatywny): rozjazd ⇔ efektywny motyw aplikacji ≠ motyw systemu
   (`colorScheme()`, Unknown → traktuj jako dark). Tryb auto z definicji
   nie ma rozjazdu. Reguła jest SYMETRYCZNA — „app light + system dark"
   to taki sam rozjazd jak „app dark + system light".
   **UWAGA:** belki tytułu to NIE dotyczy — DWM ustawiamy bezwarunkowo
   wg motywu app (patrz pułapki; atrybut DWM jest stanowy, v2.5).
6. Tryb użytkownika (auto/jasny/ciemny) zapisywany w config (sekcja 8).

### Mocne strony
- natywny, nowoczesny wygląd
- ciemny motyw bezproblemowy
- bogate widgety (QTableWidget, QTreeView, QDockWidget, QWebEngineView)
- system sygnałów/slotów — czysty event handling
- menedżery layoutów — responsywne UI
- zero zależności motywu — theme.py to ~200 linii w pełni kontrolowanego kodu

### Ograniczenia
- większy `.exe` (~50-120 MB)
- stromsza krzywa nauki
- PySide6 jako zależność (~100 MB przy instalacji)

### Pułapki techniczne (z IcoForge + EpubForge + theme.py)
- **Pasek tytułu — ustawiaj DWM BEZWARUNKOWO (korekta v2.5):**
  `DwmSetWindowAttribute(20, dark)` gdzie `dark = efektywny motyw app jest
  ciemny`, przy KAŻDYM `apply()`, na KAŻDYM oknie top-level. **NIE pomijaj
  przy zgodności motywów** — atrybut DWM jest STANOWY: gdy raz ustawisz go
  ręcznie (TRUE przy rozjeździe), powrót do zgodności i „nic-nie-robienie"
  zostawia stary TRUE, a Qt go nie odbierze → belka zostaje zamrożona
  (objaw: jasny→ciemny→jasny, belka pozostaje czarna). Bezwarunkowe
  ustawienie na zgodności daje ten sam wynik co podążanie za systemem
  (bo motyw app == systemowy), więc zero kosztu, znika pułapka stanowości.
  Dalej: `WM_NCACTIVATE` + `RedrawWindow(RDW_FRAME)`; `winId()` w `showEvent`,
  nie w `__init__`. *(Uwaga: rozróżnienie zgodność/rozjazd zostaje TYLKO dla
  dialogów — tam natywny vs nienatywny to realne albo-albo. Dla belki było
  błędną optymalizacją.)*
- **Dialog odbiera focus → belka wraca do systemowej:** nadpisz `changeEvent`
  na `ActivationChange` i ponownie ustaw atrybut DWM wg motywu app
  (bezwarunkowo, jw.).
- **Natywne dialogi plików (SYMETRYCZNIE):** natywny ⇔ brak rozjazdu.
  Cztery kombinacje: dark+dark → natywny (Win11 sam da ciemny);
  light+light → natywny; dark+light → `DontUseNativeDialog`;
  **light+dark → `DontUseNativeDialog`** (natywny byłby ciemny nad jasną
  aplikacją). Tryb auto → zawsze natywny. Motyw systemu sprawdzaj
  **w momencie otwierania dialogu**, nie cache'uj ze startu (system mógł
  się zmienić w trakcie sesji).
- **Dialog przy rozjeździe — trade-off jest BINARNY, trzeciego wyjścia
  nie ma:** natywnego okienka Windows nie da się przemalować na motyw
  aplikacji (zawsze podąża za systemem). Wybór: natywny wygląd + złe
  kolory ALBO dobre kolory + nienatywny wygląd. Standard wybiera drugie
  (spójność motywu > pasek Szybki dostęp), bo dotyczy to wyłącznie
  świadomie wymuszonego rozjazdu — w domyślnym Auto fallback nie
  występuje nigdy. *Odrzucona alternatywa „zawsze natywne":* wróć do niej
  tylko, jeśli na co dzień jeździsz na wymuszonym motywie przeciwnym do
  systemowego — wtedy fallback oglądałbyś ciągle.
- **Standard fallbacku (gałąź `DontUseNativeDialog` — wzorzec gui-kit):**
  surowy QFileDialog jest nieakceptowalny; skonfiguruj go zawsze tak:
  - `setSidebarUrls`: Pulpit / Dokumenty / Pobrane (`QStandardPaths`),
    dyski (`QDir.drives()`), ostatnio użyty katalog z configu
  - `setViewMode(Detail)`
  - rozmiar startowy ~900×550, zapamiętywany w config
  - teksty przez i18n aplikacji
  - **przyciski toolbara — ikony znikają przez przeciekający app-QSS
    (v2.6):** PRAWDZIWA przyczyna pustych przycisków nawigacji
    (`backButton`, `forwardButton`, `toParentButton`, `newFolderButton`)
    i przełączników widoku (`listModeButton`, `detailModeButton`) to NIE
    brak ikon — to app-owa reguła `QToolButton { padding/border }`, która
    przecieka do wnętrza dialogu i przycina przypięty ~22px przycisk do
    zera (dowód: `button.size()` ~22px vs `sizeHint()` ~100px). Fix:
    - **per-widget QSS** na QToolButton-y dialogu zdejmujący `padding`
      i `border` (wyższa specyficzność niż reguła app-owa) → ikona 16px
      się mieści;
    - `setIcon(standardIcon(...))` gdy `icon().isNull()` (SP_ArrowBack/
      Forward/FileDialogToParent/FileDialogNewFolder);
    - **NIE wymuszaj tekstu** — etykieta nie zmieści się w przypiętym 22px
      przycisku (to był błąd v2.4); tooltip zostaje jako jedyny opis.
    - log DEBUG `[b.objectName() for b in findChildren(QToolButton)]`
      zostaje do diagnostyki.
    **TIMING:** drzewo widgetów istnieje dopiero po
    `setOption(DontUseNativeDialog, True)` — QSS i ikony aplikuj po tym,
    przed `exec()`.
    **Reguła ogólna:** app-owy QSS celujący w generyczne typy
    (`QToolButton`, `QLineEdit`, `QComboBox`) przecieka do nienatywnych
    dialogów i psuje widgety o przypiętym rozmiarze — neutralizuj
    per-widget w fallbacku albo zawężaj selektory app-QSS.
    Test (działa offscreen): po fixie `icon().isNull()` jest False ORAZ
    efektywny padding zneutralizowany (porównaj `size()`/`sizeHint()`),
    bez polegania na malowaniu pikseli.
  - **wymaga instancyjnego API** (`QFileDialog()` + `exec()`) — metody
    statyczne `get*FileName` nie pozwalają ustawić sidebara, rozmiaru ani
    sięgnąć do przycisków toolbara; gałąź natywna może pozostać statyczna.
- **Testy reguły rozjazdu:** mockuj `styleHints().colorScheme()` —
  test 4 kombinacji + auto nie może zależeć od motywu maszyny CI.
- **Zmiana motywu w locie — zamrożone elementy:** `QToolTip` (i pokrewne
  statyczne: QWhatsThis) trzymają WŁASNĄ paletę pobraną raz — po
  `app.setPalette()` dymki zostają w starym motywie. Fix: kanoniczna
  sekwencja apply() z kontraktu theme.py (regeneracja QSS + jawne
  `QToolTip.setPalette(...)` — metoda STATYCZNA klasy, import z
  QtWidgets). Test regresji: po `apply("dark")→apply("light")`
  `QToolTip.palette().color(ToolTipBase)` == bg2 nowego motywu ORAZ
  `app.styleSheet()` nie zawiera hexów poprzedniego motywu (łapie powrót
  cache'owania QSS). Test regresji dla `QToolTip.palette()` musi używać
  fixture `qapp` z pytest-qt (lub istniejącej w `conftest`) — bez aktywnej
  instancji `QApplication` wywraca się na CI, zanim cokolwiek sprawdzi.
- **Repaint pozostałości motywu:** po zmianie palety/QSS przejdź
  `style.unpolish()/polish()` po `app.allWidgets()` **+ `update()`**
  (patrz kontrakt theme.py pkt 4 — okna w tle).
- **Hardcoded kolory:** w kodzie widgetów używaj ról palety
  (`palette(base)`, `palette(text)`), nie sztywnych hexów — inaczej
  nie zmieniają się z motywem. Hexy żyją wyłącznie w theme.py.

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

### Stany pochodne (obowiązkowe — generuje je theme.py / apply_theme)

Żeby każda aplikacja nie wymyślała ich od nowa:

| Stan | Reguła | Dark | Light |
|---|---|---|---|
| `hover` | bg3 rozjaśnione ~8% | `#383c50` | `#dcdce2` |
| `pressed` | bg3 przyciemnione ~8% | `#262936` | `#d4d4da` |
| `selection_bg` | = accent2 | `#1D9E75` | `#0F7C5B` |
| `selection_fg` | tekst na akcencie | `#ffffff` | `#ffffff` |
| `disabled_fg` | = fg3 | `#555a70` | `#86868b` |
| `disabled_bg` | = bg2 | `#252830` | `#f5f5f7` |
| `placeholder` | = fg3 | `#555a70` | `#86868b` |
| `focus_border` | = accent | `#5DCAA5` | `#1D9E75` |

> **Kontrast w jasnym motywie:** `#1D9E75` jako kolor *tekstu/linku* na białym
> tle ma ~3,2:1 — poniżej WCAG AA (4,5:1). Dla tekstu i linków w jasnym motywie
> używaj `accent2 #0F7C5B`; `accent` zostaje dla wypełnień, ikon i ramek.

### Typografia
- **Font UI:** systemowy domyślny (TkDefaultFont / Qt default) — natywny wygląd
- **Font monospace** (kod, ścieżki, logi): Consolas / Menlo / DejaVu Sans Mono
- **Rozmiary:** tytuł ~13pt bold, sekcje ~9pt bold, treść ~9pt, hinty 8pt (nie mniej — 7pt jest nieczytelne na 1080p)
- rozmiary fontów zawsze w **pt** (skalują się z DPI), nie w px
- **Nie** mieszać wielu krojów — UI font + mono font wystarczą

### Odstępy i kształty
- padding sekcji: 10-12px
- odstęp między elementami: 6-8px
- zaokrąglenia: subtelne (Qt: border-radius 4-8px; tkinter: brak natywnych, flat)
- ramki: 1px, kolor `border` (0,5px nie renderuje się na standardowym DPI)
- relief: `flat` wszędzie gdzie się da (unikać wytłoczeń „3D")

### Ikonografia
- akcent destrukcyjny (usuń) → `red`
- ostrzeżenia → `amber`
- sukces/akcja główna → `accent`
- ikony spójne w obrębie aplikacji (jeden zestaw)

#### Zestaw ikon
- **Lucide** (licencja ISC) jako domyślny; **Tabler** (MIT) jako alternatywa.
- Wybrane SVG **kopiowane do repo** (`assets/icons/`) — zero zależności
  runtime. W repo plik `LICENSE-icons` z licencją zestawu.

#### Mechanizm: przebarwialne SVG, NIE statyczne PNG (komponent `IconProvider`)
Powód SVG zamiast PNG: ikony muszą przebarwiać się razem z motywem.
Moduł (gui-kit: `qt/icons.py`) z funkcją `get_icon(name, color=None) -> QIcon`:
- ładuje `assets/icons/<name>.svg`, podmienia `currentColor` na token palety
  (domyślnie `fg`; semantyczne `red`/`amber`/`accent`; ikona pełniąca rolę
  TEKSTU w jasnym motywie → `accent_text`/`text_accent()` — reguła kontrastu §5),
- render do QPixmap 16/24 px + warianty HiDPI (`devicePixelRatio`),
- cache po kluczu `(name, color, size)`; **`clear_cache()` na sygnale
  `theme_changed`**, po czym widgety wołają ponownie `setIcon()`,
- ścieżki przez `get_resource_path()` (działa w PyInstallerze;
  `assets/icons/*` w `datas`).
- **`ICON_MAP`** — jedna stała mapująca akcję → plik SVG, jedyne miejsce
  zmiany przy podmianie ikon (pencil/eraser/pipette/paint-bucket/square/
  square-dashed/arrow-left-right/rotate-ccw/zoom-in/zoom-out/save/undo-2/
  redo-2/copy/scissors/clipboard-paste/file-plus/folder-open/sun-moon/info…).

#### Zasada „nazwa NIE znika, tylko się przenosi"
Przy zamianie tekstowych etykiet na ikony (toolbar `ToolButtonIconOnly`,
`setIconSize(20×20)`, odstępy 6–8px):
- tekst akcji wędruje do **tooltipa** w formacie „Nazwa (skrót)" (np.
  „Ołówek (B)") — spójne z wymogiem tooltipów,
- i **zostaje w `setText()`** (czytniki ekranu, menu kontekstowe, menu Plik
  gdzie Qt pokazuje ikonę automatycznie),
- narzędzie aktywne: `setCheckable(True)` + `QActionGroup` (exclusive) —
  podświetlenie zamiast zgadywania,
- po `theme_changed`: ponowne `setIcon()` (po `clear_cache()`).
- **Audyt tooltipów** jako test: iteracja po `findChildren(QAbstractButton)`
  + akcjach toolbarów; element interaktywny bez tooltipa = fail.

> Wzorzec wdrożony pierwotnie w IcoForge (etap `feat/icon-system`,
> kroki 4.1–4.6) — kandydat do ekstrakcji do gui-kit jako `qt/icons.py`.

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
| `ThemeManager` | motyw auto/jasny/ciemny + persist | słownik + apply_theme + darkdetect | theme.py: Fusion + QPalette + QSS, auto przez styleHints |
| `set_titlebar_dark` | pasek tytułu = motyw app (BEZWARUNKOWO, atrybut stanowy) | GetParent(winfo_id) | winId(); DWM = app_is_dark przy każdym apply, każde okno |
| `PathEntry` | pole + przycisk wyboru | tk.Frame | QWidget |
| `FileDialogs` | dialogi wg reguły rozjazdu + skonfigurowany fallback | tk.filedialog (zawsze natywne-jasne, ograniczenie toru) | natywny: statyczne get*; fallback: instancja QFileDialog (sidebar, Detail, rozmiar z config) |
| `FileList` | lista plików z toolbar + D&D | tk.Listbox | QListWidget |
| `Checkbox` | stylizowany checkbox (nie switch!) | tk.Checkbutton | QCheckBox |
| `IconProvider` | przebarwialne ikony SVG wg palety | — (brak; PNG lub emoji) | get_icon(name,color)→QIcon, currentColor z palety, cache, clear na theme_changed |
| `Tooltip` | podpowiedź reagująca na motyw | Toplevel | QToolTip: QSS z theme.py + setPalette przy każdym apply() (statyczna paleta!) |
| `Section` | sekcja z tytułem | ttk.LabelFrame | QGroupBox |
| `LogStreamer` | strumień subprocess → log | kolejka + after | QThread + signal |
| `AboutPanel` | logo, wersja, linki | Frame | QWidget |

> Zasada: komponent piszesz RAZ, potem importujesz. Nie przepisywać między projektami.
> Pierwsza implementacja theme.py powstaje w pdf2md (etap G1) i trafia do gui-kit.

---

## 8. Wspólne zachowania

Każda aplikacja MUSI mieć:

### Konfiguracja
- `config.json` (lub `.toml`) w katalogu z `platformdirs.user_config_dir("AppName")`
  — na Windows `%APPDATA%`, na Linux `~/.config`, na macOS `~/Library/Application Support`;
  **nie hardcodować `~/.config`** (to konwencja tylko linuksowa)
- wariant portable: config obok exe (wykrywany przez obecność pliku-markera)
- zapis atomowy (tmp + replace)
- zapamiętuje: motyw, ostatnie katalogi, presety, ustawienia okna
- **zapis przy każdej zmianie (z debounce ~1 s) lub po każdej operacji** —
  nie tylko przy zamknięciu, bo crash = utrata ustawień

### Motyw
- tryb auto/jasny/ciemny, wybór zapamiętany
- auto = śledzi system (tkinter: `darkdetect`; Qt: `styleHints().colorScheme()`)
- ciemny pasek tytułu na Windows (z niuansami z sekcji 4)
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

> **Zakres:** ta sekcja dotyczy aplikacji o czystym drzewie licencji (MIT/BSD/LGPL).
> Projekty z zależnościami copyleft w łańcuchu (jak pdf2md) dystrybuujemy
> przez pip/uv, nie przez binarkę PyInstaller.

### Oba tory: PyInstaller
- **portable:** `--onefile` → jeden `.exe`, zero instalacji
- **instalator:** `--onedir` + Inno Setup → setup.exe ze skrótami
- ikona z `assets/icon.ico`
- `console=False` (aplikacja GUI)

### Pułapki
- **Qt + `--onefile` tylko świadomie:** rozpakowywanie ~150 MB do temp =
  wolny start (kilka–kilkanaście s) i częste false-positives antywirusów;
  dla Qt preferuj `--onedir` + Inno Setup
- **`upx=False` dla Qt** — UPX uszkadza DLL-e Qt; wyłącz w `.spec`
- tkinter: hook `tkdnd` dla tkinterdnd2 w `.spec`
- Qt: PySide6 plugins (platforms, styles) zwykle wykrywane automatycznie, ale sprawdź rozmiar
- DLL conflict (python3xx.dll) — izolacja przy wywołaniach subprocess
- assets (logo, ikona) w `datas`, ładowane przez `sys._MEIPASS` w bundlu

### CI/CD
- GitHub Actions: build na `windows-latest` przy tagu `v*`
- Release z oboma plikami (portable + instalator)
- testy + lint + mypy na każdym push, ale z oszczędzaniem minut:
  - `concurrency: group: ${{ github.ref }}, cancel-in-progress: true`
  - `paths-ignore: ['**.md', 'docs/**']` dla jobów testowych
  - ciężki build Windows tylko przy tagu, nie na każdym push
  - lokalna pre-walidacja przez nox/tox przed pushem

---

## 10. Checklista nowego projektu GUI

Przy starcie nowej aplikacji:

```
[ ] Wybrano tor (tkinter / Qt) wg tabeli decyzyjnej z sekcji 2
[ ] Struktura: core/ (logika, bez GUI) + gui/ + cli/ + tests/
[ ] pyproject.toml + ruff + mypy + pytest
[ ] config przez platformdirs + zapis atomowy + debounce (sekcja 8)
[ ] ThemeManager z auto/jasny/ciemny (paleta + stany z sekcji 5)
[ ] Qt: theme.py wymusza Fusion przed setPalette
[ ] Pasek tytułu Windows: DWM = motyw app BEZWARUNKOWO przy każdym apply (atrybut stanowy!)
[ ] Dialogi natywne ⇔ brak rozjazdu (reguła symetryczna); fallback skonfigurowany wg standardu (sidebar, Detail, rozmiar)
[ ] Górny pasek wg układu z sekcji 6 (logo + motyw + about)
[ ] Komponenty z gui-kit (sekcja 7) zamiast pisać od zera
[ ] Tooltipy na wszystkich interaktywnych elementach
[ ] Domyślne katalogi = katalog źródłowy
[ ] Obsługa błędów w okienku + error.txt
[ ] Zakładka/panel "O programie" z wersją i linkami
[ ] Sprawdzono drzewo licencji (copyleft? → dystrybucja pip, nie PyInstaller)
[ ] Build: portable + instalator (z pułapkami z sekcji 9)
[ ] CI/CD: testy + build przy tagu, concurrency cancel + paths-ignore
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

*Dokument żywy — aktualizuj w miarę jak wypracowujesz kolejne wzorce. Zmiany odnotowuj w tabeli wersji na górze.*
