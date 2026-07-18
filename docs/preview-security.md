# Bezpieczeństwo dokładnego podglądu EPUB

Dokładny podgląd traktuje każdy EPUB jako niezaufany dokument. Każde otwarcie
publikacji otrzymuje losowy origin `epub-preview://<session-id>/`, a każda zmiana
tworzy nową generację snapshotu. Stary origin lub numer `rev` nie zwraca danych.

Handler schematu czyta wyłącznie nieruchomy `ResourceProvider`: najpierw snapshot
niezapisanej treści, następnie snapshot bufora `Epub`, a na końcu oryginalny wpis
ZIP. Nie odwołuje się do `EditorTab`, widgetów ani żywego `_dirty`. Zamknięcie
sesji usuwa aktywną generację i nie pozostawia otwartego uchwytu EPUB-a.

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
