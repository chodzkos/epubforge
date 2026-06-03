# 🔄 Kod do wykorzystania ze starego projektu

Ten plik zawiera fragmenty kodu ze starego `gui_main.py` (epubtools-suite) gotowe do skopiowania w nowej strukturze modułowej.

**Sposób użycia:** Gdy Claude Code dotrze do danego etapu i zacznie pisać moduł, możesz wskazać mu odpowiednią sekcję tego pliku jako bazę. Claude zrefaktoryzuje kod zgodnie z nową architekturą (typing, dataclasses, modułowość).

---

## 📦 Etap 1 — `core/epub.py` (bezpieczny zapis ZIP)

### Wzorzec zapisu EPUB zgodny ze specyfikacją:

```python
import os
import zipfile
from pathlib import Path


def write_epub(target: Path, files: dict[str, bytes]) -> None:
    """Zapisz EPUB zachowując wymogi specyfikacji.

    Args:
        target: Ścieżka docelowa pliku .epub
        files: Słownik {ścieżka_wewnętrzna: zawartość_bytes}

    Wymogi spec EPUB:
        1. mimetype PIERWSZY w archiwum
        2. mimetype BEZ kompresji (ZIP_STORED)
        3. mimetype = dokładnie "application/epub+zip" (bez newline)
        4. reszta plików z kompresją
        5. zapis atomowy (tmp + replace)
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w") as zf:
            # 1+2+3. mimetype PIERWSZY, BEZ kompresji
            zf.writestr(
                "mimetype",
                "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            # 4. pozostałe pliki z kompresją
            for name, data in files.items():
                if name == "mimetype":
                    continue  # już zapisany jako pierwszy
                zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        # 5. atomowe zastąpienie
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()  # sprzątanie po błędzie
        raise


def read_opf_path(zf: zipfile.ZipFile) -> str:
    """Odczytaj ścieżkę do OPF z META-INF/container.xml.

    NIE zgaduj ścieżki OPF - musi pochodzić z container.xml!
    """
    import xml.etree.ElementTree as ET

    container = zf.read("META-INF/container.xml")
    root = ET.fromstring(container)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = root.find(".//c:rootfile", ns)
    if rootfile is None:
        raise ValueError("Brak rootfile w container.xml — uszkodzony EPUB")
    return rootfile.attrib["full-path"]
```

**Test sprawdzający poprawność:**
```python
def test_mimetype_is_first_and_stored(tmp_path):
    target = tmp_path / "test.epub"
    write_epub(target, {"OEBPS/content.opf": b"<package/>"})

    with zipfile.ZipFile(target) as zf:
        # mimetype musi być PIERWSZY
        assert zf.namelist()[0] == "mimetype"
        # mimetype musi być NIESKOMPRESOWANY
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED
        # zawartość dokładnie ta wymagana
        assert zf.read("mimetype") == b"application/epub+zip"
```

---

## 📦 Etap 3 — `core/config.py`

### Skopiuj ze starego `gui_main.py`:

```python
import json
import sys
from pathlib import Path

def _config_path() -> Path:
    """Lokalizacja config.json — obok exe lub w ~/.config/epubforge/"""
    if hasattr(sys, "_MEIPASS"):  # PyInstaller bundle
        # Plik obok exe, NIE w _MEIPASS (bo to się resetuje)
        return Path(sys.executable).parent / "config.json"
    return Path.home() / ".config" / "epubforge" / "config.json"


def load_config() -> dict:
    """Wczytaj config.json. Zwraca {} jeśli nie istnieje."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    """Zapisz config atomowo (przez plik tymczasowy)."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    tmp.replace(path)  # atomic on POSIX, near-atomic on Windows
```

**Zmiany do wprowadzenia:**
- Wszystko jako klasa `Config` z metodami `load()`, `save()`, `get(key)`, `set(key, value)`
- Typing
- Docstring po polsku

---

## 🔍 Etap 3 — `core/detection.py`

### Skopiuj ze starego `gui_main.py`:

