# 💡 EpubForge — Features (przyszłość)

Lista funkcji do rozważenia **po** zakończeniu wersji 1.0. Każda funkcja może stać się osobnym etapem.

---

## 🚀 Priorytet wysoki

### F1. Wielojęzyczność interfejsu (i18n)
- Zewnętrzne pliki `.po` / `.mo` (gettext) dla PL/EN/DE
- Auto-detekcja języka systemu
- Przełącznik w GUI
- **Estymacja:** 4-6 godzin

### F2. Walidacja przez EpubCheck
- Wrapper na EpubCheck 5.x (JAR)
- Parsowanie wyników do strukturyzowanej listy błędów
- Klikalne błędy w GUI - skok do problematycznego pliku
- **Estymacja:** 6-8 godzin

### F3. Edytor wewnętrzny (lite)
- Podgląd plików HTML/CSS w EPUB (read-only)
- Podstawowa edycja (z syntax highlighting)
- Nie konkurujemy z Sigil - tylko quick fix
- **Estymacja:** 12-16 godzin

### F4. Batch processing z presetami
- Zapisywanie zestawów ustawień jako "preset" (np. "Mój standard PL")
- Aplikacja preset do wielu plików naraz
- Zapamiętane w `config.json`
- **Estymacja:** 4 godziny

### F5. Linux i macOS .deb/.dmg
- GitHub Actions matrix: windows + ubuntu + macos
- AppImage dla Linux
- DMG dla macOS (wymaga certyfikatu Apple Developer)
- **Estymacja:** 8-12 godzin (głównie konfig)

---

## 🎯 Priorytet średni

### F6. Code signing dla Windows
- Eliminuje SmartScreen warning
- Opcje:
  - Komercyjny cert (Sectigo, ~250 EUR/rok)
  - **Azure Trusted Signing** (darmowy dla małych projektów!)
  - Self-signed (ostrzeżenie pozostaje)
- **Estymacja:** 2-4 godziny + dokumentacja

### F7. Konwersja MOBI → EPUB
- Wsparcie odwrotne (KFX → EPUB nie jest możliwe bez DRM removal)
- Calibre + kindleunpack (jeśli legalnie posiadasz plik)
- **Estymacja:** 3-4 godziny

### F8. Statystyki książki
- Liczba słów, stron (szacowana)
- Język wykryty (langdetect)
- Reading time estimate
- Najczęstsze słowa (chmurka tagów)
- Eksport raportu do PDF/HTML
- **Estymacja:** 6-8 godzin

### F9. Automatyczna optymalizacja obrazów
- Kompresja JPEG/PNG w EPUB
- Konwersja do WebP (z fallbackiem)
- Resize dla mobile screens
- Wybór jakości
- **Estymacja:** 4-6 godzin

### F10. Spis treści generator
- Auto-generacja TOC z nagłówków h1-h6
- Edycja struktury TOC (drag-drop)
- Naprawa uszkodzonych TOC
- **Estymacja:** 8-10 godzin

### F11. CSS preset library
- Wbudowane szablony CSS dla różnych potrzeb:
  - "Reader-friendly" (większa interlinia, większy font)
  - "Print-like" (jak książka papierowa)
  - "Dark mode for OLED Kindle"
  - "Manga / Comic" (RTL, justify)
- Możliwość importu własnych
- **Estymacja:** 4 godziny

---

## 🔬 Priorytet niski / eksperymentalne

### F12. AI Cover Generator
- Integracja z lokalnym Stable Diffusion lub API (DALL-E, Midjourney)
- Generowanie okładki z metadanych (tytuł, gatunek)
- **Estymacja:** 8-12 godzin

### F13. AI Translator
- Wykorzystanie LLM API (Claude/GPT/lokalne) do tłumaczenia EPUB
- Zachowanie formatowania
- Postupne tłumaczenie z postępem
- **Estymacja:** 12-16 godzin

### F14. AI Style Improver
- Sprawdzanie stylistyki / gramatyki (LanguageTool)
- Sugestie poprawek (nie auto-apply)
- **Estymacja:** 8 godzin

