# Eksport Kindle

Wsadowy eksport EPUB do formatów Kindle: **KFX / MOBI / AZW3**. Opcjonalnie napraw
EPUB przed konwersją. Pasek postępu i przycisk **Anuluj** działają jak w Konwerterze
(anulowanie kończy proces silnika).

## Silnik KFX

- **Calibre + wtyczka KFX Output** — **ZALECANE**
- **Kindle Previewer 3** — eksperymentalny, wrażliwy na nieidealny EPUB

## Silnik MOBI / AZW3

- **Calibre `ebook-convert`** — ZALECANE (nowoczesny, rozwijany)
- **kindlegen** — generator MOBI Amazona, **oficjalnie wycofany** (2018); działa, ale
  przestarzały — preferuj Calibre

> Czy Calibre (+ wtyczka KFX), Kindle Previewer 3 lub kindlegen są dostępne —
> zobaczysz w dolnym pasku statusu. Odpowiedniki CLI: `epubforge kfx`, `epubforge mobi`
> (zakładka **Wiersz poleceń**). Pełny opis: `docs/user-guide.md`.