```python
import shutil
import subprocess
import sys
import os
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run_version_check(exe: str, args: list[str] = ["--version"]) -> str:
    """Zwraca wersję narzędzia lub pusty string."""
    try:
        result = subprocess.run(
            [exe] + args,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
        return result.stdout.split("\n")[0].strip()
    except Exception:
        return ""


def _find_pandoc() -> str | None:
    return shutil.which("pandoc")


def _find_calibre_ebook_convert() -> str | None:
    # PATH first
    exe = shutil.which("ebook-convert")
    if exe:
        return exe
    
    # Windows typical locations
    if sys.platform == "win32":
        for base in [
            r"C:\Program Files\Calibre2",
            r"C:\Program Files (x86)\Calibre2",
        ]:
            candidate = Path(base) / "ebook-convert.exe"
            if candidate.exists():
                return str(candidate)
    
    # macOS
    if sys.platform == "darwin":
        candidate = Path("/Applications/calibre.app/Contents/MacOS/ebook-convert")
        if candidate.exists():
            return str(candidate)
    
    return None


def _find_calibre_viewer() -> str | None:
    # Analogicznie do _find_calibre_ebook_convert ale szukamy "ebook-viewer"
    exe = shutil.which("ebook-viewer")
    if exe:
        return exe
    if sys.platform == "win32":
        for base in [r"C:\Program Files\Calibre2", r"C:\Program Files (x86)\Calibre2"]:
            c = Path(base) / "ebook-viewer.exe"
            if c.exists():
                return str(c)
    return None


def _find_sigil() -> str | None:
    exe = shutil.which("sigil")
    if exe:
        return exe
    if sys.platform == "win32":
        for base in [
            r"C:\Program Files\Sigil",
            r"C:\Program Files (x86)\Sigil",
        ]:
            candidate = Path(base) / "Sigil.exe"
            if candidate.exists():
                return str(candidate)
    return None


def _find_kindle_previewer() -> str | None:
    """Kindle Previewer 3 — Windows tylko."""
    if sys.platform != "win32":
        return None
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        candidate = Path(local_appdata) / "Amazon" / "Kindle Previewer 3" / "Kindle Previewer 3.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _calibre_has_kfx_plugin(calibre_config_dir: Path) -> bool:
    """Sprawdza czy wtyczka KFX Output jest zainstalowana w Calibre."""
    plugins_dir = calibre_config_dir / "plugins"
    if not plugins_dir.exists():
        return False
    
    # Wtyczka KFX Output ma nazwę zawierającą "KFX_Output" lub "KFX Output"
    for f in plugins_dir.iterdir():
        if "kfx_output" in f.name.lower() or "kfx output" in f.name.lower():
            return True
    return False
```

**Zmiany do wprowadzenia:**
- Każde `_find_*` → metoda statyczna klasy `Tools`
- Zwracaj `Tool` dataclass z bogatszą informacją (poniżej)
- Mockowanie w testach: `monkeypatch.setattr("shutil.which", lambda x: "/fake/path")`

### Zalecany model danych `Tool` (bogatszy niż w ROADMAP)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

@dataclass(frozen=True)
class Tool:
    """Informacja o wykrytym (lub nie) narzędziu zewnętrznym."""
    name: str                       # np. "Pandoc"
    executable: str                 # np. "pandoc"
    path: Path | None = None        # ścieżka jeśli znaleziono
    version: str = ""               # wersja jeśli udało się odczytać
    available: bool = False         # czy gotowe do użycia
    source: Literal[
        "path",          # znalezione w PATH
        "default_path",  # znalezione w typowej lokalizacji
        "config",        # ścieżka z config.json (ręczny override)
        "not_found"      # nie znaleziono
    ] = "not_found"
    error: str = ""                 # komunikat dlaczego niedostępne
```

**Korzyść:** GUI może pokazać użytkownikowi nie tylko „brak", ale też „czemu brak"
(np. „Pandoc: znaleziono w PATH, wersja 3.1.3" albo „Calibre: nie znaleziono w typowych
lokalizacjach — zainstaluj z calibre-ebook.com"). To znacząco poprawia UX przy
diagnozowaniu problemów z konfiguracją.

---

## 🖼️ Etap 8 — `gui/widgets/path_entry.py`

### Skopiuj ze starego `gui_main.py`:

```python
import tkinter as tk
from tkinter import filedialog


