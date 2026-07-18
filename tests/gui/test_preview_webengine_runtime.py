"""Test runtime izolacji WebEngine: sieć, pliki lokalne i skrypty publikacji."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from epubforge.gui.preview.availability import probe_webengine

pytestmark = [pytest.mark.gui, pytest.mark.security]

_RUNTIME_SCRIPT = r"""
import json
import sys
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QTimer
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineUrlScheme
from PySide6.QtWidgets import QApplication

from epubforge.core import Epub
from epubforge.gui.preview.backend import PreviewSnapshot
from epubforge.gui.preview.preinit import preinit_webengine

assert preinit_webengine(), "schemat WebEngine nie został zarejestrowany"
scheme = QWebEngineUrlScheme.schemeByName(b"epub-preview")
assert scheme.flags() == QWebEngineUrlScheme.Flag.SecureScheme, scheme.flags()

from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.webengine_backend import WebEnginePreviewBackend

app = QApplication([])
epub_path = Path(sys.argv[1])
epub = Epub(epub_path)
epub.open()
internal = "OEBPS/text/chapter1.xhtml"
source = epub.read_file(internal).decode("utf-8")
session = PreviewSession.create(epub, epub_path)
backend = WebEnginePreviewBackend()
backend.set_session(session)
result = {"finished": False}


def checked(value):
    result["payload"] = json.loads(value)
    result["finished"] = True
    app.quit()


def loaded(ok):
    if not ok:
        result["error"] = "load-failed"
        app.quit()
        return
    backend._page.runJavaScript(
        "JSON.stringify({"
        "active:document.querySelectorAll('script,iframe,form,object,embed').length,"
        "onload:document.body.hasAttribute('onload'),"
        "marker:document.body.dataset.executed||'',"
        "text:document.body.innerText,"
        "localWidth:document.querySelector('#local').naturalWidth,"
        "origin:location.origin"
        "})",
        QWebEngineScript.ScriptWorldId.ApplicationWorld,
        checked,
    )


backend._page.loadFinished.connect(loaded)
backend.render_snapshot(PreviewSnapshot(source, epub, internal, 1))
QTimer.singleShot(15000, lambda: (result.setdefault("error", "timeout"), app.quit()))
app.exec()
payload = result.get("payload", {})
print(json.dumps(result, ensure_ascii=False))
backend.dispose()
session.close()
epub.close()
valid = (
    result.get("finished")
    and payload.get("active") == 0
    and payload.get("onload") is False
    and payload.get("marker") == ""
    and payload.get("localWidth") == 0
    and sys.argv[2] not in payload.get("text", "")
    and payload.get("origin", "").startswith("epub-preview://")
    and backend._page.createWindow(backend._page.WebWindowType.WebBrowserTab) is None
)
raise SystemExit(0 if valid else 4)
"""


class _TrapHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        """Rejestruje każde niepożądane żądanie do lokalnej pułapki."""
        type(self).requests.append(self.path)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Wycisza standardowe logowanie serwera testowego."""
        return None


@pytest.mark.skipif(not probe_webengine().available, reason="Brak Qt WebEngine")
def test_runtime_blocks_network_file_and_book_scripts(sample_epub: Path, tmp_path: Path) -> None:
    """Złośliwy XHTML nie czyta file:, nie wysyła HTTP i nie wykonuje JS/onload."""
    _TrapHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TrapHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    secret = "PREVIEW-LOCAL-SECRET-7f52f22d"
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><text>'
        + secret
        + "</text></svg>",
        encoding="utf-8",
    )
    chapter = _malicious_chapter(server.server_port, secret_path)
    epub_path = tmp_path / "hostile.epub"
    _replace_chapter(sample_epub, epub_path, chapter)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _RUNTIME_SCRIPT, str(epub_path), secret],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _TrapHandler.requests == []


def _malicious_chapter(port: int, secret_path: Path) -> bytes:
    """Buduje dokument próbujący użyć wszystkich blokowanych kanałów."""
    file_url = secret_path.resolve().as_uri()
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml"><head><title>Atak</title></head>
    <body onload="document.body.dataset.executed='onload'">
      <script>document.body.dataset.executed='script'</script>
      <iframe src="{file_url}"></iframe>
      <form action="http://127.0.0.1:{port}/form"><input/></form>
      <img src="http://127.0.0.1:{port}/trap.png" alt="pułapka"/>
      <img id="local" src="{file_url}" alt="lokalny sekret"/>
      <p>Bezpieczna treść</p>
    </body></html>""".encode()


def _replace_chapter(source: Path, target: Path, chapter: bytes) -> None:
    """Kopiuje fixture EPUB, podmieniając jeden rozdział bez duplikowania wpisu."""
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, "w") as outgoing:
        for info in incoming.infolist():
            data = chapter if info.filename == "OEBPS/text/chapter1.xhtml" else incoming.read(info)
            outgoing.writestr(info, data)
