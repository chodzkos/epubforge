"""Biblioteka presetów CSS (F11) — wbudowane szablony + import własnych.

Preset to gotowy arkusz stylów dołączany do EPUB-a. API jest niezależne od GUI:

* :func:`list_presets` — wbudowane (z ``fixers/presets/``) + użytkownika
  (z ``config_dir()/presets``);
* :func:`get_preset` — pojedynczy preset po ``id``;
* :func:`apply_preset` — dopina arkusz do otwartego :class:`Epub`
  (``append`` = dodaj obok istniejących, ``replace`` = usuń istniejące arkusze
  i wstaw tylko nasz);
* :func:`import_user_preset` — kopiuje arkusz użytkownika do katalogu presetów
  po walidacji składni (tinycss2).

Mechanika ``append`` (idempotentna): arkusz ląduje w ``{opf_dir}/styles/
epubforge-preset.css``, dostaje ``<item>`` w manifeście OPF i ``<link>`` jako
OSTATNIE dziecko ``<head>`` w każdym pliku spine. Ścieżki są względne, ale o
RÓŻNYCH bazach: ``href`` manifestu liczymy względem katalogu OPF, a ``href``
linku względem katalogu danego pliku XHTML (``posixpath.relpath``).
"""

from __future__ import annotations

import json
import posixpath
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag

import tinycss2
from lxml import etree

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted_tree
from epubforge.core.config import config_dir
from epubforge.core.publication_href import read_publication_member, resolve_from_directory
from epubforge.i18n import current_language

# Stałe wstrzykiwanego arkusza i znaczniki w OPF/XHTML.
PRESET_CSS_REL = "styles/epubforge-preset.css"
PRESET_ITEM_ID = "efpreset-css"
_CSS_MEDIA_TYPE = "text/css"
_OPF_NS = "http://www.idpf.org/2007/opf"
_XHTML_NS = "http://www.w3.org/1999/xhtml"
_FALLBACK_LANGS = ("en", "pl")


class PresetError(ValueError):
    """Błąd biblioteki presetów (nieznany preset, niepoprawny import)."""


@dataclass(frozen=True)
class CssPreset:
    """Pojedynczy preset CSS.

    Attributes:
        id: identyfikator (np. ``reader-friendly`` lub nazwa pliku użytkownika).
        name: nazwa w wersjach językowych (``{"pl": ..., "en": ..., "de": ...}``).
        description: opis w wersjach językowych.
        path: ścieżka do pliku ``.css`` (wbudowanego albo użytkownika).
        builtin: czy to preset wbudowany.
    """

    id: str
    name: dict[str, str]
    description: dict[str, str]
    path: Path
    builtin: bool = True

    def display_name(self, language: str | None = None) -> str:
        """Zwraca nazwę w danym języku (fallback en → pl → id)."""
        return _pick_language(self.name, language) or self.id

    def display_description(self, language: str | None = None) -> str:
        """Zwraca opis w danym języku (fallback en → pl → pusty)."""
        return _pick_language(self.description, language)

    def read_css(self) -> str:
        """Wczytuje zawartość arkusza presetu."""
        return self.path.read_text(encoding="utf-8")


# ── Katalogi presetów ───────────────────────────────────────────────────────


