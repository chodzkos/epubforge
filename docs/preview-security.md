# Bezpieczeństwo dokładnego podglądu EPUB

Dokładny podgląd traktuje każdy EPUB jako niezaufany dokument. Każde otwarcie
publikacji otrzymuje losowy origin `epub-preview://<session-id>/`, a każda zmiana
tworzy nową generację snapshotu. Stary origin lub numer `rev` nie zwraca danych.

Worker przygotowuje nieruchomy `ResourceProvider`: najpierw snapshot niezapisanej
treści, następnie snapshot bufora `Epub`, a zasoby źródłowe preładuje z ZIP-a do
ograniczonego bajtowo cache. Handler schematu czyta już wyłącznie gotowe dane
pamięciowe — nie dotyka `EditorTab`, widgetów, żywego `_dirty`, systemu plików ani
ZIP-a. Zamknięcie sesji usuwa aktywną generację i nie pozostawia otwartego uchwytu.

Profil WebEngine jest osobny i off-the-record. Cache, trwałe cookies, trwałe
uprawnienia, spellcheck i push są wyłączone. Interceptor blokuje sieć, `file:`,
`ftp:`, `qrc:`, `blob:` i każdy origin poza aktywną sesją. Pobrania, popupy oraz
uprawnienia są automatycznie odrzucane.

Kopia XHTML jest parsowana wyłącznie przez `core/_xml_safe.py`. Usuwane są
skrypty, event handlery, ramki, obiekty, formularze, aktywne multimedia i meta
refresh. Dodawany CSP zaczynający się od `default-src 'none'`; oryginalne dane w
`Epub` nie są modyfikowane.

## Spike JavaScript — PySide6 6.11.1

Test techniczny wykonany 18 lipca 2026 potwierdził, że `runJavaScript()` w
`QWebEngineScript.ApplicationWorld` działa przy `JavascriptEnabled=False`.
Dlatego JavaScript publikacji pozostaje wyłączony. Przyszły kod inspektora może
działać wyłącznie w `ApplicationWorld`; zmiana tej decyzji wymaga ponownego testu
na przypiętej wersji Qt i przeglądu bezpieczeństwa.

## Zasoby i snapshot niezapisanych zmian

Adres zasobu rozdziela generację renderu (gen) od rewizji konkretnego wpisu
(rev). PreviewController zamraża bieżący tekst edytora przed _dirty, pozostałe
niezapisane pliki, zmiany buforowane w Epub, mapę media type i rewizje. Handler
widzi wyłącznie nieruchomy ResourceProvider; spóźniona generacja jest odrzucana.

XHTML, CSS i SVG są przepisywane tylko w kopii renderowanej. Względne odwołania,
fragmenty, dziedziczone xml:base, CSS url(...) i @import prowadzą do
wersjonowanych adresów aktywnej sesji. Importy nie są rozwijane rekurencyjnie po
stronie Pythona, dlatego cykl arkuszy nie powoduje rekurencji ani ponownego odczytu
całego ZIP-a. Aktywna treść SVG jest usuwana, a sieć i lokalne pliki pozostają
zablokowane. EPUB nie jest rozpakowywany do katalogu tymczasowego.

Diagnostyka rozróżnia błąd książki, blokadę bezpieczeństwa i ograniczenie podglądu.
Zawiera bezpieczny URL źródłowy, rozwiązany internal path i plik żądający zasobu,
ale redaguje file:, data:, query oraz ścieżki systemowe.


## Mapowanie DOM do źródła

Każda generacja buduje w pamięci mapę elementów bieżącego XHTML do linii
oryginału. Identyfikatory są deterministyczne, ale trafiają wyłącznie do kopii
renderowanej przed sanitizacją; bufor `Epub` i tekst `CodeEditor` pozostają
niezmienione. Linia wskazuje początek elementu i jest jawnie opisana jako
przybliżona, ponieważ parser XML nie udostępnia dokładnego zakresu znacznika.

Listener w `ApplicationWorld` wysyła przez prywatny, losowy token tylko 16-znakowy
identyfikator. Backend odrzuca pozostałe komunikaty konsoli i rozwiązuje ID
wyłącznie w mapie aktywnej generacji, bez logowania treści publikacji.

## Odświeżanie i awarie

Edycja jest debouncowana przez 400 ms. Zmiana XHTML tworzy nową generację i przed
reloadem zapisuje stabilny identyfikator węzła, oryginalne id, ścieżkę DOM,
fragment tekstu, aktywny fragment oraz względny scroll. Odtwarzanie używa tej samej
kolejności. Niepoprawny XHTML nie zastępuje ostatniej poprawnej wersji.

Zmiana pojedynczego CSS aktywuje nową generację zasobów i podmienia tylko href
właściwego arkusza w ApplicationWorld; DOM, scroll i zaznaczenie pozostają bez
reloadu. Gdy podmiana jest niemożliwa, wykonywany jest kontrolowany pełny reload z
diagnostyką. Zmiana motywu przemalowuje wyłącznie chrome podglądu.

Po renderProcessTerminated backend wykonuje najwyżej jedną automatyczną próbę
odtworzenia. Kolejna awaria przełącza UI na lekki backend, nie dotykając tekstu
CodeEditor, _dirty ani bufora Epub.
