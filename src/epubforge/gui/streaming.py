"""Thread-safe streamer logów do widgetu ``tk.Text``."""

from __future__ import annotations

import queue
import subprocess
import sys
import tkinter as tk

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class LogStreamer:
    """Strumień logów do widgetu ``Text`` z bezpieczną kolejką między wątkami."""

    def __init__(self, text_widget: tk.Text, poll_ms: int = 50) -> None:
        self.text = text_widget
        self.poll_ms = poll_ms
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running = False
        self.text.tag_config("ok", foreground="#5dcaa5")
        self.text.tag_config("err", foreground="#e25454")
        self.text.tag_config("warn", foreground="#ef9f27")
        self.text.tag_config("info", foreground="#8b90a7")
        self.text.tag_config("cmd", foreground="#555a70")

    def start_polling(self) -> None:
        """Uruchamia polling kolejki z pętli zdarzeń tkinter."""
        if self._running:
            return
        self._running = True
        self._poll()

    def stop(self) -> None:
        """Zatrzymuje polling kolejki."""
        self._running = False

    def write(self, text: str, tag: str = "") -> None:
        """Dodaje tekst do kolejki w sposób bezpieczny dla wątków."""
        self._queue.put((text, tag))

    def clear(self) -> None:
        """Czyści widget tekstowy."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def stream_subprocess(self, cmd: list[str], cwd: str | None = None) -> int:
        """Uruchamia subprocess i streamuje połączone stdout/stderr."""
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.stdout is not None:
            for line in proc.stdout:
                self.write(line, _tag_for_line(line))
        return proc.wait()

    def _poll(self) -> None:
        """Przenosi wpisy z kolejki do widgetu ``Text``."""
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
        self.text.after(self.poll_ms, self._poll)


def _tag_for_line(line: str) -> str:
    """Dobiera tag kolorystyczny do linii logu."""
    lower = line.lower()
    if "error" in lower or "błąd" in lower or "failed" in lower:
        return "err"
    if "warn" in lower or "warning" in lower:
        return "warn"
    if "ok" in lower or "success" in lower:
        return "ok"
    return "info"
