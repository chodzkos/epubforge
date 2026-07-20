"""Testy czystej logiki inspektora CSS (spany, replace, podgląd) — bez Qt."""

from __future__ import annotations

from epubforge.fixers.css_rules import (
    CssDecl,
    CssRuleInfo,
    build_preview_html,
    declarations_to_preview,
    parse_rules,
    parse_single_rule,
    replace_rule,
    sample_for_selector,
)

# ── parse_rules: spany ───────────────────────────────────────────────────────


def test_parse_simple_rule_span() -> None:
    """Span prostej reguły obejmuje od selektora do '}' włącznie."""
    src = "h1 { color: red }"
    (rule,) = parse_rules(src)
    start, end = rule.span
    assert src[start:end] == "h1 { color: red }"
    assert rule.selector == "h1"
    assert rule.declarations == [CssDecl("color", "red", False)]


def test_parse_multiselector() -> None:
    """Selektor wieloczłonowy zachowany w całości."""
    (rule,) = parse_rules("h1, h2 { margin: 0 }")
    assert rule.selector == "h1, h2"


def test_parse_two_rules_disjoint_spans() -> None:
    """Dwie reguły: każdy span zaczyna się selektorem, kończy '}', spany rozłączne."""
    src = "h1 { color: red }\n\np { margin: 1em }\n"
    a, b = parse_rules(src)
    assert src[a.span[0] : a.span[1]] == "h1 { color: red }"
    assert src[b.span[0] : b.span[1]] == "p { margin: 1em }"
    assert a.span[1] <= b.span[0]  # rozłączne


def test_parse_with_comments() -> None:
    """Komentarze przed regułą i w środku nie psują spanu."""
    src = "/* przed */\np { /* w środku */ color: red }"
    (rule,) = parse_rules(src)
    assert src[rule.span[0] : rule.span[1]].startswith("p {")
    assert src[rule.span[1] - 1] == "}"


def test_parse_brace_in_string_and_url() -> None:
    """'}' w stringu i w url(...) nie kończy reguły przedwcześnie."""
    src = 'p { content: "}"; background: url("a}b.png"); color: red }'
    (rule,) = parse_rules(src)
    assert src[rule.span[0] : rule.span[1]] == src  # cała reguła
    assert src[rule.span[1] - 1] == "}"


def test_parse_media_sets_media() -> None:
    """Reguła w @media ma ustawione media i poprawny span (offset absolutny)."""
    src = "@media print {\n  h1 { color: black }\n}\n"
    rules = parse_rules(src)
    assert len(rules) == 1
    assert rules[0].media == "print"
    assert src[rules[0].span[0] : rules[0].span[1]] == "h1 { color: black }"


def test_duplicate_selector_has_distinct_tree_paths() -> None:
    """Selektor nie jest identyfikatorem: wystąpienia mają różne ścieżki CSSOM."""
    src = ".x { color: blue } @media screen { .x { color: red } }"
    first, second = parse_rules(src)
    assert first.selector == second.selector == ".x"
    assert first.rule_path == (0,)
    assert second.rule_path == (1, 0)
    assert second.contexts == ("@media screen",)


def test_nested_supports_and_media_keep_full_context() -> None:
    """Zagnieżdżony kontekst nie znika z mapy źródłowej reguły."""
    src = "@supports (display:grid) { @media screen { p { display:grid } } }"
    (rule,) = parse_rules(src)
    assert rule.rule_path == (0, 0, 0)
    assert rule.contexts == ("@supports (display:grid)", "@media screen")


def test_parse_font_face_not_previewable() -> None:
    """@font-face → previewable=False."""
    (rule,) = parse_rules('@font-face { font-family: Foo; src: url("x.ttf") }')
    assert rule.previewable is False
    assert rule.selector.startswith("@font-face")


# ── replace_rule ─────────────────────────────────────────────────────────────


def test_replace_rule_keeps_outside_bytes_identical() -> None:
    """Podmiana środkowej reguły nie rusza ani bajta poza spanem."""
    src = "a { color: red }\nb { color: green }\nc { color: blue }\n"
    rules = parse_rules(src)
    middle = rules[1]
    out = replace_rule(src, middle.span, "b { color: BLACK }")
    assert out[: middle.span[0]] == src[: middle.span[0]]
    tail_len = len(src) - middle.span[1]
    assert out[len(out) - tail_len :] == src[middle.span[1] :]
    assert "BLACK" in out


# ── declarations_to_preview ──────────────────────────────────────────────────


