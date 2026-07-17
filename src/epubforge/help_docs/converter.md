# Konwerter → EPUB

Konwertuje pliki wejściowe do **EPUB**. Pasek postępu pokazuje procent z Calibre,
a przycisk **Anuluj** przerywa konwersję (kończy proces silnika).

## Obsługiwane wejście

- Tekst: `.txt` `.md` `.markdown`
- Dokumenty: `.docx` `.odt` `.rtf`
- Strony: `.html` `.htm`
- Inne: `.pdf` `.fb2` `.lit`
- Kindle: `.mobi` `.azw3` `.azw` `.prc` — wejście Kindle wymaga Calibre

## Opcje

- **Tytuł / Autor / Język / Okładka** — metadane wynikowego EPUB (opcjonalne)
- **Folder wyjściowy** — puste = zapis obok pliku źródłowego

## Silnik

- **Auto** — wybiera dostępne narzędzie
- **Pandoc** — szybki, dobry do tekstu i dokumentów
- **Calibre** — szeroki zakres formatów; **wymagany dla wejścia Kindle**
- **pdf2md** — **zalecany silnik dla PDF** → EPUB (lepszy skład niż Calibre)

**PDF:** po dodaniu pliku PDF — gdy wykryto pdf2md — pojawia się wybór
**pdf2md (zalecany)** vs **Calibre (eksperymentalny)**; wybór jest zapamiętywany.
Przycisk **Otwórz w pdf2md** przekazuje plik do jego GUI. Bez pdf2md tryb Auto dla PDF
wraca do Calibre.

**DRM:** pliki Kindle zabezpieczone DRM nie są konwertowane — EpubForge nie usuwa
zabezpieczeń.

> Czy Pandoc / Calibre / pdf2md są dostępne — sprawdzisz w dolnym pasku statusu
> (np. `Pandoc: OK`, `Calibre: brak`). Ten sam efekt z linii poleceń:
> `epubforge convert` (zakładka **Wiersz poleceń**). Pełny opis: `docs/user-guide.md`.
