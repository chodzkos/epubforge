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

## Model bezpieczeństwa (niezaufane pliki EPUB)

EPUB to archiwum ZIP dostarczone przez użytkownika — traktujemy je jako
**niezaufane**. Zanim odczytamy jakąkolwiek treść, `epubforge.core.Epub`
centralnie waliduje archiwum (`core/_archive.py`) **na metadanych nagłówka ZIP,
bez dekompresji** — każde odrzucenie następuje więc zanim cokolwiek zostanie
rozpakowane:

- **budżety zasobów** (bomby ZIP / wyczerpanie pamięci): liczba wpisów, suma
  rozmiarów nieskompresowanych, rozmiar pojedynczego wpisu, rozmiar XML/tekstu,
  maksymalny współczynnik kompresji i budżet operacji;
- **niekanoniczne nazwy**: duplikaty, znak NUL, backslash, ścieżki absolutne,
  segmenty `..` (traversal) oraz wpisy zaszyfrowane — odrzucane z
  `ResourceLimitError` (bezpieczny komunikat dla GUI/CLI).

Limity są **konfigurowalne i udokumentowane** (`ArchiveLimits`) — domyślne
wartości nie blokują typowych dużych EPUB-ów (grafika/audio), a kto ufa źródłu,
może je świadomie podnieść:

```python
from epubforge.core import Epub, ArchiveLimits

limits = ArchiveLimits(max_entry_size=1024 ** 3)  # np. 1 GiB na wpis
with Epub(path, limits=limits) as epub:
    ...
```

Zapis kopiuje niezmienione wpisy **strumieniowo** (stały bufor), więc pamięć
szczytowa nie rośnie z rozmiarem największego wpisu. Niezaufany XML (container,
OPF, NCX, XHTML) parsujemy utwardzonym parserem lxml (`core/_xml_safe.py`):
bez rozwijania encji, bez sieci, bez zewnętrznego DTD (ochrona przed XXE i
rozdmuchaniem encji).

## Model bezpieczeństwa (sieć — metadane książek)

Pobieranie metadanych jest **opt-in** i przechodzi w całości przez jeden
utwardzony klient (`bookmeta/_http.py`):

- **wyłącznie `https`** — schemat, host i port walidowane przez `urlsplit` przed
  połączeniem; `http:`/`file:`/`data:` oraz `userinfo` (`login:hasło@`) odrzucane;
- **ochrona przed SSRF** — host jest rozwiązywany przez DNS, a adresy loopback /
  prywatne / link-local / reserved / multicast są odrzucane (brak żądań do sieci
  lokalnej i metadanych chmury);
- **walidacja każdego przekierowania** — własny redirect handler sprawdza KAŻDY
  hop przed kolejnym żądaniem (brak downgrade do HTTP, brak skoku na host lokalny)
  i ogranicza liczbę przekierowań;
- **pin hostów per provider** — każdy provider akceptuje tylko własny host API;
  LubimyCzytac dodatkowo akceptuje wyłącznie **własne** URL-e książek (host LC lub
  link względny) z wyników wyszukiwarki;
- **limit rozmiaru** — odpowiedź ponad `MAX_BYTES` jest odrzucana (odczyt
  `MAX_BYTES+1`, bez cichego ucięcia), obowiązuje twardy timeout, a każdy błąd
  sieciowy kończy się `None` (nigdy wyjątkiem widocznym dla UI).

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