def test_preview_whitelist_each_property() -> None:
    """Każda właściwość z whitelisty trafia do inline style."""
    decls = [
        CssDecl("font-family", "serif"),
        CssDecl("font-size", "12pt"),
        CssDecl("font-style", "italic"),
        CssDecl("color", "#abc"),
        CssDecl("background-color", "#aabbcc"),
        CssDecl("text-indent", "1.2em"),
        CssDecl("line-height", "1.5"),
        CssDecl("margin-top", "10px"),
        CssDecl("padding-left", "5px"),
        CssDecl("text-decoration", "underline"),
        CssDecl("text-transform", "uppercase"),
    ]
    style, unsupported = declarations_to_preview(decls)
    for decl in decls:
        assert decl.name in style
    assert unsupported == []


def test_preview_units_and_colors() -> None:
    """Jednostki i formaty kolorów przechodzą do podglądu."""
    style, _u = declarations_to_preview(
        [
            CssDecl("font-size", "16px"),
            CssDecl("text-indent", "120%"),
            CssDecl("color", "rgb(1, 2, 3)"),
            CssDecl("background-color", "red"),
        ]
    )
    assert "16px" in style and "120%" in style and "rgb(1, 2, 3)" in style and "red" in style


def test_preview_font_weight_numeric_to_bold() -> None:
    """font-weight: 700 → bold."""
    style, _u = declarations_to_preview([CssDecl("font-weight", "700")])
    assert "font-weight: bold" in style


def test_preview_justify_passes() -> None:
    """text-align: justify przechodzi (działa w silniku Qt)."""
    style, _u = declarations_to_preview([CssDecl("text-align", "justify")])
    assert "text-align: justify" in style


def test_preview_unsupported_listed() -> None:
    """Właściwości spoza whitelisty trafiają na listę nieobsługiwanych."""
    style, unsupported = declarations_to_preview(
        [CssDecl("letter-spacing", "2px"), CssDecl("hyphens", "auto")]
    )
    assert style == ""
    joined = " ".join(unsupported)
    assert "letter-spacing" in joined and "hyphens" in joined


def test_preview_important_value_passes_with_note() -> None:
    """!important: wartość przechodzi, a adnotacja ląduje na liście nieobsługiwanych."""
    style, unsupported = declarations_to_preview([CssDecl("color", "red", important=True)])
    assert "color: red" in style
    assert any("important" in item.lower() for item in unsupported)


# ── sample_for_selector ──────────────────────────────────────────────────────


def test_sample_for_selector() -> None:
    """Dobór przykładu po rodzaju selektora."""
    assert sample_for_selector("h1")[0] == "h1"
    assert sample_for_selector("h3.title")[0] == "h3"
    assert sample_for_selector("p")[0] == "p"
    assert sample_for_selector(".quote")[0] == "blockquote"
    assert sample_for_selector("blockquote")[0] == "blockquote"
    assert sample_for_selector("pre code")[0] == "pre"
    assert sample_for_selector("div#x > span")[0] == "p"  # fallback
    # akapit zawiera polskie diakrytyki
    assert "ż" in sample_for_selector("p")[1]


# ── build_preview_html ───────────────────────────────────────────────────────


def test_build_preview_html_escapes_and_styles() -> None:
    """build_preview_html escapuje tekst i osadza inline style."""
    rule = CssRuleInfo(selector="h1", declarations=[CssDecl("color", "red")], span=(0, 0))
    html, _u = build_preview_html(rule)
    assert 'style="color: red"' in html
    assert html.startswith("<h1") and html.endswith("</h1>")


def test_build_preview_html_escapes_special_chars() -> None:
    """Znaki specjalne w przykładzie są escapowane (brak surowego '<')."""
    rule = CssRuleInfo(selector="pre", declarations=[], span=(0, 0))
    html, _u = build_preview_html(rule)
    body = html[html.index(">") + 1 : html.rindex("<")]
    assert "<" not in body  # tekst zescapowany


# ── parse_single_rule ────────────────────────────────────────────────────────


def test_parse_single_rule_ok() -> None:
    """Poprawna reguła → CssRuleInfo."""
    result = parse_single_rule("p { color: red }")
    assert isinstance(result, CssRuleInfo)
    assert result.selector == "p"


def test_parse_single_rule_errors() -> None:
    """Niepoprawna reguła (pusta wartość) → lista błędów."""
    result = parse_single_rule("p { color: }")
    assert isinstance(result, list)
    assert result  # niepusta lista komunikatów


def test_parse_single_rule_rejects_second_rule() -> None:
    """Warstwa preview nie może przemycić drugiej reguły poza edytowany span."""
    result = parse_single_rule("p { color: red } a { color: blue }")
    assert isinstance(result, list)
    assert any("dokładnie jedną" in error for error in result)
