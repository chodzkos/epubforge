# Edytor EPUB

Edytor służy do bezpiecznego przeglądania i szybkiej korekty plików **wewnątrz**
EPUB-a. Nie zastępuje pełnego programu DTP ani Sigila: zmienia wskazane pliki, pokazuje
rzeczywisty podgląd i pomaga znaleźć źródło problemu bez automatycznego przepisywania
całej publikacji.

## Pierwsze kroki

1. Kliknij **Otwórz EPUB…** i wybierz publikację.
2. W drzewie po lewej rozwiń grupę **Tekst**, **Style**, **Obrazy**, **Fonty** lub
   **Inne**, a następnie wybierz plik. Pełna ścieżka pliku jest również w dymku.
3. Pliki XHTML, HTML, XML, OPF i CSS otwierają się jako kod; obrazy mają własny
   podgląd, a pozostałe pliki pokazują typ i rozmiar.
4. Aby zmieniać kod, włącz **Tryb: edycja**. Startowy tryb tylko do podglądu chroni
   przed przypadkową zmianą. Pliki zawierające niepoprawne bajty UTF-8 pozostają
   tylko do odczytu.

Drzewo i każdy panel mają własne przewijanie. Uchwyty pomiędzy drzewem, kodem,
podglądem i inspektorem zmieniają ich szerokość, ale nie pozwalają zwinąć ważnej
zawartości do nieczytelnego paska. Szerokie paski kontrolek przewijają się poziomo,
zamiast ucinać nazwy akcji.

## Zapis, Undo i reset układu

- **Ctrl+S** zapisuje bieżący tekst do bufora otwartego EPUB-a. Dla XHTML/XML/OPF
  wykonywana jest walidacja; zapis niepoprawnego XML wymaga potwierdzenia.
- **Zapisz EPUB** utrwala bufor na dysku i tworzy kopię `.bak`. Sam podgląd,
  diagnostyka i przycisk **Zastosuj** inspektora nie zapisują automatycznie całego
  EPUB-a.
- Zastosowanie jednej reguły CSS jest jedną operacją **Undo** w głównym edytorze.
- **Resetuj układ** najpierw prosi o potwierdzenie. Po zgodzie chowa inspektor,
  diagnostykę, ustawienia czytnika, wyszukiwanie i widok dzielony oraz przywraca
  podstawowe proporcje paneli. Nie usuwa zmian w kodzie ani buforze EPUB-a.

## Kod, Podgląd i Podział

Dla pliku HTML/XHTML pojawiają się trzy kontrolki:

- **Kod** — pokazuje źródło z numerami linii i podświetlaniem składni;
- **Podgląd** — pokazuje wyrenderowany bieżący dokument, również z niezapisanymi
  zmianami;
- **Podział** — umieszcza Kod i Podgląd obok siebie. Ustawienie jest zapamiętywane.

Zmiana kodu jest przekazywana do podglądu z krótkim opóźnieniem. Zaznaczony element
i względna pozycja przewijania są odzyskiwane po zmianie CSS lub profilu, jeśli nowy
DOM nadal pozwala odnaleźć ten element.

Przycisk **Resetuj układ** jest najprostszym sposobem powrotu do samego kodu, gdy
otwarto wiele paneli.

## Szybki i dokładny podgląd

Selektor **Podgląd** wybiera tor renderowania:

- **Auto** — używa dokładnego WebEngine, gdy jest dostępny, a w przeciwnym razie
  bezpiecznie przechodzi na szybki tor;
- **Dokładny** — Chromium przez Qt WebEngine, z zasobami i CSS bieżącego snapshotu;
- **Szybki** — lekki `QTextDocument`, działający także bez WebEngine.

**Przeładuj dokładnie** wykonuje pełny reload bieżącej migawki. **Użyj szybkiego**
pojawia się po awarii wymuszonego toru dokładnego. Status obok selektora rozróżnia
renderowanie, wersję aktualną, ostatnią poprawną wersję, fallback i błąd.

