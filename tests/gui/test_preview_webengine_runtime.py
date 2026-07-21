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

pytestmark = [pytest.mark.gui, pytest.mark.security, pytest.mark.webengine]

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
generation = session.advance(epub, internal, {internal: source})
backend.render_snapshot(PreviewSnapshot(source, epub, internal, 1, generation))
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
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
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


_RESOURCE_RUNTIME_SCRIPT = r"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWidgets import QApplication

from epubforge.core import Epub
from epubforge.gui.preview.backend import PreviewSnapshot
from epubforge.gui.preview.preinit import preinit_webengine

assert preinit_webengine()
from epubforge.gui.preview.session import PreviewSession
from epubforge.gui.preview.webengine_backend import WebEnginePreviewBackend

app = QApplication([])
epub = Epub(Path(sys.argv[1]))
epub.open()
document = "OEBPS/text/ch.xhtml"
stylesheet = "OEBPS/styles/book.css"
source = epub.read_file(document).decode("utf-8")
session = PreviewSession.create(epub)
backend = WebEnginePreviewBackend()
backend.set_session(session)
first = session.advance(epub, document, {document: source})
loads = {"count": 0}
result = {}


def finish(value):
    result.update(json.loads(value))
    result["loads"] = loads["count"]
    print(json.dumps(result, ensure_ascii=False))
    backend.dispose()
    session.close()
    epub.close()
    app.quit()


def inspect():
    backend._page.runJavaScript(
        "JSON.stringify({"
        "color:getComputedStyle(document.querySelector('#target')).color,"
        "family:getComputedStyle(document.querySelector('#glyph')).fontFamily,"
        "fontLoaded:document.fonts.check('16px PreviewGlyph'),"
        "imageWidth:document.querySelector('#cover').naturalWidth,"
        "background:getComputedStyle(document.body).backgroundImage,"
        "scroll:window.scrollY,"
        "selected:String(window.getSelection())"
        "})",
        QWebEngineScript.ScriptWorldId.ApplicationWorld,
        finish,
    )


def apply_css(_value):
    css = (
        "@font-face{font-family:PreviewGlyph;src:url('../fonts/preview.woff2') format('woff2')}"
        "body{background-image:url('../images/bg.png')}"
        "#target{color:rgb(7, 8, 9)}"
        "#glyph{font-family:PreviewGlyph}"
    )
    second = session.advance(
        epub,
        document,
        {document: source, stylesheet: css},
        {"OEBPS/fonts/preview.woff2": "font/woff2"},
    )
    backend.render_snapshot(
        PreviewSnapshot(source, epub, document, 2, second, stylesheet, True)
    )
    backend.set_theme(backend._palette)
    QTimer.singleShot(1800, inspect)


def prepare(_value):
    backend._page.runJavaScript(
        "window.scrollTo(0, document.documentElement.scrollHeight);"
        "const r=document.createRange();"
        "r.selectNodeContents(document.querySelector('#target'));"
        "const s=window.getSelection();s.removeAllRanges();s.addRange(r);true",
        QWebEngineScript.ScriptWorldId.ApplicationWorld,
        apply_css,
    )


def loaded(ok):
    loads["count"] += 1
    if not ok:
        result["error"] = "load-failed"
        app.quit()
        return
    QTimer.singleShot(300, lambda: backend._page.runJavaScript(
        "document.fonts.ready.then(() => true)",
        QWebEngineScript.ScriptWorldId.ApplicationWorld,
        prepare,
    ))


backend._page.loadFinished.connect(loaded)
backend.render_snapshot(PreviewSnapshot(source, epub, document, 1, first))
QTimer.singleShot(15000, lambda: (result.setdefault("error", "timeout"), app.quit()))
app.exec()
valid = (
    result.get("color") == "rgb(7, 8, 9)"
    and "PreviewGlyph" in result.get("family", "")
    and result.get("fontLoaded") is True
    and result.get("imageWidth", 0) > 0
    and "epub-preview://" in result.get("background", "")
    and result.get("scroll", 0) > 0
    and result.get("selected") == "Zaznaczony tekst"
    and result.get("loads") == 1
)
raise SystemExit(0 if valid else 5)
"""


@pytest.mark.skipif(not probe_webengine().available, reason="Brak Qt WebEngine")
def test_runtime_renders_resources_and_updates_css_without_reload(tmp_path: Path) -> None:
    """WebEngine używa CSS, WOFF2 i obrazów; niezapisany CSS nie przeładowuje DOM."""
    epub_path = _make_resource_runtime_epub(tmp_path / "resources.epub")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _RESOURCE_RUNTIME_SCRIPT, str(epub_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _make_resource_runtime_epub(path: Path) -> Path:
    """Buduje fixture z rzeczywistym WOFF2 i poprawnymi obrazami PNG."""
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    font = (fixture_dir / "preview-glyphicons.woff2").read_bytes()
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f9b0000000049454e44ae426082"
    )
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head>
      <link rel="stylesheet" href="../styles/book.css"/></head><body>
      <img id="cover" src="../images/cover.png"/>
      <p id="glyph">&#xe003;</p>
      <div style="height:1800px"></div><p id="target">Zaznaczony tekst</p>
    </body></html>"""
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
      unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:identifier id="id">runtime</dc:identifier><dc:title>Runtime</dc:title>
      <dc:language>pl</dc:language></metadata><manifest>
      <item id="ch" href="text/ch.xhtml" media-type="application/xhtml+xml"/>
      <item id="css" href="styles/book.css" media-type="text/css"/>
      <item id="font" href="fonts/preview.woff2" media-type="font/woff2"/>
      <item id="cover" href="images/cover.png" media-type="image/png"/>
      <item id="bg" href="images/bg.png" media-type="image/png"/>
      </manifest><spine><itemref idref="ch"/></spine></package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/text/ch.xhtml", chapter)
        archive.writestr(
            "OEBPS/styles/book.css",
            "@font-face{font-family:PreviewGlyph;"
            "src:url('../fonts/preview.woff2') format('woff2')}"
            "#glyph{font-family:PreviewGlyph}",
        )
        archive.writestr("OEBPS/fonts/preview.woff2", font)
        archive.writestr("OEBPS/images/cover.png", png)
        archive.writestr("OEBPS/images/bg.png", png)
    return path