def _builtin_dir() -> Path:
    """Katalog wbudowanych presetów (także w bundlu PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "fixers" / "presets"
    return Path(__file__).resolve().parent / "presets"


def user_presets_dir(user_dir: Path | None = None) -> Path:
    """Katalog presetów użytkownika (domyślnie ``config_dir()/presets``)."""
    return Path(user_dir) if user_dir is not None else config_dir() / "presets"


# ── Lista / pobranie ────────────────────────────────────────────────────────


def list_presets(user_dir: Path | None = None) -> list[CssPreset]:
    """Zwraca presety: wbudowane + użytkownika (te o tym samym ``id`` nadpisują)."""
    presets: dict[str, CssPreset] = {}
    for preset in _load_builtin_presets():
        presets[preset.id] = preset
    for preset in _load_user_presets(user_presets_dir(user_dir)):
        presets[preset.id] = preset
    return list(presets.values())


def get_preset(preset_id: str, user_dir: Path | None = None) -> CssPreset:
    """Zwraca preset po ``id`` albo rzuca :class:`PresetError`."""
    for preset in list_presets(user_dir):
        if preset.id == preset_id:
            return preset
    raise PresetError(f"Nieznany preset CSS: {preset_id}")


def import_user_preset(source: Path, user_dir: Path | None = None) -> CssPreset:
    """Waliduje i kopiuje arkusz użytkownika do katalogu presetów.

    Raises:
        PresetError: gdy pliku nie ma albo CSS jest pusty/sam błąd składni.
    """
    source = Path(source)
    if not source.is_file():
        raise PresetError(f"Plik presetu nie istnieje: {source}")
    text = source.read_text(encoding="utf-8", errors="replace")
    if not _is_valid_css(text):
        raise PresetError(f"Plik nie zawiera poprawnego CSS: {source}")

    target_dir = user_presets_dir(user_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}.css"
    shutil.copyfile(source, target)
    return _user_preset(target)


# ── Aplikacja presetu do EPUB ───────────────────────────────────────────────


def apply_preset(epub: Epub, preset: CssPreset, mode: str = "append") -> None:
    """Dopina preset do otwartego EPUB-a.

    Args:
        epub: otwarty :class:`Epub`.
        preset: preset do zastosowania.
        mode: ``append`` (dodaj obok istniejących) lub ``replace`` (usuń istniejące
            arkusze CSS i wstaw tylko nasz).
    """
    opf_dir = epub.opf_dir()
    css_internal = _css_internal_path(opf_dir)

    if mode == "replace":
        _remove_existing_stylesheets(epub, keep_internal=css_internal)

    # Zapis arkusza (ponowna aplikacja = podmiana zawartości — idempotencja).
    epub.write_file(css_internal, preset.read_css().encode("utf-8"))
    _ensure_manifest_item(epub, opf_dir, css_internal)

    href_by_id = {item.id: item for item in epub.manifest}
    for idref in epub.spine:
        item = href_by_id.get(idref)
        if item is None:
            continue
        xhtml_internal = _resolve_path(item.href, opf_dir)
        _ensure_link(epub, xhtml_internal, css_internal)


def _remove_existing_stylesheets(epub: Epub, keep_internal: str) -> None:
    """Usuwa wszystkie arkusze CSS (manifest + linki + pliki) poza naszym."""
    opf_dir = epub.opf_dir()
    spine_paths = _spine_paths(epub)

    tree = _parse_xml(epub.read_file(epub.opf_path))
    manifest_el = tree.getroot().find(f"{{{_OPF_NS}}}manifest")
    removed: set[str] = set()
    if manifest_el is not None:
        for item in list(manifest_el):
            href = item.get("href")
            media_type = item.get("media-type")
            if href is None:
                continue
            internal = _resolve_path(href, opf_dir)
            is_css = media_type == _CSS_MEDIA_TYPE or _suffix(href) == ".css"
            if is_css and item.get("id") != PRESET_ITEM_ID and internal != keep_internal:
                manifest_el.remove(item)
                removed.add(internal)

    if not removed:
        return
    epub.write_file(epub.opf_path, _serialize_xml(tree))
    for internal in removed:
        epub.delete_file(internal)
    for xhtml_internal in spine_paths:
        _remove_links(epub, xhtml_internal, removed)


def _ensure_manifest_item(epub: Epub, opf_dir: str, css_internal: str) -> None:
    """Dodaje ``<item>`` arkusza do manifestu OPF, jeśli go tam nie ma."""
    tree = _parse_xml(epub.read_file(epub.opf_path))
    manifest_el = tree.getroot().find(f"{{{_OPF_NS}}}manifest")
    if manifest_el is None:
        return
    for item in manifest_el:
        href = item.get("href")
        if item.get("id") == PRESET_ITEM_ID or (
            href is not None and _resolve_path(href, opf_dir) == css_internal
        ):
            return
    item = etree.SubElement(manifest_el, f"{{{_OPF_NS}}}item")
    item.set("id", PRESET_ITEM_ID)
    item.set("href", _relative_href(css_internal, opf_dir))
    item.set("media-type", _CSS_MEDIA_TYPE)
    epub.write_file(epub.opf_path, _serialize_xml(tree))


def _ensure_link(epub: Epub, xhtml_internal: str, css_internal: str) -> None:
    """Dodaje ``<link>`` do arkusza jako OSTATNIE dziecko ``<head>`` (idempotentnie)."""
    tree = _parse_xml(read_publication_member(epub, xhtml_internal))
    head, ns = _find_head(tree.getroot())
    if head is None:
        return
    xhtml_dir = posixpath.dirname(xhtml_internal)
    link_tag = f"{{{ns}}}link" if ns else "link"
    for link in head.findall(link_tag):
        href = link.get("href")
        if href is not None and _resolve_path(href, xhtml_dir) == css_internal:
            return
    link = etree.SubElement(head, link_tag)
    link.set("rel", "stylesheet")
    link.set("type", _CSS_MEDIA_TYPE)
    link.set("href", _relative_href(css_internal, xhtml_dir))
    epub.write_file(xhtml_internal, _serialize_xml(tree))


def _remove_links(epub: Epub, xhtml_internal: str, removed: set[str]) -> None:
    """Usuwa z ``<head>`` linki wskazujące na usunięte arkusze."""
    tree = _parse_xml(read_publication_member(epub, xhtml_internal))
    head, ns = _find_head(tree.getroot())
    if head is None:
        return
    xhtml_dir = posixpath.dirname(xhtml_internal)
    link_tag = f"{{{ns}}}link" if ns else "link"
    changed = False
    for link in head.findall(link_tag):
        href = link.get("href")
        if href is not None and _resolve_path(href, xhtml_dir) in removed:
            head.remove(link)
            changed = True
    if changed:
        epub.write_file(xhtml_internal, _serialize_xml(tree))


# ── Pomocnicze ──────────────────────────────────────────────────────────────


def _load_builtin_presets() -> list[CssPreset]:
    """Wczytuje wbudowane presety z ``presets.json``."""
    base = _builtin_dir()
    manifest = json.loads((base / "presets.json").read_text(encoding="utf-8"))
    presets: list[CssPreset] = []
    for entry in manifest:
        presets.append(
            CssPreset(
                id=str(entry["id"]),
                name=dict(entry.get("name", {})),
                description=dict(entry.get("description", {})),
                path=base / str(entry["file"]),
                builtin=True,
            )
        )
    return presets


def _load_user_presets(directory: Path) -> list[CssPreset]:
    """Wczytuje presety użytkownika (każdy ``*.css`` w katalogu)."""
    if not directory.is_dir():
        return []
    return [_user_preset(path) for path in sorted(directory.glob("*.css"))]


def _user_preset(path: Path) -> CssPreset:
    """Buduje :class:`CssPreset` z pliku użytkownika (nazwa = nazwa pliku)."""
    label = path.stem
    return CssPreset(
        id=label,
        name=dict.fromkeys(("pl", "en", "de"), label),
        description={},
        path=path,
        builtin=False,
    )


def _is_valid_css(text: str) -> bool:
    """Sprawdza, że CSS nie jest pusty i ma choć jedną poprawną regułę."""
    if not text.strip():
        return False
    rules = tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True)
    return any(getattr(rule, "type", "") != "error" for rule in rules)


def _pick_language(values: dict[str, str], language: str | None) -> str:
    """Wybiera tekst dla języka z fallbackiem en → pl."""
    lang = language or current_language()
    if values.get(lang):
        return values[lang]
    for fallback in _FALLBACK_LANGS:
        if values.get(fallback):
            return values[fallback]
    return ""


def _css_internal_path(opf_dir: str) -> str:
    """Ścieżka arkusza presetu wewnątrz archiwum (względem korzenia EPUB)."""
    return posixpath.normpath(posixpath.join(opf_dir, PRESET_CSS_REL))


def _resolve_path(href: str, base_dir: str) -> str:
    """Rozwiązuje publication href do ścieżki w archiwum (wspólna polityka)."""
    return resolve_from_directory(base_dir, href)


def _relative_href(target_internal: str, base_dir: str) -> str:
    """Liczy ``href`` z ``base_dir`` do ``target_internal`` (POSIX)."""
    return posixpath.relpath(target_internal, base_dir if base_dir else ".")


def _spine_paths(epub: Epub) -> list[str]:
    """Zwraca wewnętrzne ścieżki plików spine (kolejność czytania)."""
    href_by_id = {item.id: item for item in epub.manifest}
    opf_dir = epub.opf_dir()
    paths: list[str] = []
    for idref in epub.spine:
        item = href_by_id.get(idref)
        if item is not None:
            paths.append(_resolve_path(item.href, opf_dir))
    return paths


def _find_head(root: etree._Element) -> tuple[etree._Element | None, str]:
    """Znajduje ``<head>`` z uwzględnieniem namespace XHTML."""
    ns = _namespace(root.tag)
    head = root.find(f"{{{ns}}}head") if ns else root.find("head")
    if head is None and ns != _XHTML_NS:
        head = root.find(f"{{{_XHTML_NS}}}head")
        if head is not None:
            ns = _XHTML_NS
    return head, ns


def _namespace(tag: object) -> str:
    """Wyciąga namespace z tagu lxml (``{ns}local`` → ``ns``)."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1 : tag.index("}")]
    return ""


def _suffix(href: str) -> str:
    """Zwraca rozszerzenie href bez fragmentu URL."""
    path, _fragment = urldefrag(href)
    return Path(path).suffix.lower()


def _parse_xml(data: bytes) -> etree._ElementTree:
    """Parsuje XML/XHTML do drzewa (recover) przez centralne, utwardzone API."""
    return parse_untrusted_tree(data)


def _serialize_xml(tree: etree._ElementTree) -> bytes:
    """Serializuje drzewo zachowując deklarację XML i ewentualny doctype."""
    return etree.tostring(tree, xml_declaration=True, encoding="utf-8")
