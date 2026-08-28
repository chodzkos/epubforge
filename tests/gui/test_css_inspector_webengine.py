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

_AGGREGATE_SCRIPT = r"""
import json
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWidgets import QApplication

from epubforge.gui.css_inspector_limits import MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS
from epubforge.gui.preview.css_bridge import INSPECT_SCRIPT
from epubforge.gui.preview.preinit import preinit_webengine

assert preinit_webengine()
app = QApplication([])
page = QWebEnginePage()
result = {}

def instrumented_script(budget):
    script = INSPECT_SCRIPT.replace(
        f"const maxReportTextChars = {MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS}",
        f"const maxReportTextChars = {budget}",
    )
    marker = "  return result;\n})"
    replacement = (
        "  result.__budget_used = reportTextChars; "
        "result.__scanned_rules = scannedRules;\n  return result;\n})"
    )
    assert marker in script
    return script.replace(marker, replacement)

def run_report(budget, callback):
    script = f"JSON.stringify({instrumented_script(budget)}(null))"
    def finished(value):
        callback(json.loads(value), len(value))
    page.runJavaScript(script, QWebEngineScript.ScriptWorldId.ApplicationWorld, finished)

def fail(message):
    result["error"] = message
    finish()

def finish():
    print(json.dumps(result, ensure_ascii=False))
    page.deleteLater()
    app.quit()

def large_reported(report, payload_length):
    result["large"] = {
        "truncated": report.get("truncated"),
        "cascade_truncated": report.get("cascade_truncated"),
        "rules": len(report.get("rules", [])),
        "scanned_rules": report.get("__scanned_rules"),
        "payload_length": payload_length,
        "limitations": report.get("limitations", []),
    }
    finish()

def large_loaded(ok):
    if not ok:
        fail("large-load-failed")
        return
    page.loadFinished.disconnect(large_loaded)
    run_report(MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS, large_reported)

def below_reported(report, _payload_length):
    result["below"] = report
    value = "x" * 1000
    rules = "".join(
        f"@media screen {{ .target {{ --p{i}: {value}; }} }}" for i in range(1200)
    )
    page.loadFinished.connect(large_loaded)
    page.setHtml(
        f"<html><head><style>{rules}</style></head>"
        "<body><p class='target' data-epubforge-active-node=''>x</p></body></html>"
    )

def exact_reported(report, _payload_length):
    result["exact"] = report
    run_report(result["used"] - 1, below_reported)

def baseline_reported(report, _payload_length):
    result["used"] = report["__budget_used"]
    run_report(result["used"], exact_reported)

def small_loaded(ok):
    if not ok:
        fail("small-load-failed")
        return
    page.loadFinished.disconnect(small_loaded)
    run_report(MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS, baseline_reported)

small_rules = "".join(
    f"@media screen {{ .target {{ --small{i}: {'y' * 200}; }} }}" for i in range(12)
)
page.loadFinished.connect(small_loaded)
page.setHtml(
    f"<html><head><style>{small_rules}</style></head>"
    "<body><p class='target' data-epubforge-active-node=''>x</p></body></html>"
)
QTimer.singleShot(30000, lambda: fail("timeout"))
app.exec()

valid = (
    not result.get("error")
    and result.get("exact", {}).get("truncated") is False
    and result.get("below", {}).get("truncated") is True
    and result.get("below", {}).get("cascade_truncated") is True
    and result.get("large", {}).get("truncated") is True
    and result.get("large", {}).get("cascade_truncated") is True
    and result.get("large", {}).get("rules") == 0
    and result.get("large", {}).get("scanned_rules", 2400) < 2400
    and result.get("large", {}).get("payload_length", 10**9)
        <= MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS + 128 * 1024
    and any("budżet 1 MiB" in item for item in result.get("large", {}).get("limitations", []))
)
raise SystemExit(0 if valid else 9)
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


@pytest.mark.skipif(not probe_webengine().available, reason="Brak Qt WebEngine")
def test_aggregate_report_budget_is_enforced_before_json_stringify() -> None:
    """Collector akceptuje exact, odrzuca +1 i wcześnie kończy duży raport."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", _AGGREGATE_SCRIPT],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
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
