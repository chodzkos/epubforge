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


_TOC_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:epubforge-toc-0001</dc:identifier>
    <dc:title>Książka ze spisem</dc:title>
    <dc:language>pl</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch3" href="text/ch3.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
    <itemref idref="ch3"/>
  </spine>
</package>
"""

# ch1: h1 + dwa h2 (jeden z <em> w środku), nagłówki bez id.
_TOC_CH1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Rozdział pierwszy</title></head>
  <body>
    <h1>Rozdział pierwszy</h1>
    <p>Zażółć gęślą jaźń.</p>
    <h2>Wstęp do tematu</h2>
    <p>Treść.</p>
    <h2>Rozdział <em>drugi</em> akt</h2>
    <p>Więcej treści.</p>
  </body>
</html>
"""

# ch2: h1 bez id + osierocony h3 (brak h2 pośredniego).
_TOC_CH2 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Rozdział drugi</title></head>
  <body>
    <h1>Rozdział drugi</h1>
    <h3>Podrozdział osierocony</h3>
    <p>Tekst.</p>
  </body>
</html>
"""

# ch3: brak nagłówków, ale jest <title>.
_TOC_CH3 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Bez nagłówków</title></head>
  <body><p>Sam akapit, żadnego nagłówka.</p></body>
</html>
"""

# Prosty nav z jednym MARTWYM wpisem (plik nie istnieje).
_TOC_NAV = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Spis treści</title></head>
  <body>
    <nav epub:type="toc">
      <ol>
        <li><a href="text/ch1.xhtml">Rozdział pierwszy</a></li>
        <li><a href="text/missing.xhtml">Martwy wpis</a></li>
      </ol>
    </nav>
  </body>
</html>
"""


# ── Wariant EPUB 2 (do testów upgrade → EPUB 3) ──────────────────────────────

# Pakiet 2.0: NCX + guide (cover/text) + dwie dc:date z opf:event.
_EPUB2_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">urn:uuid:c0ffee00-1234-4abc-8def-0123456789ab</dc:identifier>
    <dc:title>Książka EPUB 2</dc:title>
    <dc:creator>Jan Kowalski</dc:creator>
    <dc:language>pl</dc:language>
    <dc:date opf:event="publication">2019-03-15</dc:date>
    <dc:date opf:event="modification">2020-06-01</dc:date>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
  <guide>
    <reference type="cover" title="Okładka" href="cover.xhtml"/>
    <reference type="text" title="Początek" href="text/ch1.xhtml"/>
  </guide>
</package>
"""

_EPUB2_NCX = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:c0ffee00-1234-4abc-8def-0123456789ab"/>
    <meta name="dtb:depth" content="1"/>
  </head>
  <docTitle><text>Książka EPUB 2</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>Rozdział pierwszy</text></navLabel>
      <content src="text/ch1.xhtml"/>
    </navPoint>
    <navPoint id="np2" playOrder="2">
      <navLabel><text>Rozdział drugi</text></navLabel>
      <content src="text/ch2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

_EPUB2_COVER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Okładka</title></head>
  <body><h1>Okładka</h1></body>
</html>
"""

_EPUB2_CH1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Rozdział pierwszy</title></head>
  <body><h1>Rozdział pierwszy</h1><p>Zażółć gęślą jaźń.</p></body>
</html>
"""

_EPUB2_CH2 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Rozdział drugi</title></head>
  <body><h1>Rozdział drugi</h1><p>Drugi rozdział.</p></body>
</html>
"""


def make_epub2_epub(output: Path) -> Path:
    """Buduje EPUB 2 (version 2.0, NCX, guide) do testów upgrade → EPUB 3."""
    with zipfile.ZipFile(output, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", _EPUB2_OPF.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", _EPUB2_NCX.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/cover.xhtml", _EPUB2_COVER.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/ch1.xhtml", _EPUB2_CH1.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/ch2.xhtml", _EPUB2_CH2.encode(), zipfile.ZIP_DEFLATED)
    return output


def make_toc_epub(output: Path) -> Path:
    """Buduje EPUB do testów TOC (rozdziały z nagłówkami + nav z martwym wpisem)."""
    with zipfile.ZipFile(output, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", _TOC_OPF.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", _TOC_NAV.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/ch1.xhtml", _TOC_CH1.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/ch2.xhtml", _TOC_CH2.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/ch3.xhtml", _TOC_CH3.encode(), zipfile.ZIP_DEFLATED)
    return output


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
    epub2 = make_epub2_epub(Path(__file__).parent / "sample_epub2.epub")
    print(f"Utworzono fixture: {epub2}")
