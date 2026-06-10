# Zasoby graficzne GUI

Tu wrzuć grafiki aplikacji. Kod sam je podchwyci — **podmiana pliku wystarczy,
bez zmian w kodzie**.

## Pliki

| Plik | Przeznaczenie | Format | Zalecany rozmiar |
|---|---|---|---|
| `logo.png` | Logo w zakładce „O programie" | PNG z przezroczystością | ~96–160 px wysokości (np. 160×160) |
| `icon.ico` | Ikona okna i pliku `.exe` (Windows, PyInstaller) | ICO wielorozmiarowe | 16, 32, 48, 256 px w jednym `.ico` |

## Uwagi

- **`logo.png`** — gdy plik nie istnieje, zakładka „O programie" pokazuje tekstowy
  zastępnik „EpubForge". Wczytywanie wymaga Pillow (zależność z grupy `gui`).
- **`icon.ico`** — wykorzystywany później w buildzie PyInstaller (Etap 13).
- Trzymaj logo z marginesem i na przezroczystym tle, by dobrze wyglądało w obu
  motywach (jasnym i ciemnym).
