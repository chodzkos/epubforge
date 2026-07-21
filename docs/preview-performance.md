# Wydajność dokładnego podglądu

Ciężkie przygotowanie snapshotu, parsowanie XHTML i preload zasobów wykonuje
`QThreadPool`. Worker operuje na skopiowanych danych wejściowych i nigdy nie
dotyka widgetów Qt. Handler własnego schematu otrzymuje gotowe, nieruchome dane
pamięciowe; nie czyta ZIP-a i nie wykonuje `stat()` podczas requestu Chromium.

Cache jest osobny dla sesji EPUB i ma limity bajtowe: dokumenty 4 MiB, CSS 2 MiB,
obrazy 24 MiB, fonty 16 MiB i pozostałe zasoby 2 MiB. Kluczem jest ścieżka oraz
revision zasobu. Zmiana CSS unieważnia tylko właściwy zasób, bez ponownego
odczytu całego archiwum. Zasób większy od limitu kategorii nie obchodzi limitu
ukrytą ścieżką dyskową w handlerze — podgląd zgłasza jego brak.

## Benchmark i budżety testowe

Pomiar bazowego `tests/fixtures/sample.epub` na Linuksie dał 1,56 ms dla pierwszej
generacji, medianę 0,58 ms dla kolejnej i 0,01 ms dla zamknięcia. Syntetyczny EPUB
1,27 MiB z dużym CSS, obrazem i fontem dał odpowiednio 3,78 ms, 0,49 ms,
0,57 ms dla CSS-only i 0,16 ms dla zamknięcia; cache zajmował 1 049 487 B.

Testy stosują progi z dużym marginesem dla współdzielonych runnerów CI: 800 ms
pierwszy render, 250 ms kolejny, 200 ms CSS-only i 50 ms zamknięcie. To progi
regresji blokującej interfejs, ustalone z powyższych pomiarów repozytorium, a nie
obietnice czasu na każdym komputerze. Metryki bieżącej sesji są dostępne przez
`PreviewSession.performance`, a rozmiar i podział cache przez `cache_stats()`.
