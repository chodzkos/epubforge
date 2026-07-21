"""Strukturalne testy symulatora czytnika (bez Qt i bez pixel-perfect)."""

from __future__ import annotations

from epubforge.gui.preview.quality import parse_quality_report
from epubforge.gui.preview.reader import (
    READER_PROFILES,
    ComparisonMode,
    FlowMode,
    LayoutMode,
    PublicationLayout,
    UserStyleSettings,
    build_reader_layers,
    detect_publication_layout,
)

_OPF_REFLOW = b"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata/><manifest/><spine page-progression-direction="ltr"/>
</package>"""

_OPF_FIXED_RTL = b"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:spread">landscape</meta>
    <meta property="rendition:orientation">portrait</meta>
  </metadata>
  <manifest/><spine page-progression-direction="rtl"/>
</package>"""

_XHTML = """<html xmlns="http://www.w3.org/1999/xhtml"><head>
<meta name="viewport" content="width=1200,height=1600"/></head>
<body><p data-epubforge-node-id="n1">Tekst</p></body></html>"""


def test_neutral_profiles_have_complete_viewport_data() -> None:
    assert set(READER_PROFILES) == {
        "eink-small",
        "eink-large",
        "phone-portrait",
        "tablet-portrait",
        "tablet-landscape",
        "custom",
    }
    for profile in READER_PROFILES.values():
        assert profile.width >= 240 and profile.height >= 240
        assert profile.device_pixel_ratio > 0
        assert profile.user_style.font_size_px > 0
        assert profile.orientation in {"portrait", "landscape"}


def test_reflowable_scroll_and_pages_use_distinct_layers() -> None:
    publication = detect_publication_layout(_OPF_REFLOW, _XHTML)
    assert publication.layout is LayoutMode.REFLOWABLE
    scroll_profile = READER_PROFILES["phone-portrait"]
    scroll = build_reader_layers(scroll_profile, publication)
    pages = build_reader_layers(READER_PROFILES["tablet-portrait"], publication)
    assert scroll.columns_enabled is False
    assert "column-width" not in scroll.simulator_css
    assert pages.columns_enabled is True
    assert "column-width" in pages.simulator_css


def test_fixed_layout_is_scaled_and_never_gets_columns() -> None:
    publication = detect_publication_layout(_OPF_FIXED_RTL, _XHTML)
    assert publication.fixed_layout
    assert publication.viewport_width == 1200
    assert publication.viewport_height == 1600
    assert publication.spread == "landscape"
    assert publication.orientation == "portrait"
    assert publication.page_progression == "rtl"
    layers = build_reader_layers(READER_PROFILES["tablet-portrait"], publication)
    assert layers.columns_enabled is False
    assert "column-width" not in layers.simulator_css
    assert "transform: scale(" in layers.simulator_css
    assert "direction: rtl" in layers.simulator_css


def test_user_style_is_separate_reversible_layer() -> None:
    profile = READER_PROFILES["phone-portrait"]
    publication = PublicationLayout()
    user = UserStyleSettings(
        enabled=True,
        font_size_px=24,
        line_height=1.8,
        margin_px=35,
        force_font=True,
        font_family="Literata, serif",
        disable_publisher_styles=True,
        disable_embedded_fonts=True,
    )
    combined = build_reader_layers(profile, publication, user, ComparisonMode.PUBLISHER_USER)
    publisher = build_reader_layers(profile, publication, user, ComparisonMode.PUBLISHER)
    unstyled = build_reader_layers(profile, publication, user, ComparisonMode.UNSTYLED)
    assert "font-size: 24px" in combined.user_css
    assert "Literata, serif" in combined.user_css
    assert combined.publisher_disabled is True
    assert publisher.publisher_disabled is False
    assert publisher.user_css == ""
    assert unstyled.publisher_disabled is True


def test_fixed_layout_skips_destructive_user_typography() -> None:
    fixed = PublicationLayout(layout=LayoutMode.FIXED, viewport_width=800, viewport_height=600)
    layers = build_reader_layers(
        READER_PROFILES["tablet-landscape"],
        fixed,
        UserStyleSettings(font_size_px=42, force_font=True),
    )
    assert "font-size: 42px" not in layers.user_css
    assert any("fixed-layout" in item for item in layers.limitations)


def test_quality_report_keeps_node_for_source_navigation() -> None:
    issues = parse_quality_report(
        {
            "issues": [
                {
                    "kind": "element_overflow",
                    "category": "quality_warning",
                    "message": "Element wychodzi poza viewport.",
                    "node_id": "node-7",
                    "value": "900px",
                }
            ]
        }
    )
    assert len(issues) == 1
    assert issues[0].node_id == "node-7"
    assert issues[0].kind == "element_overflow"


def test_profile_flow_is_explicit_enum() -> None:
    assert READER_PROFILES["eink-small"].flow is FlowMode.PAGES
    assert READER_PROFILES["phone-portrait"].flow is FlowMode.SCROLL


def test_document_rtl_is_visible_when_progression_is_default() -> None:
    publication = detect_publication_layout(
        _OPF_REFLOW.replace(b' page-progression-direction="ltr"', b""),
        _XHTML.replace("<body>", '<body dir="rtl">'),
    )
    assert publication.page_progression == "default"
    assert publication.document_direction == "rtl"
    assert (
        "direction: rtl"
        in build_reader_layers(READER_PROFILES["tablet-portrait"], publication).simulator_css
    )