class PathEntry(tk.Frame):
    """Pole tekstowe z przyciskiem '…' do wyboru pliku/folderu."""
    
    def __init__(self, parent, mode: str = "dir", filetypes=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.mode = mode  # "dir", "file", "save"
        self.filetypes = filetypes or [("Wszystkie", "*.*")]
        self.var = tk.StringVar()
        
        self.entry = tk.Entry(self, textvariable=self.var)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        
        tk.Button(
            self, text="…",
            command=self._browse,
            cursor="hand2",
            padx=8
        ).pack(side="right", padx=(4, 0))
    
    def _browse(self) -> None:
        if self.mode == "dir":
            path = filedialog.askdirectory()
        elif self.mode == "file":
            path = filedialog.askopenfilename(filetypes=self.filetypes)
        else:  # save
            path = filedialog.asksaveasfilename(filetypes=self.filetypes)
        if path:
            self.var.set(path)
    
    def get(self) -> str:
        return self.var.get().strip()
    
    def set(self, value: str) -> None:
        self.var.set(value)
```

**Zmiany do wprowadzenia:**
- Pełne typowanie (parent: tk.Widget, etc.)
- Konfiguracja kolorów z modułu theme.py (NIE hardcoded)
- Callback `on_change` dla reactive UI

---

## 📋 Etap 8 — `gui/widgets/file_list.py`

### Skopiuj ze starego `gui_main.py`:

```python
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False


class FileList(tk.Frame):
    """Lista plików z toolbar (Dodaj/Usuń/Wyczyść) i opcjonalnym D&D."""
    
    EXTENSIONS = {".epub", ".txt", ".md", ".docx", ".html", ".pdf"}  # konfigurowane
    
    def __init__(self, parent, extensions=None, on_change=None, **kw):
        super().__init__(parent, **kw)
        self.extensions = extensions or self.EXTENSIONS
        self.on_change = on_change
        self._files = []
        
        # Toolbar
        toolbar = tk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 4))
        
        tk.Button(toolbar, text="+ Dodaj pliki", command=self._add).pack(side="left")
        tk.Button(toolbar, text="+ Folder", command=self._add_folder).pack(side="left", padx=4)
        tk.Button(toolbar, text="✕ Usuń", command=self._remove).pack(side="left")
        tk.Button(toolbar, text="⊘ Wyczyść", command=self._clear).pack(side="left", padx=4)
        
        self.count_lbl = tk.Label(toolbar, text="0 plików")
        self.count_lbl.pack(side="right")
        
        # Listbox z scrollbarem
        frm = tk.Frame(self)
        frm.pack(fill="both", expand=True)
        
        self.lb = tk.Listbox(frm, selectmode="extended")
        sb = ttk.Scrollbar(frm, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lb.pack(fill="both", expand=True)
        
        # Drag & Drop (opcjonalne)
        if HAS_DND:
            self.lb.drop_target_register(DND_FILES)
            self.lb.dnd_bind("<<Drop>>", self._on_drop)
    
    def _add(self):
        ft = [("Obsługiwane", " ".join(f"*{e}" for e in self.extensions))]
        for p in filedialog.askopenfilenames(filetypes=ft):
            if p not in self._files:
                self._files.append(p)
        self._refresh()
    
    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            for p in Path(d).iterdir():
                if p.suffix.lower() in self.extensions and str(p) not in self._files:
                    self._files.append(str(p))
            self._refresh()
    
    def _remove(self):
        for i in reversed(self.lb.curselection()):
            self._files.pop(i)
        self._refresh()
    
    def _clear(self):
        self._files.clear()
        self._refresh()
    
    def _on_drop(self, event):
        """Obsługa drop'a — tkinterdnd2 zwraca paths jako string z {} dla spacji."""
        files = self.tk.splitlist(event.data)
        for f in files:
            f = f.strip("{}")
            if Path(f).suffix.lower() in self.extensions and f not in self._files:
                self._files.append(f)
        self._refresh()
    
    def _refresh(self):
        self.lb.delete(0, "end")
        for p in self._files:
            self.lb.insert("end", f"{Path(p).name}  ({Path(p).parent})")
        n = len(self._files)
        suffix = "plik" if n == 1 else "pliki" if 2 <= n <= 4 else "plików"
        self.count_lbl.configure(text=f"{n} {suffix}")
        if self.on_change:
            self.on_change()
    
    def files(self) -> list[str]:
        return list(self._files)
```

---

## 🎨 Etap 8 — `gui/theme.py`

### Skopiuj ze starego `gui_main.py`:

```python
"""Motywy jasny i ciemny dla GUI."""

DARK = {
    "bg":     "#1e2028",
    "bg2":    "#252830",
    "bg3":    "#2d3040",
    "fg":     "#dde1ec",
    "fg2":    "#8b90a7",
    "fg3":    "#555a70",
    "accent": "#5DCAA5",
    "accent2": "#1D9E75",
    "border": "#383c50",
    "red":    "#e25454",
    "amber":  "#EF9F27",
}

LIGHT = {
    "bg":     "#ffffff",
    "bg2":    "#f5f5f7",
    "bg3":    "#e8e8ed",
    "fg":     "#1d1d1f",
    "fg2":    "#515154",
    "fg3":    "#86868b",
    "accent": "#1D9E75",
    "accent2": "#0F7C5B",
    "border": "#d1d1d6",
    "red":    "#d70015",
    "amber":  "#b25000",
}


def apply_theme(widget, theme: dict) -> None:
    """Aplikuj motyw rekurencyjnie na widget i jego dzieci."""
    cls = widget.winfo_class()
    
    try:
        if cls in ("Frame", "Tk", "Toplevel", "Labelframe"):
            widget.configure(bg=theme["bg2"])
        elif cls == "Label":
            widget.configure(bg=theme["bg2"], fg=theme["fg"])
        elif cls == "Button":
            widget.configure(bg=theme["bg3"], fg=theme["fg"])
        elif cls == "Entry":
            widget.configure(bg=theme["bg3"], fg=theme["fg"], insertbackground=theme["accent"])
        elif cls == "Listbox":
            widget.configure(
                bg=theme["bg3"], fg=theme["fg"],
                selectbackground=theme["accent2"], selectforeground=theme["bg"]
            )
        elif cls == "Text":
            widget.configure(bg=theme["bg3"], fg=theme["fg"], insertbackground=theme["accent"])
        elif cls == "Checkbutton" or cls == "Radiobutton":
            widget.configure(
                bg=theme["bg2"], fg=theme["fg"],
                activebackground=theme["bg2"], selectcolor=theme["accent2"]
            )
    except tk.TclError:
        pass  # Niektóre widgety nie wspierają wszystkich opcji
    
    # Rekursja na dzieci
    for child in widget.winfo_children():
        apply_theme(child, theme)
```

---

## 🌊 Etap 8 — `gui/streaming.py`

### Skopiuj ze starego `gui_main.py`:

```python
"""Thread-safe streamer dla wyjścia subprocess do widgetu tk.Text."""

import queue
import threading
import tkinter as tk


class LogStreamer:
    """Strumień logów do widgetu Text z bezpiecznymi wątkami."""
    
    def __init__(self, text_widget: tk.Text):
        self.text = text_widget
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        
        # Tagi kolorystyczne (kolory ustawione przez parent)
        self.text.tag_config("ok",    foreground="#5DCAA5")
        self.text.tag_config("err",   foreground="#e25454")
        self.text.tag_config("warn",  foreground="#EF9F27")
        self.text.tag_config("info",  foreground="#8b90a7")
        self.text.tag_config("cmd",   foreground="#555a70")
    
    def start_polling(self) -> None:
        """Uruchom polling kolejki (z main loop tkinter)."""
        self._running = True
        self._poll()
    
    def stop(self) -> None:
        self._running = False
    
    def write(self, text: str, tag: str = "") -> None:
        """Dodaj tekst do kolejki (thread-safe)."""
        self._queue.put((text, tag))
    
    def _poll(self) -> None:
        """Wewnętrzny polling — wywoływany z main loop."""
        if not self._running:
            return
        try:
            while True:
                text, tag = self._queue.get_nowait()
                self.text.configure(state="normal")
                self.text.insert("end", text, tag)
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.text.after(50, self._poll)  # 20 FPS
    
    def stream_subprocess(self, cmd: list[str], **kwargs) -> int:
        """Uruchom subprocess i streamuj jego stdout/stderr."""
        import subprocess
        import sys
        
        flags = 0x08000000 if sys.platform == "win32" else 0
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
            **kwargs
        )
        
        for line in proc.stdout:
            # Heurystyka tagów na podstawie zawartości
            line_lower = line.lower()
            if any(w in line_lower for w in ["error", "błąd", "traceback"]):
                tag = "err"
            elif any(w in line_lower for w in ["warning", "warn"]):
                tag = "warn"
            elif any(w in line_lower for w in ["ok", "done", "success"]):
                tag = "ok"
            else:
                tag = ""
            self.write(line, tag)
        
        proc.wait()
        return proc.returncode
