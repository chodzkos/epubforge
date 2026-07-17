# Spis treści (TOC)

Podgląd, generowanie, naprawa i edycja drzewa spisu treści (zapis jako `nav` + `ncx`,
kopia `.bak`). EpubForge wczyta istniejący spis (nav.xhtml lub toc.ncx).

- **Generuj** — buduje spis z nagłówków `h1..hN`; najgłębszy poziom ustawia **Poziom:**
- **Napraw** — usuwa martwe wpisy (linki do nieistniejących miejsc; z potwierdzeniem).
  Martwe wpisy są na czerwono z tooltipem
- **Edycja drzewa** — dwuklik tytułu zmienia tekst; przyciski **Dodaj / Usuń**,
  **⬆ ⬇** (kolejność wśród rodzeństwa) i **⬅ ➡** (poziom zagnieżdżenia) oraz
  **drag&drop** zmieniają strukturę
- **Zapisz do EPUB** — zapisuje `nav` i `ncx`

Niezapisane zmiany są pilnowane przy zmianie pliku i zamknięciu.

> Odpowiednik CLI: `epubforge toc --show / --generate / --repair` (zakładka
> **Wiersz poleceń**). Pełny opis: `docs/user-guide.md`.