Szybki tor nie oblicza pełnej kaskady Chromium. Dlatego dla HTML przycisk
**Inspektor CSS** jest dostępny tylko w trybie dokładnym. Dla zwykłego pliku `.css`
tryb **Arkusz** działa w obu backendach i nawet bez WebEngine.

## Inspektor CSS — Arkusz

Po wybraniu pliku CSS włącz **Inspektor CSS** i otwórz kartę **Arkusz**:

- lista pokazuje selektor, skrót deklaracji i kontekst `@media`;
- wybrana reguła jest edytowana po dokładnym spanie źródłowym;
- karta podglądu zachowuje ostatni poprawny wynik, gdy wpisany CSS jest błędny;
- **Przywróć** odrzuca lokalną edycję reguły;
- **Zastosuj do arkusza** sprawdza revision i podmienia jeden span jako jeden krok
  Undo. Zmiana źródła w międzyczasie powoduje jawny konflikt, bez cichego nadpisania.

Ten tryb jest celowo zgodny ze starszym inspektorem i nie wymaga aktywnego dokumentu
HTML.

## Inspektor CSS — Element

Wybierz HTML/XHTML i tor **Dokładny**, a następnie włącz **Inspektor CSS**. Dokument
zostanie przygotowany także wtedy, gdy pozostajesz w widoku Kod. Kliknięcie elementu
w podglądzie wybiera go i aktualizuje raport. Karta **Element** pokazuje:

- breadcrumb DOM, tag, `id`, klasy i fragment tekstu;
- box model: margin, border, padding i rozmiar content;
- reguły autora, style inline, deklaracje dziedziczone i aktywność `@media`;
- wartość zadeklarowaną, computed, `!important`, specyficzność i kolejność;
- stan: zwycięska, częściowo nadpisana, przegrana albo nieaktywna; przegrana
  deklaracja wskazuje kolejność zwycięzcy;
- plik, linię, kolumnę, kontekst reguły oraz wiarygodnie zmapowany span;
- faktycznie użyty font, wartość computed, status fontu osadzonego i fallback;
- jawne nadpisania warstwy użytkownika oraz ograniczenia analizy.

Filtry **Typografia**, **Layout**, **Kolory**, **Box model** i **Nadpisane** można
łączyć z wyszukiwarką nazwy właściwości.

Akcje elementu:

- **Przejdź do reguły** — otwiera właściwy arkusz i dokładne wystąpienie reguły;
- **Pokaż źródło elementu** — wraca do przybliżonej linii HTML;
- **Utwórz regułę dla elementu** — dodaje szkielet reguły do pasującego arkusza;
- **Kopiuj selektor** — kopiuje selektor do schowka;
- **Podświetl wszystkie dopasowania** — zaznacza pasujące elementy w renderowanej
  kopii.

## Edycja CSS na żywo

Edycja reguły elementu najpierw trafia do tymczasowej warstwy w kopii renderowanej,
bez zmiany źródła. Zakres **Bieżący element** używa technicznego selektora tylko w
podglądzie; **Wszystkie dopasowania** używa oryginalnego selektora. Panel pokazuje
liczbę dopasowań i ostrzega, że warstwa dołączona na końcu dokumentu może mieć inną
kolejność niż reguła źródłowa.

Błąd CSS nie usuwa ostatniej poprawnej warstwy. **Zastosuj** ponownie sprawdza
revision, zapisuje właściwy plik i span przez istniejącą ścieżkę Undo, odświeża mapę
reguł i podgląd, ale nie zapisuje całego EPUB-a na dysku.

## Symulator czytnika

Profile są opisowe, ponieważ EpubForge nie uruchamia silnika konkretnej marki:
**e-ink mały**, **e-ink duży**, **telefon pionowy**, **tablet pionowy**,
**tablet poziomy** i **własny viewport**. Profil określa CSS px, informacyjny DPR,
margines, font/fallback, rozmiar, line-height, kolory, orientację i przepływ.