```

---

## 🏗️ Etap 13 — `build/epubforge.spec`

### Adaptuj ze starego `epubtools_suite.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['../src/epubforge/gui/app.py'],
    pathex=['../src'],
    binaries=[],
    datas=[
        # Dołącz zasoby GUI jeśli będą (ikony itp.)
        # ('../src/epubforge/gui/assets/*', 'assets'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'lxml',
        'lxml.etree',
        'pyphen',
        'cssutils',
        'tkinterdnd2',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy',
        'PIL.tests', 'unittest', 'test',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='epubforge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app — NIE chcemy okna konsoli
    icon='icon.ico',  # wygenerowane przez create_icon.py
    version_file=None,
)
```

### `build/build.bat`:

```bat
@echo off
REM Lokalny build epubforge.exe dla Windows
REM Wymaga: pip install -e ".[build]"

echo Building EpubForge...
cd /d "%~dp0"

REM Czyść poprzednie buildy
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM Generuj ikonę jeśli nie istnieje
if not exist icon.ico (
    echo Generuję icon.ico...
    python create_icon.py
)

REM PyInstaller
python -m PyInstaller epubforge.spec --clean

if exist dist\epubforge.exe (
    echo.
    echo [SUKCES] dist\epubforge.exe utworzony pomyślnie!
    dir dist\epubforge.exe
) else (
    echo [BŁĄD] Build nie powiódł się
    exit /b 1
)
```

### `build/create_icon.py`:

```python
"""Generator ikony aplikacji icon.ico."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


def create_icon(output: Path = Path(__file__).parent / "icon.ico") -> None:
    """Wygeneruj ikonę 256x256 i zapisz jako .ico (multi-size)."""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Tło: gradient ciemnozielony
        for y in range(size):
            color_val = int(29 + (158 - 29) * (y / size))
            draw.line([(0, y), (size, y)], fill=(29, color_val, 117, 255))
        
        # Litera "ε" (epsilon) na środku
        try:
            font_size = int(size * 0.7)
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        
        text = "ε"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) // 2 - bbox[0]
        y = (size - text_h) // 2 - bbox[1]
        draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
        
        images.append(img)
    
    # Zapisz jako ICO z wieloma rozmiarami
    images[0].save(
        output,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"✓ Utworzono {output}")


if __name__ == "__main__":
    create_icon()
```

---

## ⚙️ Etap 13 — `.github/workflows/build.yml`

```yaml
name: Build Release

on:
  push:
    tags: ['v*']
  workflow_dispatch:

jobs:
  build-windows:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Python 3.12
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[build,gui]"
    
    - name: Generate icon
      run: python build/create_icon.py
    
    - name: Build with PyInstaller
      run: |
        cd build
        python -m PyInstaller epubforge.spec --clean
    
    - name: Upload artifact
      uses: actions/upload-artifact@v4
      with:
        name: epubforge-windows
        path: build/dist/epubforge.exe
        retention-days: 30
    
    - name: Create Release (only on tags)
      if: startsWith(github.ref, 'refs/tags/v')
      uses: softprops/action-gh-release@v2
      with:
        files: build/dist/epubforge.exe
        generate_release_notes: true
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## 🎯 Etap 9 — Tooltip widget

### `gui/widgets/tooltip.py`:

```python
import tkinter as tk


class Tooltip:
    """Tooltip dla widgetów tkinter."""
    
    def __init__(self, widget, text: str, delay_ms: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self.tip_window = None
        self.after_id = None
        
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)
    
    def _on_enter(self, event=None) -> None:
        self.after_id = self.widget.after(self.delay, self._show)
    
    def _on_leave(self, event=None) -> None:
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        self._hide()
    
    def _show(self) -> None:
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            tw, text=self.text,
            justify="left",
            bg="#2d3040", fg="#dde1ec",
            relief="solid", borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=8, pady=4
        )
        label.pack()
    
    def _hide(self) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
```

---

## 📝 Notatki ogólne

### Co przekształcić z starego kodu:
1. **Funkcje globalne `_find_*`** → metody static klasy `Tools`
2. **Globalne stałe kolorów** → moduł `theme.py`
3. **Procedury budowania komend subprocess** → funkcje w `converters/` i `fixers/`
4. **Walidacja UI** → logika w `core/`, UI tylko wyświetla błędy
5. **Stary `_save_config`/`_load_config`** → klasa `Config`

### Czego NIE kopiować:
- ❌ Inline'owe HTML/CSS w kodzie Python (separate files)
- ❌ Hardcoded ścieżki (use `pathlib` + detection)
- ❌ Magic numbers (np. `0x08000000`) — definiuj jako `CREATE_NO_WINDOW`
- ❌ `print()` calls (use `logging`)
- ❌ Funkcje > 50 linii (rozbij)

### Pattern do testowania subprocess:

```python
# stary kod:
result = subprocess.run(["pandoc", source, "-o", target])

# nowy, testowalny:
def _run_pandoc(args: list[str], runner=subprocess.run) -> CompletedProcess:
    return runner(args, capture_output=True, text=True)

# test:
def test_pandoc_command(mocker):
    mock_run = mocker.Mock(return_value=Mock(returncode=0, stdout="ok", stderr=""))
    result = _run_pandoc(["pandoc", "in.txt", "-o", "out.epub"], runner=mock_run)
    mock_run.assert_called_once_with(
        ["pandoc", "in.txt", "-o", "out.epub"],
        capture_output=True, text=True
    )
```
