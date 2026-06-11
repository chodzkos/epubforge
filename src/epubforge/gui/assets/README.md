# Zasoby graficzne GUI

Tu wrzuć grafiki aplikacji. Kod sam je podchwyci — **podmiana pliku wystarczy,
bez zmian w kodzie**.

## Pliki

| Plik | Przeznaczenie | Format | Zalecany rozmiar |
|---|---|---|---|
| `logo.png` | Logo w zakładce „O programie" | PNG z przezroczystością | ~400 px szerokości |
| `icon.ico` | Ikona `.exe` i instalatora (Windows, PyInstaller/Inno Setup) | ICO wielorozmiarowe | 16, 32, 48, 64, 128, 256 px w jednym `.ico` |

## Uwagi

- **`logo.png`** — gdy plik nie istnieje, zakładka „O programie" pokazuje tekstowy
  zastępnik „EpubForge". Wczytywanie wymaga Pillow (zależność z grupy `gui`).
  W spakowanym `.exe` logo jest dołączane do bundla i ładowane przez `sys._MEIPASS`.
- **`icon.ico`** — jeśli ten plik **istnieje**, build PyInstaller i instalator
  używają go. Jeśli go **brak**, `build/create_icon.py` generuje placeholder.
  Podmiana na docelową ikonę nie wymaga zmian w kodzie ani spec-ach.
- Trzymaj logo z marginesem i na przezroczystym tle, by dobrze wyglądało w obu
  motywach (jasnym i ciemnym).
