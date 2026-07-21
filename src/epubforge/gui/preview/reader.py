"""Czysty model kontrolowanego symulatora czytnika EPUB.

Moduł nie importuje Qt.  Opisuje neutralne profile viewportu, rozpoznaje
metadane reflowable/fixed-layout i buduje dwie jawnie oddzielone warstwy CSS:
symulatora oraz ustawień użytkownika.  Faktyczny layout i computed style nadal
wylicza Chromium w :mod:`webengine_backend`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted, parse_untrusted_document

_OPF_NS = "http://www.idpf.org/2007/opf"
_VIEWPORT_PART = re.compile(r"(?:^|[,;]\s*)(width|height)\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.I)


class FlowMode(str, Enum):
    """Sposób poruszania się po publikacji reflowable."""

    SCROLL = "scroll"
    PAGES = "pages"


class LayoutMode(str, Enum):
    """Algorytm layoutu wynikający z metadanych publikacji."""

    REFLOWABLE = "reflowable"
    FIXED = "pre-paginated"


class ComparisonMode(str, Enum):
    """Jawny wariant udziału CSS wydawcy i użytkownika."""

    PUBLISHER = "publisher"
    PUBLISHER_USER = "publisher_user"
    UNSTYLED = "unstyled"


@dataclass(frozen=True)
class UserStyleSettings:
    """Odwracalna warstwa preferencji czytelnika, niezależna od CSS książki."""

    enabled: bool = True
    font_size_px: float = 18.0
    line_height: float = 1.5
    margin_px: float = 24.0
    font_family: str = "system-ui, sans-serif"
    force_font: bool = False
    page_color: str = "#ffffff"
    text_color: str = "#1a1a1a"
    disable_publisher_styles: bool = False
    disable_embedded_fonts: bool = False

    def normalized(self) -> UserStyleSettings:
        """Zwraca wartości ograniczone do bezpiecznego zakresu symulatora."""
        return replace(
            self,
            font_size_px=min(72.0, max(8.0, float(self.font_size_px))),
            line_height=min(3.0, max(0.8, float(self.line_height))),
            margin_px=min(160.0, max(0.0, float(self.margin_px))),
            font_family=_safe_font_family(self.font_family),
            page_color=_safe_color(self.page_color, "#ffffff"),
            text_color=_safe_color(self.text_color, "#1a1a1a"),
        )


@dataclass(frozen=True)
class ReaderProfile:
    """Neutralny profil viewportu; DPR nie zmienia geometrii CSS px."""

    key: str
    label: str
    width: int
    height: int
    device_pixel_ratio: float
    page_margin: int
    base_font: str
    fallback_font: str
    font_size_px: float
    line_height: float
    page_color: str
    text_color: str
    orientation: str
    flow: FlowMode
    user_style: UserStyleSettings = field(default_factory=UserStyleSettings)

    def normalized(self) -> ReaderProfile:
        """Normalizuje własny viewport bez udawania fizycznego urządzenia."""
        width = min(3840, max(240, int(self.width)))
        height = min(3840, max(240, int(self.height)))
        return replace(
            self,
            width=width,
            height=height,
            device_pixel_ratio=min(4.0, max(0.5, float(self.device_pixel_ratio))),
            page_margin=min(160, max(0, int(self.page_margin))),
            base_font=_safe_font_family(self.base_font),
            fallback_font=_safe_font_family(self.fallback_font),
            font_size_px=min(72.0, max(8.0, float(self.font_size_px))),
            line_height=min(3.0, max(0.8, float(self.line_height))),
            page_color=_safe_color(self.page_color, "#ffffff"),
            text_color=_safe_color(self.text_color, "#1a1a1a"),
            orientation="landscape" if width > height else "portrait",
            user_style=self.user_style.normalized(),
        )


@dataclass(frozen=True)
class PublicationLayout:
    """Metadane layoutu potrzebne do wyboru jednego z dwóch algorytmów."""

    layout: LayoutMode = LayoutMode.REFLOWABLE
    viewport_width: float | None = None
    viewport_height: float | None = None
    spread: str = "auto"
    orientation: str = "auto"
    page_progression: str = "default"
    document_direction: str = "ltr"
    has_writing_mode: bool = False
    has_multimedia: bool = False
    limitations: tuple[str, ...] = ()

    @property
    def fixed_layout(self) -> bool:
        return self.layout is LayoutMode.FIXED


@dataclass(frozen=True)
class ReaderLayers:
    """CSS i opis aktywnych nadpisań przekazywany do WebEngine/inspektora."""

    simulator_css: str
    user_css: str
    publisher_disabled: bool
    columns_enabled: bool
    overrides: Mapping[str, str]
    limitations: tuple[str, ...] = ()


def _profile(
    key: str,
    label: str,
    width: int,
    height: int,
    dpr: float,
    margin: int,
    size: float,
    line_height: float,
    flow: FlowMode,
    *,
    page_color: str = "#ffffff",
    text_color: str = "#1a1a1a",
) -> ReaderProfile:
    user = UserStyleSettings(
        font_size_px=size,
        line_height=line_height,
        margin_px=margin,
        page_color=page_color,
        text_color=text_color,
    )
    return ReaderProfile(
        key,
        label,
        width,
        height,
        dpr,
        margin,
        "serif",
        "system-ui, sans-serif",
        size,
        line_height,
        page_color,
        text_color,
        "landscape" if width > height else "portrait",
        flow,
        user,
    )


READER_PROFILES: Mapping[str, ReaderProfile] = MappingProxyType(
    {
        "eink-small": _profile(
            "eink-small", "e-ink mały", 600, 800, 1.0, 28, 18, 1.45, FlowMode.PAGES
        ),
        "eink-large": _profile(
            "eink-large", "e-ink duży", 824, 1200, 1.0, 40, 20, 1.5, FlowMode.PAGES
        ),
        "phone-portrait": _profile(
            "phone-portrait", "telefon pionowy", 390, 844, 3.0, 20, 18, 1.5, FlowMode.SCROLL
        ),
        "tablet-portrait": _profile(
            "tablet-portrait", "tablet pionowy", 768, 1024, 2.0, 42, 19, 1.5, FlowMode.PAGES
        ),
        "tablet-landscape": _profile(
            "tablet-landscape", "tablet poziomy", 1024, 768, 2.0, 52, 19, 1.5, FlowMode.PAGES
        ),
        "custom": _profile(
            "custom", "własny viewport", 800, 600, 1.0, 32, 18, 1.5, FlowMode.SCROLL
        ),
    }
)


def default_profile() -> ReaderProfile:
    """Zwraca stabilny profil startowy, bez nazwy konkretnego urządzenia."""
    return READER_PROFILES["tablet-portrait"]


def profile_by_key(key: str) -> ReaderProfile:
    """Rozwiązuje zapisany klucz, także dawną wartość ``default``."""
    return READER_PROFILES.get(key, default_profile())


def user_style_from_mapping(
    value: object, fallback: UserStyleSettings | None = None
) -> UserStyleSettings:
    """Odtwarza ustawienia z configu, ignorując nieznane lub błędne pola."""
    base = fallback or UserStyleSettings()
    if not isinstance(value, Mapping):
        return base.normalized()
    fields = UserStyleSettings.__dataclass_fields__
    accepted = {key: item for key, item in value.items() if key in fields}
    try:
        return replace(base, **accepted).normalized()
    except (TypeError, ValueError):
        return base.normalized()


def custom_profile_from_mapping(value: object) -> ReaderProfile:
    """Nakłada bezpieczne wymiary własnego viewportu na profil bazowy."""
    base = READER_PROFILES["custom"]
    if not isinstance(value, Mapping):
        return base
    accepted = {
        key: value[key]
        for key in (
            "width",
            "height",
            "device_pixel_ratio",
            "page_margin",
            "font_size_px",
            "line_height",
            "page_color",
            "text_color",
            "flow",
        )
        if key in value
    }
    if "flow" in accepted:
        try:
            accepted["flow"] = FlowMode(str(accepted["flow"]))
        except ValueError:
            accepted["flow"] = base.flow
    try:
        return replace(base, **accepted).normalized()
    except (TypeError, ValueError):
        return base


def detect_publication_layout(opf: bytes, xhtml: str | bytes) -> PublicationLayout:
    """Wykrywa rendition, progression i viewport bez modyfikacji publikacji."""
    limitations: list[str] = []
    layout = LayoutMode.REFLOWABLE
    spread, orientation, progression = "auto", "auto", "default"
    try:
        root = parse_untrusted(opf)
        metadata = root.find(f"{{{_OPF_NS}}}metadata")
        if metadata is not None:
            properties = {
                (meta.get("property") or "").strip(): (meta.text or "").strip()
                for meta in metadata.findall(f"{{{_OPF_NS}}}meta")
            }
            if properties.get("rendition:layout") == LayoutMode.FIXED.value:
                layout = LayoutMode.FIXED
            spread = properties.get("rendition:spread", spread)
            orientation = properties.get("rendition:orientation", orientation)
        spine = root.find(f"{{{_OPF_NS}}}spine")
        if spine is not None:
            progression = (spine.get("page-progression-direction") or progression).lower()
    except (etree.XMLSyntaxError, ValueError):
        limitations.append("Nie odczytano metadanych layoutu z OPF.")

    raw = xhtml.encode("utf-8") if isinstance(xhtml, str) else xhtml
    viewport_width: float | None = None
    viewport_height: float | None = None
    direction = "rtl" if progression == "rtl" else "ltr"
    has_writing_mode = b"writing-mode" in raw.lower()
    has_multimedia = False
    try:
        doc, _doctype = parse_untrusted_document(raw)
        html_dir = (doc.get("dir") or "").lower()
        body = next((node for node in doc.iter() if _local_name(node) == "body"), None)
        if html_dir in {"ltr", "rtl"}:
            direction = html_dir
        elif body is not None and (body.get("dir") or "").lower() in {"ltr", "rtl"}:
            direction = (body.get("dir") or "ltr").lower()
        for node in doc.iter():
            name = _local_name(node)
            if name == "meta" and (node.get("name") or "").lower() == "viewport":
                values = {
                    key.lower(): float(value)
                    for key, value in _VIEWPORT_PART.findall(node.get("content") or "")
                }
                viewport_width = values.get("width")
                viewport_height = values.get("height")
            if name in {"audio", "video", "object", "canvas"}:
                has_multimedia = True
    except (etree.XMLSyntaxError, ValueError):
        limitations.append("Nie odczytano viewportu dokumentu.")

    if layout is LayoutMode.FIXED and (viewport_width is None or viewport_height is None):
        limitations.append("Fixed-layout bez pełnego viewportu dokumentu; użyto wymiarów profilu.")
    if has_writing_mode:
        limitations.append(
            "Writing-mode jest renderowany przez Chromium, ale nawigacja stron ma ograniczoną analizę."
        )
    if has_multimedia:
        limitations.append(
            "Multimedia są widoczne jako ograniczenie symulatora i mogą nie być odtwarzane."
        )
    if progression == "rtl":
        limitations.append("RTL odwraca kierunek nawigacji stron podglądu.")
    elif direction == "rtl":
        limitations.append("Kierunek dokumentu RTL odwraca nawigację przy domyślnym progression.")
    return PublicationLayout(
        layout=layout,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        spread=spread,
        orientation=orientation,
        page_progression=progression,
        document_direction=direction,
        has_writing_mode=has_writing_mode,
        has_multimedia=has_multimedia,
        limitations=tuple(limitations),
    )


def build_reader_layers(
    profile: ReaderProfile,
    publication: PublicationLayout,
    user_style: UserStyleSettings | None = None,
    comparison: ComparisonMode = ComparisonMode.PUBLISHER_USER,
) -> ReaderLayers:
    """Buduje warstwy symulatora; fixed-layout nigdy nie otrzymuje columns."""
    profile = profile.normalized()
    user = (user_style or profile.user_style).normalized()
    use_user = comparison is ComparisonMode.PUBLISHER_USER and user.enabled
    publisher_disabled = comparison is ComparisonMode.UNSTYLED or (
        use_user and user.disable_publisher_styles
    )
    columns = not publication.fixed_layout and profile.flow is FlowMode.PAGES
    direction = "rtl" if publication.page_progression == "rtl" else publication.document_direction
    simulator: list[str] = [
        ":root { color-scheme: light; }",
        f"html {{ background: {profile.page_color}; color: {profile.text_color}; direction: {direction}; }}",
    ]
    limitations = list(publication.limitations)
    if publication.fixed_layout:
        doc_width = publication.viewport_width or profile.width
        doc_height = publication.viewport_height or profile.height
        scale = min(profile.width / doc_width, profile.height / doc_height)
        simulator.extend(
            [
                "html, body { margin: 0 !important; padding: 0 !important; overflow: hidden !important; }",
                f"body {{ width: {doc_width:g}px !important; height: {doc_height:g}px !important; transform: scale({scale:.8f}); transform-origin: top left; }}",
            ]
        )
    elif columns:
        gap = profile.page_margin * 2
        simulator.extend(
            [
                "html, body { height: 100vh !important; overflow: hidden !important; }",
                f"body {{ box-sizing: border-box; margin: 0 !important; padding: {profile.page_margin}px !important; column-width: calc(100vw - {gap}px); column-gap: {gap}px; column-fill: auto; width: max-content; max-height: 100vh; }}",
                "body > * { break-inside: auto; }",
            ]
        )
    else:
        simulator.extend(
            [
                "html { overflow-x: hidden; overflow-y: auto; }",
                f"body {{ box-sizing: border-box; max-width: 100%; margin: 0 !important; padding: {profile.page_margin}px !important; }}",
            ]
        )

    user_css: list[str] = []
    overrides: dict[str, str] = {
        "profil": profile.label,
        "viewport": f"{profile.width}x{profile.height} CSS px",
        "DPR (symulacyjne)": f"{profile.device_pixel_ratio:g}",
        "algorytm": "fixed-layout (skalowanie)"
        if publication.fixed_layout
        else f"reflowable ({profile.flow.value})",
    }
    if publisher_disabled:
        user_css.append(
            "body, body * { all: revert !important; box-sizing: border-box !important; }"
        )
        overrides["CSS wydawcy"] = "wyłączony"
    if use_user and not publication.fixed_layout:
        user_css.extend(
            [
                f"body {{ font-size: {user.font_size_px:g}px !important; line-height: {user.line_height:g} !important; color: {user.text_color} !important; background: {user.page_color} !important; }}",
                f"body {{ padding-left: {user.margin_px:g}px !important; padding-right: {user.margin_px:g}px !important; }}",
            ]
        )
        overrides.update(
            {
                "rozmiar tekstu": f"{user.font_size_px:g}px",
                "line-height": f"{user.line_height:g}",
                "margines użytkownika": f"{user.margin_px:g}px",
                "kolorystyka": f"{user.page_color} / {user.text_color}",
            }
        )
        if user.force_font or user.disable_embedded_fonts:
            user_css.append(f"body, body * {{ font-family: {user.font_family} !important; }}")
            overrides["font"] = user.font_family
        if user.disable_embedded_fonts:
            overrides["fonty osadzone"] = "wyłączone dla kaskady przez wymuszony fallback"
            limitations.append(
                "Załadowanych FontFace nie można usunąć z Chromium; wymuszono rodzinę fallback w osobnej warstwie."
            )
    elif use_user and publication.fixed_layout:
        limitations.append(
            "Ustawienia typografii pominięto dla fixed-layout, aby nie uszkodzić geometrii strony."
        )

    return ReaderLayers(
        simulator_css="\n".join(simulator),
        user_css="\n".join(user_css),
        publisher_disabled=publisher_disabled,
        columns_enabled=columns,
        overrides=MappingProxyType(overrides),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def reader_payload(
    profile: ReaderProfile,
    publication: PublicationLayout,
    user_style: UserStyleSettings,
    comparison: ComparisonMode,
) -> dict[str, Any]:
    """Serializowalny opis stanu do raportu inspektora i testów GUI."""
    layers = build_reader_layers(profile, publication, user_style, comparison)
    return {
        "profile": asdict(profile.normalized()),
        "publication": asdict(publication),
        "comparison": comparison.value,
        "columns_enabled": layers.columns_enabled,
        "publisher_disabled": layers.publisher_disabled,
        "overrides": dict(layers.overrides),
        "limitations": list(layers.limitations),
    }


def _local_name(node: etree._Element) -> str:
    try:
        return etree.QName(node.tag).localname.lower()
    except (TypeError, ValueError):
        return ""


def _safe_color(value: str, fallback: str) -> str:
    candidate = str(value).strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
        return candidate.lower()
    return fallback


def _safe_font_family(value: str) -> str:
    candidate = str(value).strip()
    return (
        candidate
        if candidate and re.fullmatch(r"[\w\s,'\"-]{1,120}", candidate)
        else "system-ui, sans-serif"
    )
