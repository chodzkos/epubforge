# Polityka bezpieczeństwa

Dziękujemy za pomoc w utrzymaniu bezpieczeństwa **EpubForge**. Ten dokument
opisuje, które wersje są wspierane oraz jak zgłaszać podatności.

## Wspierane wersje

Poprawki bezpieczeństwa trafiają do najnowszej linii wydawniczej. Starsze wersje
nie są łatane — zalecamy aktualizację do najnowszej.

| Wersja  | Wspierana          |
|---------|--------------------|
| 3.0.x   | :white_check_mark: |
| < 3.0   | :x:                |

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

limits = ArchiveLimits(max_entry_size=1024**3)  # np. 1 GiB na wpis
with Epub(path, limits=limits) as epub:
    ...
```

Zapis kopiuje niezmienione wpisy **strumieniowo** (stały bufor), więc pamięć
szczytowa nie rośnie z rozmiarem największego wpisu.

Niezaufany XML (container, OPF, NCX, XHTML) parsujemy **wyłącznie** przez jeden
utwardzony moduł `core/_xml_safe.py` — poza nim w kodzie nie ma bezpośredniego
`etree.XMLParser`/`fromstring`/`parse`. Parser ma jawnie ustawione
`resolve_entities=False`, `no_network=True`, `load_dtd=False`,
`dtd_validation=False` (DOCTYPE jest zachowany do serializacji, ale **nie
wykonywany**), co chroni przed XXE, dereferencją `SYSTEM file://`/`http://` i
rozdmuchaniem encji (billion laughs). Moduł udostępnia tryby strict/recover oraz
wariant na drzewo, a każdy przyjmuje limit rozmiaru `max_bytes` sprzężony z
limitem wpisu tekstowego EPUB (odrzucenie „dużego XML" przez `XmlSecurityError`).

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

## Procesy zewnętrzne i bezpieczny zapis

Wszystkie konwertery i walidatory (Pandoc, Calibre, EpubCheck, Ace, Kindle
Previewer…) uruchamiają procesy przez **jeden wspólny runner**
(`core/process.py`). Runner:

- egzekwuje **domyślne, konfigurowalne timeouty** (`ProcessLimits`) — proces w
  zawieszeniu nie blokuje aplikacji w nieskończoność;
- **ubija całe drzewo/grupę procesu** przy anulowaniu lub timeoucie (na POSIX
  przez `os.killpg` na nowej sesji, na Windows przez `taskkill /T`), więc żaden
  proces-„sierota" nie zostaje po przerwaniu;
- **ogranicza przechowywany log** (z licznikiem uciętych bajtów) i stosuje
  **ograniczoną kolejkę** (backpressure) — gadatliwy proces nie wyczerpie pamięci;
- dekoduje wyjście z `errors="replace"` (odporność na błędy kodowania).
  Tryb synchroniczny i strumieniowy mają **identyczną semantykę** (jeden silnik).
  Tor DETEKCJI narzędzi ma osobną, celowo prostą mechanikę sond i nie korzysta z
  tego runnera.

Zapis EPUB (`Epub.save`) jest **bezpieczny dla oryginału**: nowa treść trafia do
**unikalnego pliku tymczasowego w katalogu docelowym**, jest **fsyncowana** (plik,
a na POSIX także katalog) i podmieniana **atomowo** (`os.replace`). Przy dowolnym
błędzie (brak miejsca, brak uprawnień, przerwana podmiana) temp jest sprzątany, a
**oryginał zostaje nietknięty i czytelny**. Nadpisanie oryginału (także gdy
`output_path` wskazuje na źródło) poprzedza **rotowany backup** z konfigurowalną
retencją, więc żaden zapis nie kasuje po cichu jedynej kopii bezpieczeństwa.

## Łańcuch dostaw i CI (least privilege)

Pipeline CI trzyma się zasady **minimalnych uprawnień**, żeby kompromitacja
zależności lub akcji nie dała dostępu do zapisu w repozytorium ani do publikacji
wydań:

- **jawne uprawnienia per job** — domyślny poziom workflow to `permissions: {}`
  (zero); token nadajemy dopiero na poziomie joba. Joby uruchamiające kod
  zależności (`test`, build `.exe`, `pdoc`, CodeQL) dostają wyłącznie
  `contents: read` i checkout z `persist-credentials: false` — nie widzą tokenu z
  prawem zapisu ani utrwalonych credentials;
- **rozdzielony build i publikacja** — job budujący nie może publikować. Osobny
  job `release` (`contents: write`) i `deploy` Pages (`pages`/`id-token: write`)
  **nie instalują zależności projektu**: konsumują tylko gotowy, zweryfikowany
  artefakt (`sha256sum -c` przed utworzeniem Release; oficjalny `deploy-pages` bez
  checkoutu repo);
- **piny po pełnym SHA** — wszystkie akcje GitHub oraz hooki `pre-commit` przypięte
  po pełnym SHA commitu (nie po ruchomym tagu), więc dostawca nie podmieni ich po
  cichu przez re-tag;
- **przypięte narzędzia zewnętrzne** — Inno Setup instalowany w dokładnej wersji z
  wymuszoną weryfikacją sumy (`--require-checksums`, fail-closed);
- **skan sekretów** — hook `gitleaks` (pre-commit) blokuje przypadkowe klucze,
  tokeny i hasła, zanim trafią do historii; uzupełnia go cotygodniowy CodeQL.

## Zaufany release i weryfikacja pochodzenia

Każde wydanie jest **weryfikowalne przez odbiorcę** i spójne z wersją w kodzie:

- **kontrola zgodności tagu z wersją** — przed budową sprawdzamy, że tag `vX.Y.Z`
  odpowiada `epubforge.__version__` (`build/check_tag_version.py`); rozjazd
  przerywa release, więc opublikowana wersja zawsze zgadza się z tagiem;
- **pełny test przed publikacją** — sdist+wheel budują się i instalują czysto, oba
  pliki `.exe` (portable + instalator) przechodzą smoke test `--self-check`;
- **`SHA256SUMS`** — sumy wszystkich artefaktów są liczone w nieuprzywilejowanym
  jobie, weryfikowane przed publikacją (`sha256sum -c`) i **dołączane do wydania**,
  więc każdy może potwierdzić integralność pobranego pliku;
- **SBOM (CycloneDX/SPDX)** — pełny wykaz zależności dołączony do wydania;
- **GitHub artifact attestation** — provenance każdego artefaktu (kto/co/skąd zbudował);
  odbiorca weryfikuje pochodzenie poleceniem:

  ```bash
  gh attestation verify epubforge.exe --repo chodzkos/epubforge
  sha256sum -c SHA256SUMS
  ```

- **podpis Authenticode** — pliki `.exe` są podpisywane, **jeśli** w repozytorium
  skonfigurowano bezpieczny certyfikat i sekret (krok warunkowy; brak sekretu nie
  blokuje wydania niepodpisanego).

## Checklista ustawień repozytorium

Poniższe ustawienia utrzymują integralność gałęzi i procesu (do skonfigurowania w
ustawieniach repozytorium — poza kodem):

- [ ] **Branch protection / ruleset** na `main`: wymagany PR, wymagane statusy,
      brak bezpośrednich pushy, aktualność gałęzi przed merge, liniowa historia;
- [ ] **wymagane statusy**: `Tests` (matryca OS/Python), `CodeQL`,
      `Package (sdist + wheel)`, `Security tests`;
- [ ] **Secret scanning** + **push protection** włączone;
- [ ] **Dependabot alerts** (i aktualizacje bezpieczeństwa) włączone;
- [ ] **Private Vulnerability Reporting** włączone (kanał zgłoszeń, patrz niżej);
- [ ] środowisko `github-pages` i (opcjonalnie) środowisko podpisu z sekretem
      certyfikatu ograniczonym do gałęzi wydań.

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
