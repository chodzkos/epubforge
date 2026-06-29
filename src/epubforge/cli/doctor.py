"""Subkomenda CLI ``epubforge doctor`` — diagnostyka środowiska (detekcja na żywo).

Zarówno ``doctor`` (pełny raport rich), jak i ``info`` (krótkie podsumowanie) sondują
narzędzia ZAWSZE świeżo przez ``detect_with_cache(force=True)`` — z pominięciem cache,
żeby nie pokazywać zwietrzałego stanu (override'y ścieżek z configu są stosowane w środku).
"""

from __future__ import annotations

import argparse
import platform
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from epubforge import __version__
from epubforge.core import Tool, detect_with_cache
from epubforge.i18n import _

console = Console()

# Narzędzia istniejące wyłącznie pod Windows/macOS (Amazon/KP3). Pod Linuksem ich brak
# nie znaczy „zainstaluj" — analogia do linux_only w pdf2md, tylko odwrócona.
_PLATFORM_RESTRICTED = frozenset({"kindle_previewer", "kindlegen"})

# Kolejność i etykiety raportu — 9 narzędzi zwracanych przez Tools.detect_all().
_TOOL_LABELS: tuple[tuple[str, str], ...] = (
    ("pandoc", "Pandoc"),
    ("calibre_ebook_convert", "Calibre ebook-convert"),
    ("calibre_viewer", "Calibre ebook-viewer"),
    ("calibre_editor", "Calibre ebook-edit"),
    ("sigil", "Sigil"),
    ("kindle_previewer", "Kindle Previewer 3"),
    ("kindlegen", "KindleGen"),
    ("java", "Java"),
    ("epubcheck", "EpubCheck"),
)


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``doctor`` w głównym parserze argparse."""
    parser = subparsers.add_parser(
        "doctor", help=_("Diagnozuj środowisko — pełny raport wykrytych narzędzi (na żywo)")
    )
    parser.set_defaults(func=run)


def _restricted_here(name: str) -> bool:
    """Czy narzędzie jest ograniczone do Windows/macOS, a działamy na innej platformie."""
    if name not in _PLATFORM_RESTRICTED:
        return False
    return sys.platform != "win32" and platform.system() != "Darwin"


def _status(tool: Tool, name: str) -> str:
    """Etykieta statusu: dostępne (z wersją), nota o platformie albo brak."""
    if tool.available:
        return "✅ " + (tool.version or _("dostępny"))
    if _restricted_here(name):
        return _("ℹ️ niedostępne na tej platformie (Windows/macOS)")  # noqa: RUF001
    return "❌ " + _("brak")


def run(args: argparse.Namespace) -> int:
    """Pełny raport diagnostyczny — detekcja ZAWSZE na żywo (force=True, bez cache)."""
    tools = detect_with_cache(force=True)

    console.print(Panel.fit(f"EpubForge {__version__} — doctor", style="bold cyan"))

    system_table = Table(title=_("System"))
    system_table.add_column(_("Element"))
    system_table.add_column(_("Wartość"))
    system_table.add_row("OS", platform.system())
    system_table.add_row("Python", platform.python_version())
    console.print(system_table)

    tools_table = Table(title=_("Narzędzia"))
    tools_table.add_column(_("Narzędzie"))
    tools_table.add_column(_("Status"))
    tools_table.add_column(_("Ścieżka"))
    for name, label in _TOOL_LABELS:
        tool = tools.get(name)
        if tool is None:
            continue
        path = str(tool.path) if tool.path is not None else "—"
        tools_table.add_row(label, _status(tool, name), path)
    console.print(tools_table)
    return 0


def run_info() -> int:
    """Krótki wariant komendy ``info`` — wersja + lista dostępnych narzędzi (na żywo)."""
    tools = detect_with_cache(force=True)
    print(f"EpubForge {__version__}")
    available = [label for name, label in _TOOL_LABELS if _is_available(tools.get(name))]
    if available:
        print(_("Dostępne narzędzia: ") + ", ".join(available))
    else:
        print(_("Nie wykryto żadnych narzędzi."))
    return 0


def _is_available(tool: Tool | None) -> bool:
    """Czy narzędzie zostało wykryte (bezpieczne na brak klucza w mapie)."""
    return tool is not None and tool.available
