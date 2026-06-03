# 📘 EpubForge — Instrukcja startu

Krok po kroku od zera do działającego projektu. Zakładam, że masz już:
- ✅ Windows 10/11
- ✅ WSL z Ubuntu
- ✅ VS Code z rozszerzeniem Claude Code
- ✅ Konto na GitHub

---

## Krok 1 — Przygotowanie konta GitHub (5 min)

### 1.1 Utwórz nowe repozytorium
1. Wejdź na [github.com/new](https://github.com/new)
2. **Repository name**: `epubforge`
3. **Description**: „Modern EPUB toolkit — validate, fix, convert, hyphenate"
4. **Public** (bo MIT)
5. **NIE** zaznaczaj „Initialize with README" (zrobimy to lokalnie)
6. Kliknij **Create repository**

### 1.2 Zainstaluj GitHub CLI (jeśli jeszcze nie masz)
W WSL terminal:
```bash
# Sprawdź czy masz
gh --version

# Jeśli nie - zainstaluj
sudo apt update && sudo apt install gh -y
gh auth login
```
Wybierz GitHub.com → HTTPS → Yes (authenticate) → Login with web browser → skopiuj kod → otwórz link.

### 1.3 Skonfiguruj git (tylko raz w życiu)
```bash
git config --global user.name "Twoje Imię Nazwisko"
git config --global user.email "twoj@email.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

---

## Krok 2 — Klonowanie i pierwszy commit (10 min)

### 2.1 Otwórz WSL w folderze projektowym
W WSL terminal:
```bash
cd ~
mkdir -p projekty
cd projekty
git clone https://github.com/TWOJ_LOGIN/epubforge.git
cd epubforge
```

### 2.2 Skopiuj pliki startowe z tego pakietu
Pobierz cały folder `epubforge_starter/` i skopiuj jego zawartość do `~/projekty/epubforge/`.

W WSL:
```bash
# Przykład - dostosuj ścieżkę do swojej
cp -r /mnt/c/Users/TWOJ_USER/Downloads/epubforge_starter/* ~/projekty/epubforge/
cp -r /mnt/c/Users/TWOJ_USER/Downloads/epubforge_starter/.github ~/projekty/epubforge/
cp /mnt/c/Users/TWOJ_USER/Downloads/epubforge_starter/.gitignore ~/projekty/epubforge/
```

### 2.3 Pierwszy commit
```bash
cd ~/projekty/epubforge
git add .
git commit -m "chore: initial project scaffolding"
git push -u origin main
```

✅ **Punkt kontrolny**: wejdź na github.com/TWOJ_LOGIN/epubforge — powinieneś widzieć wszystkie pliki.

---

## Krok 3 — Otwórz projekt w VS Code (2 min)

```bash
cd ~/projekty/epubforge
code .
```
VS Code otworzy się z projektem. Po prawej stronie (lub `Ctrl+Esc`) powinien być panel **Claude Code**.

---

## Krok 4 — Praca z Claude Code (kluczowe!)

### Jak działa workflow:

Dla **każdego etapu** z `ROADMAP.md`:

1. **Otwórz `PROMPTS.md`** i znajdź prompt dla bieżącego etapu
2. **Skopiuj prompt** do okna Claude Code
3. **Claude utworzy gałąź** (np. `feature/stage-1-core-epub`), napisze kod, testy i commity
4. **Sprawdź ręcznie** czy wszystko działa (uruchom `pytest`)
5. **Zatwierdź zmiany** — Claude pushuje na GitHub
6. **Utwórz Pull Request**:
   ```bash
   gh pr create --title "Stage N: ..." --body "..."
   ```
7. **Sprawdź czy CI przeszedł** (zielony check na GitHubie)
8. **Zmerguj PR** (squash merge zalecany):
   ```bash
   gh pr merge --squash --delete-branch
   ```
9. **Wróć na main**:
   ```bash
   git checkout main && git pull
   ```
10. **Przejdź do następnego etapu**

---

## Krok 5 — Środowisko dewelopera (opcjonalnie, w WSL)

Claude Code może to zrobić za Ciebie, ale jeśli chcesz testować lokalnie:

```bash
# Python 3.10+
sudo apt install python3.10 python3.10-venv python3-tk -y

# Wirtualne środowisko
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Pre-commit hooks (uruchamiają lint + mypy przed każdym commitem)
pre-commit install
```

Sprawdzenie:
```bash
pytest                      # uruchom testy
ruff check .                # linter
mypy src/                   # type checker
pre-commit run --all-files  # wszystkie hooki naraz
epubforge --help            # CLI działa
```

---

## Co masz zrobić sam (lista kontrolna)

| Zadanie | Czas | Wymaga uwagi |
|---|---|---|
| ✅ Utworzyć repo na GitHub | 2 min | Tak |
| ✅ Zainstalować GitHub CLI | 5 min | Raz |
| ✅ Skonfigurować git (imię, email) | 2 min | Raz |
| ✅ Skopiować pliki startowe i pchnąć | 5 min | Raz |
| ✅ Przeklejać prompty z `PROMPTS.md` | sukcesywnie | Tak |
| ✅ Manualnie testować GUI (Claude nie widzi ekranu) | po każdym etapie z GUI | Tak |
| ✅ Akceptować merge PR-ów | po każdym etapie | Tak |
| ✅ Tagować release v0.x.0 po ważnych etapach | po etapie 9 | Tak |

## Co zrobi Claude Code (sam)

- Pisanie całego kodu Python
- Tworzenie i przełączanie gałęzi git
- Pisanie testów jednostkowych
- Uruchamianie testów (`pytest`)
- Lintowanie i naprawianie błędów (`ruff`, `mypy`)
- Tworzenie commitów z conventional commits
- Pushowanie na GitHub (po Twoim zatwierdzeniu)
- Otwieranie Pull Requestów
- Aktualizacja dokumentacji
- Generowanie ikon, szablonów

---

## Najczęstsze problemy

**Q: Claude Code mówi „permission denied" przy push**
A: Sprawdź `gh auth status`. Jeśli wygasł token: `gh auth refresh`.

**Q: VS Code nie widzi WSL**
A: Zainstaluj rozszerzenie **WSL** (Microsoft) w VS Code, otwórz folder przez `code .` z poziomu WSL.

**Q: Testy nie uruchamiają tkinter w CI**
A: To normalne — GitHub Actions na Linuxie nie ma displayu. Testy GUI uruchamiamy tylko lokalnie przez `xvfb-run pytest tests/gui/`.

**Q: PyInstaller .exe nie chce się zbudować w WSL**
A: PyInstaller dla Windows wymaga Windowsa. Zostawmy to GitHub Actions (workflow `build.yml`).

---

## Co robić w razie problemów

1. **Zerknij na `CLAUDE.md`** — zawiera pułapki techniczne
2. **Zerknij na `ROADMAP.md`** — sprawdź czy nie pominąłeś etapu
3. **Otwórz issue na GitHubie** swojego repo — Claude może mu pomóc je analizować
4. **W ostateczności**: `git reset --hard HEAD~1` cofa ostatni commit lokalnie

---

🚀 **Gotowy? Zacznij od `ROADMAP.md`, potem otwórz `PROMPTS.md` i wklej Etap 0 do Claude Code.**
