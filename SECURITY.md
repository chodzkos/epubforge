# Polityka bezpieczeństwa

Dziękujemy za pomoc w utrzymaniu bezpieczeństwa **EpubForge**. Ten dokument
opisuje, które wersje są wspierane oraz jak zgłaszać podatności.

## Wspierane wersje

Poprawki bezpieczeństwa trafiają do najnowszej linii wydawniczej. Starsze wersje
nie są łatane — zalecamy aktualizację do najnowszej.

| Wersja  | Wspierana          |
|---------|--------------------|
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Zgłaszanie podatności

**Nie zgłaszaj podatności przez publiczne Issues ani Pull Requesty** — dałoby to
atakującym okno, zanim pojawi się poprawka.

Zgłoś ją prywatnie przez wbudowany kanał GitHub:

1. Wejdź w zakładkę **Security** repozytorium
   [chodzkos/epubforge](https://github.com/chodzkos/epubforge/security).
2. Kliknij **Report a vulnerability** (GitHub Private Vulnerability Reporting).
3. Opisz problem możliwie dokładnie — patrz niżej.

Zgłoszenie jest widoczne wyłącznie dla opiekunów projektu do czasu publikacji
poprawki i skoordynowanego ujawnienia.

### Co dołączyć do zgłoszenia

- dotknięty moduł/plik i wersja EpubForge (`epubforge --version`),
- kroki reprodukcji (najlepiej minimalny przykład, np. spreparowany plik EPUB),
- wpływ (np. odczyt plików spoza archiwum, wykonanie kodu, DoS),
- ewentualna propozycja poprawki.

## Czas reakcji

Projekt jest prowadzony przez wolontariuszy, więc terminy są orientacyjne (best
effort):

| Etap                                   | Cel czasowy          |
|----------------------------------------|----------------------|
| Potwierdzenie przyjęcia zgłoszenia     | do 72 godzin         |
| Wstępna ocena (istotność, zakres)      | do 7 dni             |
| Poprawka lub plan działania            | do 30 dni od potwierdzenia |

Krytyczne, aktywnie wykorzystywane podatności traktujemy priorytetowo i staramy
się reagować szybciej.

## Ujawnianie

Preferujemy **skoordynowane ujawnienie**: prosimy o wstrzymanie się z publikacją
szczegółów do czasu udostępnienia poprawki. Po wydaniu łatki chętnie uznamy Twój
wkład w opisie wydania (chyba że wolisz pozostać anonimowy/-a).
