"""Generator minimalnego, poprawnego pliku ``sample.epub`` do testów.

Uruchom: ``python tests/fixtures/make_sample_epub.py``

Tworzy archiwum zgodne z OCF: ``mimetype`` pierwszy i nieskompresowany,
``META-INF/container.xml`` wskazujący na ``OEBPS/content.opf`` oraz jeden
rozdział XHTML. Plik jest commitowany do repo jako fixture — skrypt służy
do jego odtworzenia, gdyby trzeba było zmienić zawartość.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

OUTPUT = Path(__file__).parent / "sample.epub"

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CONTENT_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:epubforge-sample-0001</dc:identifier>
    <dc:title>Przykładowa książka</dc:title>
    <dc:creator>Jan Kowalski</dc:creator>
    <dc:language>pl</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""

NAV_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Spis treści</title></head>
  <body>
    <nav epub:type="toc"><ol><li><a href="text/chapter1.xhtml">Rozdział 1</a></li></ol></nav>
  </body>
</html>
"""

CHAPTER1_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Rozdział 1</title></head>
  <body><h1>Rozdział 1</h1><p>Zażółć gęślą jaźń. Tekst próbny.</p></body>
</html>
"""


def build(output: Path = OUTPUT) -> Path:
    """Buduje fixture EPUB pod wskazaną ścieżką i zwraca tę ścieżkę."""
    with zipfile.ZipFile(output, "w") as zf:
        # mimetype PIERWSZY i bez kompresji.
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", CONTENT_OPF.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", NAV_XHTML.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", CHAPTER1_XHTML.encode(), zipfile.ZIP_DEFLATED)
    return output


if __name__ == "__main__":
    path = build()
    print(f"Utworzono fixture: {path}")
