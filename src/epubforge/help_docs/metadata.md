# Metadane (Dublin Core)

Edycja metadanych **Dublin Core** zapisywanych w pliku OPF EPUB-a. Poprawne
metadane to lepsze katalogowanie w czytnikach i sklepach. Zapis tworzy kopię
zapasową `.bak`.

| Pole | Element OPF | Uwagi |
|---|---|---|
| Tytuł | `dc:title` | Tytuł książki |
| Cykl | `meta` (calibre:series) | Nazwa serii i numer tomu (opcjonalnie) |
| Autorzy | `dc:creator` | Jeden na linię; format: Nazwisko, Imię |
| Język | `dc:language` | Kod języka, np. `pl`, `en` |
| Wydawca | `dc:publisher` | Nazwa wydawcy |
| Data | `dc:date` | Format ISO: `RRRR-MM-DD` |
| Identyfikator | `dc:identifier` | ISBN lub UUID |
| Liczba stron | `meta property="schema:numberOfPages"` | Dodatnia liczba całkowita; tylko EPUB 3 |
| Tematy | `dc:subject` | Tematy/tagi — jeden na linię |
| Opis | `dc:description` | Streszczenie książki |

## Liczba stron

W EPUB 3 pole **Liczba stron** można wpisać ręcznie, zastąpić wartością pobraną
z katalogu albo wyczyścić. **Zapisz** utrwala wszystkie zmiany metadanych razem;
puste pole usuwa istniejące `schema:numberOfPages`. EPUB 2 nie obsługuje tej
właściwości — pole oraz przycisk **Oblicz** pozostają nieaktywne do czasu konwersji
pliku do EPUB 3.

Przycisk **Oblicz** analizuje tekst poza głównym wątkiem i wstawia wartość z modułu
Statystyki (domyślnie 250 słów na stronę). To tylko **estymacja objętości tekstu**,
a nie pewna liczba stron konkretnego wydania papierowego. Wynik można poprawić
przed zapisaniem.

Te dane nie są też numerem „strony podglądu” z symulatora czytnika. Strony
podglądu powstają technicznie z bieżącego viewportu i ustawień renderowania, więc
ich liczba może zmieniać się wraz z profilem.

## Pobieranie metadanych z sieci

Przycisk **Pobierz metadane…** dociąga dane po **ISBN** z łańcucha źródeł:
**Biblioteka Narodowa → LubimyCzytac → Open Library → Google Books**. W podglądzie
zaznaczasz, **które pola nadpisać** — nigdy nie dzieje się to po cichu.

- **ISBN e-booka a katalog BN** — e-booki mają własny ISBN wydania elektronicznego,
  którego katalog BN (głównie wydania papierowe) często nie ma. Gdy ISBN nie trafia,
  aplikacja automatycznie **dopasowuje książkę po tytule** (z metadanych pliku) i
  wyraźnie to zaznacza w komunikacie („dopasowanie po tytule — ISBN e-wydania
  nieobecny w BN"). Uzupełniane są tylko metadane bibliograficzne; **ISBN pliku
  pozostaje niezmieniony** — zweryfikuj dopasowanie przed zatwierdzeniem.
- **Bez ISBN** — wpisz **Tytuł/Autor** i użyj „Szukaj wg tytułu": wyszukiwarka
  LubimyCzytac zwraca listę kandydatów z oceną dopasowania; wybór należy do Ciebie
  (poniżej progu pewności nic nie jest zaznaczane automatycznie).
- **Liczba stron** z katalogu opisuje wskazane wydanie papierowe. Po zaakceptowaniu
  trafia do widocznego formularza, gdzie można ją sprawdzić lub zmienić; samo
  pobranie nie zapisuje pliku.

## Tagi (taksonomia + AI, opt-in)

Sekcja **Tagi** proponuje tagi po polsku z kaskady źródeł: deskryptory z metadanych,
taksonomia PL, a opcjonalnie model AI.

- **Zaproponuj tagi** — mapuje deskryptory/kategorie na kanoniczne tagi taksonomii;
  wybierasz, które dopisać do `dc:subject` (nigdy ciche).
- **Użyj AI (opt-in)** — dołącza tagi z modelu; **domyślnie wyłączone**. Domyślny
  backend to lokalna **Ollama** (bez klucza); chmury (OpenAI, Anthropic, Gemini,
  DeepSeek, GLM) ustawisz w **Ustawienia AI…**. Klucz API czytany jest wyłącznie ze
  **zmiennej środowiskowej** (w konfiguracji trzymana jest tylko jej nazwa, nigdy sam
  klucz).

## Edycja w zewnętrznym programie

Przyciski **Sigil**, **Calibre Editor** i **Viewer** otwierają wybrany plik wprost w
zewnętrznym programie (jeśli wykryty) — do głębszej edycji lub wiernego podglądu.
Wsadowe wzbogacanie wielu plików naraz robi komenda CLI `epubforge enrich`
(zakładka **Wiersz poleceń**).

> Pełny opis funkcji: `docs/user-guide.md` w repozytorium. Status wykrytych narzędzi
> widać na dolnym pasku GUI.
