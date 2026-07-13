"""Kontrola zgodności tagu wydania ``vX.Y.Z`` z ``epubforge.__version__`` (F-16).

Bramka przed release: tag Gita, z którego robimy wydanie, MUSI odpowiadać wersji
zadeklarowanej w kodzie. Rozjazd (np. tag ``v3.1.0`` przy ``__version__ = "3.0.0"``)
oznacza pomyłkę w procesie wydawniczym — przerywamy, zanim powstaną artefakty.

Wersję czytamy **statycznie** z ``src/epubforge/__init__.py`` (regex), bez importu
pakietu — helper nie wymaga zainstalowanych zależności i działa w minimalnym CI.

Użycie::

    python build/check_tag_version.py v3.0.0
    python build/check_tag_version.py "$GITHUB_REF_NAME"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_INIT_PATH = Path(__file__).resolve().parent.parent / "src" / "epubforge" / "__init__.py"
_VERSION_RE = re.compile(r'^__version__\s*=\s*["\'](?P<version>[^"\']+)["\']', re.MULTILINE)
# Akceptujemy wyłącznie tag postaci vX.Y.Z (opcjonalny sufiks prerelease/rc).
_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]+)?)$")


def read_declared_version(init_path: Path = _INIT_PATH) -> str:
    """Zwraca ``__version__`` odczytany statycznie z ``__init__.py`` pakietu.

    Raises:
        ValueError: gdy w pliku nie ma deklaracji ``__version__``.
    """
    match = _VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"Nie znaleziono __version__ w {init_path}")
    return match.group("version")


def tag_version(tag: str) -> str:
    """Wyłuskuje wersję z tagu ``vX.Y.Z``.

    Raises:
        ValueError: gdy tag nie ma postaci ``vX.Y.Z`` (z opcjonalnym prerelease).
    """
    match = _TAG_RE.match(tag.strip())
    if match is None:
        raise ValueError(f"Tag '{tag}' nie ma postaci vX.Y.Z")
    return match.group("version")


def check(tag: str, init_path: Path = _INIT_PATH) -> tuple[bool, str]:
    """Porównuje wersję z tagu z wersją zadeklarowaną w kodzie.

    Returns:
        Krotka ``(zgodne, komunikat)`` — ``zgodne`` True gdy wersje są identyczne.
    """
    try:
        declared = read_declared_version(init_path)
        from_tag = tag_version(tag)
    except ValueError as exc:
        return False, str(exc)
    if declared != from_tag:
        return False, (
            f"Rozjazd wersji: tag '{tag}' → {from_tag}, ale __version__ = {declared}. "
            f"Zaktualizuj wersję w kodzie albo popraw tag przed wydaniem."
        )
    return True, f"OK: tag {tag} zgodny z __version__ = {declared}"


def main(argv: list[str]) -> int:
    """CLI: ``check_tag_version.py <tag>`` — 0 gdy zgodne, 1 gdy rozjazd/błąd."""
    if len(argv) != 2:
        print("Użycie: check_tag_version.py <tag vX.Y.Z>", file=sys.stderr)
        return 2
    ok, message = check(argv[1])
    print(message, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
