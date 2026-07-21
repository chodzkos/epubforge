"""Integracyjny test kaskady i live edit na rzeczywistym Qt WebEngine."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from epubforge.gui.preview.availability import probe_webengine

pytestmark = [pytest.mark.gui, pytest.mark.webengine]

_SCRIPT = r"""
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
epub = Epub(Path(sys.argv[1])); epub.open()
document = "OEBPS/ch.xhtml"
source = epub.read_file(document).decode("utf-8")
session = PreviewSession.create(epub)
generation = session.advance(epub, document, {document: source})
node_id = next(node.node_id for node in generation.source_map.values() if node.element_id == "target")
backend = WebEnginePreviewBackend(); backend.set_session(session)
result = {}

def fail(message):
    result["error"] = message; finish()

def finish():
    print(json.dumps(result, ensure_ascii=False))
    backend.dispose(); session.close(); epub.close(); app.quit()

def preview_value(value):
    result["preview_margin"] = value
    result["source_unchanged"] = "margin-left: 9px" not in epub.read_file("OEBPS/book.css").decode("utf-8")
    finish()

def previewed(value):
    backend.css_preview_result.disconnect(previewed)
    result["preview"] = value
    backend._page.runJavaScript(
        "getComputedStyle(document.querySelector('#target')).marginLeft",
        QWebEngineScript.ScriptWorldId.ApplicationWorld,
        preview_value,
    )

def inspected(report):
    backend.element_inspected.disconnect(inspected)
    result["report"] = report
    backend.css_preview_result.connect(previewed)
    backend.preview_css_rule("body p.note", "body p.note { margin-left: 9px }", current_element=False)

def loaded(ok):
    if not ok: fail("load-failed"); return
    backend.element_inspected.connect(inspected)
    backend.inspect_element(node_id)

backend._page.loadFinished.connect(loaded)
backend.render_snapshot(PreviewSnapshot(source, epub, document, 1, generation))
QTimer.singleShot(15000, lambda: fail("timeout"))
app.exec()

report = result.get("report", {})
rules = report.get("rules", [])
decls = [(r.get("selector"), d) for r in rules for d in r.get("declarations", [])]
def state(selector, prop):
    return next((d.get("state") for s, d in decls if s == selector and d.get("property") == prop), None)
valid = (
    not result.get("error")
    and state("element.style", "color") == "winning"
    and state("#target", "color") == "lost"
    and state("p", "background-color") == "winning"
    and state("#target", "background-color") == "lost"
    and state("body p.note", "margin-left") == "winning"
    and any(not r.get("active") and r.get("selector") == "#target" for r in rules)
    and result.get("preview", {}).get("matches") == 1
    and result.get("preview_margin") == "9px"
    and result.get("source_unchanged") is True
)
raise SystemExit(0 if valid else 8)
"""


@pytest.mark.skipif(not probe_webengine().available, reason="Brak Qt WebEngine")
def test_real_cascade_and_live_edit_without_source_write(tmp_path: Path) -> None:
    """Chromium rozstrzyga v1, a preview zmienia element bez zapisu arkusza."""
    epub_path = _make_epub(tmp_path / "cascade.epub")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(epub_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _make_epub(path: Path) -> Path:
    """Buduje minimalny EPUB z konfliktami specyficzności, inline i @media."""
    container = b"""<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata><manifest><item id="h" href="ch.xhtml" media-type="application/xhtml+xml"/><item id="c" href="book.css" media-type="text/css"/></manifest><spine><itemref idref="h"/></spine></package>"""
    xhtml = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head><link rel="stylesheet" href="book.css"/></head><body><p id="target" class="note" style="color: green">Tekst</p></body></html>"""
    css = b"""p { color: red; background-color: white !important; margin-left: 1px }
#target { color: blue; background-color: black }
body p.note { margin-left: 3px }
@media print { #target { font-size: 99px } }
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/ch.xhtml", xhtml)
        archive.writestr("OEBPS/book.css", css)
    return path