- **Przewijanie** pokazuje dokument reflowable w zwykłym flow.
- **Strony podglądu** używają kontrolowanej warstwy CSS columns. Przyciski
  **Poprzednia**, **Następna** i **Do elementu** poruszają się po technicznych stronach
  podglądu — nie po numerach stron książki.
- Fixed-layout wykryty z `rendition:layout=pre-paginated` i viewportu jest skalowany
  jako cała strona. Nie otrzymuje reflow, columns ani wymuszonej typografii.
- RTL, kierunek postępu, spread, orientation, writing-mode i multimedia są
  stosowane w obsługiwanym zakresie; konkretne ograniczenie pojawia się w panelu.

### Ustawienia użytkownika

**Ustawienia użytkownika** otwierają warstwę oddzielną od CSS wydawcy. Można ją w
całości wyłączyć oraz ustawić rozmiar tekstu, line-height, marginesy, font/fallback,
kolory, wyłączenie fontów osadzonych i wyłączenie stylów wydawcy. Porównanie wybiera:

1. CSS wydawcy;
2. CSS wydawcy + ustawienia użytkownika;
3. tekst bez stylów wydawcy.

**Porównaj obok siebie** uruchamia drugi profil w dokładnym torze. Panel pokazuje też
faktycznie użyty font, licznik pamięciowego cache i akcję **Wyczyść cache**.

## Diagnostyka i screenshot

**Diagnostyka** jest przełącznikiem: pierwszy klik pokazuje i uruchamia analizę,
drugi ją chowa. Dwuklik problemu przechodzi do elementu oraz źródła, gdy lokalizacja
jest dostępna. Kategorie odróżniają błąd publikacji, ostrzeżenie jakości, blokadę
bezpieczeństwa i ograniczenie symulatora.

Analiza obejmuje poziomy overflow, szerokości większe od viewportu, za szerokie
obrazy, podejrzane `position: absolute/fixed`, mały font lub line-height, brakujące i
zablokowane zasoby, zewnętrzne URL-e, niezaładowane fonty, ostrzeżenia kontrastu oraz
opcjonalnie brak `alt` i prostą hierarchię nagłówków. Kontrast jest ostrzeżeniem —
aplikacja nie wykonuje arbitralnego auto-fixu.

**Screenshot** zapisuje sam dokładny viewport bez nakładki inspektora. W szybkim
torze funkcja zgłasza jawne ograniczenie.

## Szukaj i zamień

- **Ctrl+F** — wyszukiwanie w aktualnym polu kodu; F3 / Shift+F3 przechodzą między
  trafieniami.
- **Ctrl+Shift+F** — panel całego edytora: bieżący plik lub cały EPUB, tekst albo
  regex, rozróżnianie wielkości liter i całe słowa.
- Dwuklik wyniku otwiera plik i pozycję. **Zamień wszystkie** zmienia bufor, a nie
  zapisany EPUB; pliki nie-UTF-8 są pomijane. Długie wyszukiwanie można anulować.

## Bezpieczeństwo i ograniczenia

Każde otwarcie EPUB-a ma osobną sesję i origin. Sieć, `file://`, downloady, popupy,
uprawnienia, skrypty publikacji, event handlery i iframe są blokowane lub usuwane.
Kod aplikacji działa w kontrolowanym świecie WebEngine; tryb szybki nie importuje
WebEngine.

Pseudoelementy, animacje i transitions, pełna analiza `@layer`, złożone `var()`,
`@container`, `@scope`, pełne style user-agent oraz niejednoznaczne shorthandy są
tylko do odczytu albo mają widoczne ograniczenie — nierozpoznana reguła nie znika
po cichu.

Przyciski **Sigil** i **Calibre Editor** w pierwszym, górnym pasku przekazują cały
otwarty plik `.epub` do wykrytego narzędzia — nigdy pojedynczy zasób z drzewa.
Zewnętrzny program czyta wersję zapisaną na dysku; niezapisany bufor Edytora trzeba
najpierw świadomie utrwalić przyciskiem **Zapisz EPUB**.

Pełny opis wszystkich funkcji: `docs/user-guide.md`.
