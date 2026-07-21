# Gotowość wydania dokładnego podglądu

## Model wydania

Windows ma jeden pełny release z Qt WebEngine. Lekki `QTextDocument` jest
fallbackiem developerskim i awaryjnym, a bazowe core/CLI nadal nie importują Qt.
Pełny build używa wspólnego `build/_spec_common.py`; WebEngine jest świadomym
wyjątkiem, zaś Quick/Qml/3D/Multimedia i pozostałe nieużywane moduły są wykluczone.
Oba specy zachowują `upx=False`.

Nie migrujemy obecnie z meta-pakietu `PySide6` do ręcznego zestawu Essentials +
Addons. Kod korzysta z modułów obu dystrybucji, w tym Widgets, WebEngine i
WebChannel; pełny artefakt i tak wymaga Addons. Nie istnieje extra `preview`, które
pozornie obiecywałoby mniejszy zestaw zależności.

## Macierz testowa

Syntetyczne EPUB-y i snapshoty testów obejmują wiele CSS, inline style,
`!important`, aktywne i nieaktywne `@media`, WOFF2, SVG, RTL, writing-mode,
fixed-layout, brakujące zasoby i zewnętrzne URL-e. Osobne przypadki pokrywają
script/event handlers/iframe, traversal i podwójne kodowanie, duży CSS/obraz/font
oraz dwie książki otwierane kolejno w jednym procesie.

Test runtime WebEngine uruchamia lokalny serwer-pułapkę i plik z sekretem, a potem
potwierdza brak requestu i brak odczytu `file://`. Testy sprawdzają zamkniętą
sesję, izolację originów i renderer crash z jednokrotnym odzyskaniem oraz
fallbackiem. Eksport screenshotu ma stabilny test strukturalny: nakładki
inspektora są wyłączane przed `grab()` i odtwarzane po nim. DOM, computed style i
kontrakty bezpieczeństwa pozostają ważniejsze niż kruche porównanie pikseli;
ewentualny golden screenshot wolno aktualizować tylko na wersji Qt przypiętej w
`uv.lock` i z repozytoryjnymi fontami testowymi.

CI jest rozdzielone na unit + fallback offscreen, bazowe CLI bez Qt, WebEngine
headless na Linuksie oraz Windows frozen smoke. Flaga Chromium `--disable-gpu`
istnieje wyłącznie w środowisku kontrolowanego joba; kod produkcyjny nie ustawia
`--no-sandbox`. Gotowe onefile i onedir uruchamiają `--self-check`, który sprawdza
`QtWebEngineProcess`, DLL-e WebEngine/WebChannel, resources, locales, pakiety
Chromium i noty third-party.

## Checklista

- [x] Core i CLI nie importują Qt/WebEngine; bazowy job działa bez PySide6.
- [x] Brak WebEngine pozostawia sprawny lekki backend.
- [x] Każdy EPUB ma losowy origin, własną off-the-record sesję i rewizje zasobów.
- [x] Sieć, `file://`, download, popupy i uprawnienia są blokowane.
- [x] Skrypty publikacji nie wykonują się; aktywne elementy są sanitizowane.
- [x] Skrypt aplikacji działa w kontrolowanym `ApplicationWorld`, co sprawdza test
  na przypiętej wersji PySide6.
- [x] Niezapisane XHTML/CSS trafiają do snapshotu, a błędny XHTML zachowuje ostatni
  poprawny render.
- [x] Scroll i wybrany element są odzyskiwane po zmianie CSS/profilu.
- [x] Inspektor mapuje regułę do unikalnego pliku, ścieżki reguły i spanu.
- [x] Zastosowanie CSS używa `apply_replacement` jako jednej operacji Undo i
  wykrywa konflikt revision.
- [x] Reflowable i fixed-layout korzystają z osobnych torów.
- [x] Motyw gui-kit zmienia chrome, nie treść książki.
- [x] Ustawienia używają istniejącego `ConfigStore` i debounce.
- [x] WebEngine nie trafia do `chodzkos-detection` ani cache narzędzi.
- [x] Onefile i onedir mają obowiązkowy Windows frozen smoke test.
- [x] Dokumentacja opisuje koszt, bezpieczeństwo i ograniczenia renderowania.

Limity v1 inspektora (pseudoelementy, animacje/transitions, pełne `@layer`,
złożone `var()`, `@container`, `@scope`, user-agent tree i niejednoznaczne
shorthandy) są prezentowane jako ograniczenia/read-only, nie pomijane po cichu.
Zasób większy niż limit swojej kategorii cache jest jawnie niedostępny dla
renderera zamiast powodować dyskowy odczyt w handlerze.
