# Walidacja (EpubCheck)

Walidacja przez **EpubCheck 5.x** — oficjalny walidator EPUB (W3C). Uruchamiany jako
`java -jar epubcheck.jar`. W trakcie pasek postępu pracuje w trybie nieokreślonym, a
**Anuluj** przerywa sprawdzanie (kończy proces Javy).

**Wymaga Javy ≥ 11** (np. **Eclipse Temurin / Adoptium**) oraz pliku `epubcheck.jar`.
EpubForge wykrywa je automatycznie (PATH, App Paths, rejestr Adoptium, typowe
katalogi). Gdy brak Javy/jara, zakładka pokazuje instrukcję i przycisk
**Wskaż epubcheck.jar…** (ścieżka zapisuje się w konfiguracji).

## Poziomy wyników

- **FATAL / ERROR** — łamią standard; czytniki lub sklepy mogą plik odrzucić
- **WARNING** — zalecane poprawki
- **INFO** — informacyjne (w tym `usage`)

Wyniki są **klikalne**: dwuklik wiersza z lokalizacją przeskakuje do miejsca w
**Edytorze**. **Eksport…** zapisuje raport jako JSON lub HTML.

Przyciski **Sigil** i **Calibre Editor** w górnym pasku otwierają cały zaznaczony
plik `.epub`, a bez zaznaczenia mogą użyć pliku ostatniego raportu. Nie przekazują
pojedynczego zasobu wskazanego w tabeli. Podczas trwającej walidacji są zablokowane,
aby zewnętrzny program nie zmienił pliku czytanego przez EpubCheck lub Ace.

## Dostępność (DAISY Ace)

**Sprawdź dostępność (Ace)** — audyt zgodności z WCAG / EPUB Accessibility (European
Accessibility Act obowiązuje e-booki od 2025). Naruszenia trafiają do tej samej,
**klikalnej** tabeli co EpubCheck. Wymaga narzędzia `ace`
(`npm install -g @daisy/ace`); bez niego funkcja jest wyszarzona.

> Czy Java / EpubCheck / Ace są wykryte **teraz** — sprawdzisz w dolnym pasku statusu.
> Odpowiedniki CLI: `epubforge check`, `epubforge a11y` (zakładka **Wiersz poleceń**).
> Pełny opis: `docs/user-guide.md`.