### F15. OCR dla skanów PDF
- Tesseract dla obrazowych PDF
- Konwersja skan → EPUB z tekstem
- **Estymacja:** 10-14 godzin

### F16. Audio book generator
- Konwersja EPUB → MP3 przez TTS (Microsoft Edge TTS, ElevenLabs API)
- Generowanie M4B (audiobook format)
- **Estymacja:** 12-16 godzin

### F17. Cloud sync
- Synchronizacja biblioteki EPUB z Dropbox/Google Drive/OneDrive
- Backup metadanych do chmury
- **Estymacja:** 16-20 godzin (auth!, OAuth)

### F18. Kindle send-to-device
- Bezpośredni upload do Kindle przez Send to Kindle
- Konfiguracja email Kindle w `config.json`
- **Estymacja:** 4 godziny

---

## 🛠️ Quality of life

### Q1. Drag & drop folderów (rekurencyjnie)
Już mamy D&D plików, dodać foldery z `os.walk()` po EPUB-ach.

### Q2. Recent files w menu
Lista ostatnio otwieranych plików w menu File.

### Q3. Undo/Redo dla metadata edit
History stack w GUI dla nawigacji wstecz.

### Q4. Keyboard shortcuts panel
Lista skrótów dostępna przez `Ctrl+/`.

### Q5. CLI shell completions
Bash/Zsh/PowerShell auto-completion dla `epubforge`.

### Q6. Progress notifications
Native notyfikacje Windows/macOS po zakończeniu długiej konwersji.

### Q7. Dark mode auto-switch
Wykrywanie motywu systemowego, auto-switch.

### Q8. File watcher mode
`epubforge watch ./folder` - auto-fix przy każdej zmianie pliku.

---

## 🔌 Integracje

### I1. Calibre Library integration
- Czytanie biblioteki Calibre (`metadata.db`)
- Edycja metadanych ze synchronizacją

### I2. Goodreads / OpenLibrary metadata fetch
- Wpisz tytuł/ISBN → pobierz metadane + okładkę

### I3. Wikidata enrichment
- Auto-uzupełnianie metadanych z Wikidata

### I4. Plugin system
- API dla rozszerzeń (entry points)
- Hot-reload pluginów
- Marketplace pluginów (?)

---

## 📊 Analytics / monitoring (opcjonalnie)

### A1. Opt-in telemetry
- Anonimowe statystyki użycia (Sentry / Plausible)
- TYLKO za zgodą użytkownika
- Pomaga w priorytecie features

### A2. Crash reporting
- Auto-raport crashy na Sentry
- Z możliwością wyłączenia

---

## 🎓 Edukacja / Community

### E1. Tutorial w aplikacji
- Pierwsze uruchomienie - guided tour
- Tooltips z linkami do dokumentacji

### E2. Discord / Matrix community
- Serwer dla użytkowników i developerów

### E3. YouTube tutorials
- Screencasty z głównych funkcji

---

## 📝 Notatki implementacyjne

### Format pliku konfiguracji
Rozważyć migrację `config.json` → `config.toml` (czytelniejszy, support komentarzy).

### Cross-platform packaging
- Windows: PyInstaller (sprawdzone)
- macOS: py2app + DMG
- Linux: PyInstaller + AppImage
- Universal: Flatpak (Linux), Snap (Linux), MSIX (Windows 10+)

### Performance optimization (dla v2.0)
Jeśli aplikacja stanie się popularna i ludzie będą konwertować setki plików:
- Rewrite hot paths w Rust (PyO3)
- Async I/O dla operacji na ZIP
- Multiprocessing dla batch operations

---

## 🗳️ Jak głosować na features

Po wydaniu v1.0 - utwórz GitHub Discussions / Issues z label `feature-request`.
Reakcje (👍) decydują o priorytecie.

Co kwartał - przegląd i wybór 3-5 features do najbliższego release.

---

**Pamiętaj:** Nie wszystko musi być w aplikacji. Czasem lepiej zostawić niszowe funkcje wtyczkom, a core utrzymać prostym i niezawodnym.
