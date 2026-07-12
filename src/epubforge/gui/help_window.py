"""Treść okna pomocy offline EpubForge — zakładki dla kitowego ``HelpWindow``.

Okno (belka DWM + re-render motywu na ``PaletteChange``) liczy wspólny kit
(:class:`chodzkos_gui_kit.qt.widgets.HelpWindow`). Tu zostaje WYŁĄCZNIE wiedza o
EpubForge: lista zakładek ``(tytuł, html)`` (:func:`help_tabs`) odwzorowująca
realne zakładki GUI (Metadane / Konwerter / Fixer / Eksport Kindle / Edytor /
Walidacja / Spis treści / Statystyki) + przegląd narzędzi zewnętrznych.

Treść opisuje STABILNE fakty (funkcje, formaty, wymagania). Stan ZMIENNY — czy
Java / EpubCheck / Calibre są wykryte w tym środowisku — delegujemy do dolnego
paska statusu narzędzi (``Java: OK/brak`` itd.), zamiast wpisywać go na sztywno.

Kolory idą przez ``palette(...)`` (helpery kitu to robią) — zero hexów; re-render
na zmianę motywu (re-``setHtml`` tym samym html) robi kit dla WSZYSTKICH zakładek.

Wołający::

    from chodzkos_gui_kit.qt.widgets import HelpWindow
    from epubforge.gui.help_window import HELP_TITLE, help_tabs
    HelpWindow(parent, title=HELP_TITLE, tabs=help_tabs()).exec()
"""

from __future__ import annotations

from chodzkos_gui_kit.qt.widgets import (
    code as _code,
)
from chodzkos_gui_kit.qt.widgets import (
    paragraph as _p,
)
from chodzkos_gui_kit.qt.widgets import (
    section as _section,
)
from chodzkos_gui_kit.qt.widgets import (
    table as _table,
)
from chodzkos_gui_kit.qt.widgets import (
    unordered_list as _ul,
)

HELP_TITLE = "Pomoc — EpubForge"


def help_tabs() -> list[tuple[str, str]]:
    """Zakładki pomocy jako ``(tytuł, html)`` — odwzorowują zakładki GUI EpubForge."""
    return [
        ("Metadane", _metadata_tab()),
        ("Konwerter", _converter_tab()),
        ("Fixer", _fixer_tab()),
        ("Eksport Kindle", _kindle_tab()),
        ("Edytor", _editor_tab()),
        ("Walidacja", _validation_tab()),
        ("Spis treści", _toc_tab()),
        ("Statystyki", _stats_tab()),
        ("Narzędzia zewnętrzne", _tools_tab()),
    ]


# ── Treść zakładek (po polsku; opis realnego stanu z kodu) ─────────────────────


def _metadata_tab() -> str:
    intro = _p(
        "Edycja metadanych <b>Dublin Core</b> zapisywanych w pliku OPF EPUB-a. "
        "Poprawne metadane to lepsze katalogowanie w czytnikach i sklepach."
    )
    fields = _table(
        ["Pole", "Element OPF", "Uwagi"],
        [
            ["Tytuł", _code("dc:title"), "Tytuł książki"],
            ["Cykl", "meta (calibre:series)", "Nazwa serii i numer tomu (opcjonalnie)"],
            ["Autorzy", _code("dc:creator"), "Jeden na linię; format: Nazwisko, Imię"],
            ["Język", _code("dc:language"), "Kod języka, np. " + _code("pl") + ", " + _code("en")],
            ["Wydawca", _code("dc:publisher"), "Nazwa wydawcy"],
            ["Data", _code("dc:date"), "Format ISO: " + _code("RRRR-MM-DD")],
            ["Identyfikator", _code("dc:identifier"), "ISBN lub UUID"],
            ["Tematy", _code("dc:subject"), "Tematy/tagi — jeden na linię"],
            ["Opis", _code("dc:description"), "Streszczenie książki"],
        ],
    )
    fetch = _section(
        "Pobieranie metadanych z sieci",
        _p(
            "Przycisk <b>Pobierz metadane…</b> dociąga dane po <b>ISBN</b> z łańcucha źródeł: "
            "<b>Biblioteka Narodowa → LubimyCzytac → Open Library → Google Books</b>. W podglądzie "
            "zaznaczasz, <b>które pola nadpisać</b> — nigdy nie dzieje się to po cichu."
        )
        + _ul(
            "<b>ISBN e-booka a katalog BN</b> — e-booki mają własny ISBN wydania "
            "elektronicznego, którego katalog BN (głównie wydania papierowe) często nie ma. "
            "Gdy ISBN nie trafia, aplikacja automatycznie <b>dopasowuje książkę po tytule</b> "
            "(z metadanych pliku) i wyraźnie to zaznacza w komunikacie "
            "(„dopasowanie po tytule — ISBN e-wydania nieobecny w BN”). Uzupełniane są tylko "
            "metadane bibliograficzne; <b>ISBN pliku pozostaje niezmieniony</b> — zweryfikuj "
            "dopasowanie przed zatwierdzeniem.",
            "<b>Bez ISBN</b> — wpisz <b>Tytuł/Autor</b> i użyj „Szukaj wg tytułu”: wyszukiwarka "
            "LubimyCzytac zwraca listę kandydatów z oceną dopasowania; wybór należy do Ciebie "
            "(poniżej progu pewności nic nie jest zaznaczane automatycznie).",
            "<b>Liczba stron</b> wydania papierowego zapisywana jest do OPF (tylko EPUB 3).",
        ),
    )
    tags = _section(
        "Tagi (taksonomia + AI, opt-in)",
        _p(
            "Sekcja <b>Tagi</b> proponuje tagi po polsku z kaskady źródeł: deskryptory z metadanych, "
            "taksonomia PL, a opcjonalnie model AI."
        )
        + _ul(
            "<b>Zaproponuj tagi</b> — mapuje deskryptory/kategorie na kanoniczne tagi taksonomii; "
            "wybierasz, które dopisać do " + _code("dc:subject") + " (nigdy ciche).",
            "<b>Użyj AI (opt-in)</b> — dołącza tagi z modelu; <b>domyślnie wyłączone</b>. Domyślny "
            "backend to lokalna <b>Ollama</b> (bez klucza); chmury (OpenAI, Anthropic, Gemini, "
            "DeepSeek, GLM) ustawisz w <b>Ustawienia AI…</b>. Klucz API czytany jest wyłącznie ze "
            "<b>zmiennej środowiskowej</b> (w konfiguracji trzymana jest tylko jej nazwa, nigdy sam klucz).",
        ),
    )
    return _section("Metadane (Dublin Core)", intro + fields) + fetch + tags


def _converter_tab() -> str:
    intro = _p("Konwertuje pliki wejściowe do <b>EPUB</b>.")
    formats = _section(
        "Obsługiwane wejście",
        _ul(
            "Tekst: " + _code(".txt") + " " + _code(".md") + " " + _code(".markdown"),
            "Dokumenty: " + _code(".docx") + " " + _code(".odt") + " " + _code(".rtf"),
            "Strony: " + _code(".html") + " " + _code(".htm"),
            "Inne: " + _code(".pdf") + " " + _code(".fb2") + " " + _code(".lit"),
            "Kindle: "
            + _code(".mobi")
            + " "
            + _code(".azw3")
            + " "
            + _code(".azw")
            + " "
            + _code(".prc")
            + " — wejście Kindle wymaga Calibre",
        ),
    )
    options = _section(
        "Opcje",
        _ul(
            "<b>Tytuł / Autor / Język / Okładka</b> — metadane wynikowego EPUB (opcjonalne)",
            "<b>Folder wyjściowy</b> — puste = zapis obok pliku źródłowego",
        ),
    )
    engine = _section(
        "Silnik",
        _ul(
            "<b>Auto</b> — wybiera dostępne narzędzie",
            "<b>Pandoc</b> — szybki, dobry do tekstu i dokumentów",
            "<b>Calibre</b> — szeroki zakres formatów; <b>wymagany dla wejścia Kindle</b>",
            "<b>pdf2md</b> — <b>zalecany silnik dla PDF</b> → EPUB (lepszy skład niż Calibre)",
        ),
    )
    pdf = _p(
        "<b>PDF:</b> po dodaniu pliku PDF — gdy wykryto pdf2md — pojawia się wybór "
        "<b>pdf2md (zalecany)</b> vs <b>Calibre (eksperymentalny)</b>; wybór jest zapamiętywany. "
        "Przycisk <b>Otwórz w pdf2md</b> przekazuje plik do jego GUI. Bez pdf2md tryb Auto dla PDF "
        "wraca do Calibre."
    )
    drm = _p(
        "<b>DRM:</b> pliki Kindle zabezpieczone DRM nie są konwertowane — EpubForge "
        "nie usuwa zabezpieczeń."
    )
    tools = _p(
        "Czy Pandoc / Calibre / pdf2md są dostępne w tym środowisku — sprawdzisz w <b>dolnym pasku "
        "statusu</b> (np. " + _code("Pandoc: OK") + ", " + _code("Calibre: brak") + ")."
    )
    return _section("Konwerter → EPUB", intro) + formats + options + engine + pdf + drm + tools


def _fixer_tab() -> str:
    intro = _p("Naprawa i ujednolicenie EPUB pod czytniki — wsadowo dla wielu plików.")
    hyphen = _section(
        "Dzielenie wyrazów (hyphenacja)",
        _ul(
            "<b>Język słownika</b> (pyphen), np. " + _code("pl") + ", " + _code("en_US"),
            "<b>Metoda</b> — uwaga: <i>soft-hyphen</i> może psuć słownik i wyszukiwarkę na Kindle",
            "<b>Pomiń nagłówki</b> — nie dziel wyrazów w nagłówkach (h1-h3)",
        ),
    )
    css = _section(
        "CSS Fixer",
        _ul(
            "<b>Usuń kolory</b> — usuwa " + _code("color") + "/" + _code("background") + " "
            "(czytnik narzuca własne)",
            "<b>Usuń fonty</b> — zdejmuje narzucone kroje (czytelnik wybiera font)",
            "<b>Dodaj reset CSS</b> — delikatny reset marginesów/paddingu dla spójności",
            "<b>Zamień justowanie na lewe</b> — " + _code("justify") + " → " + _code("left") + " "
            "(mniej dużych odstępów)",
            "<b>Wyłącz hyphenację nagłówków</b> — reguła CSS blokująca dzielenie w nagłówkach",
            "<b>Margines książki</b> — wstrzykuje margines strony w pikselach (0-120)",
        ),
    )
    preset = _p("<b>Preset CSS</b> — dołącza wybrany arkusz stylów do EPUB podczas naprawy.")
    typo = _section(
        "Typografia polska",
        _ul(
            "<b>Cudzysłowy</b> — proste cudzysłowy → pary typograficzne wg języka (pl/en/de)",
            "<b>Pauzy</b> — dywizy w dialogach i wtrąceniach → pauza " + _code("—"),
            "<b>Wielokropek</b> — trzy kropki → " + _code("…"),
            "<b>Twarde spacje</b> — po polskich sierotach (a/i/o/u/w/z) i opcjonalnie przy liczbach",
        ),
    )
    fonts = _p(
        "<b>Przytnij fonty do użytych znaków</b> (subsetting) — przycina osadzone fonty do znaków "
        "faktycznie użytych w treści (zwykle o 70-90% rozmiaru fontu). Wymaga extra "
        + _code("[fonts]")
        + " (fonttools); zwróć uwagę na licencje fontów. Nie mylić z <b>Usuń fonty</b> powyżej."
    )
    images = _section(
        "Optymalizacja obrazów",
        _ul(
            "<b>Kompresja JPEG/PNG</b> — mniejszy plik bez zmiany formatu (bez WebP); okładka pomijana",
            "<b>Maks. dłuższy bok (px)</b> — skalowanie w dół (0 = bez skalowania)",
            "<b>Jakość JPEG</b> (1-95) oraz <b>skala szarości (e-ink)</b> pod czytniki e-ink",
            "EXIF/ICC usuwane; zapis tylko, gdy wynik jest mniejszy",
        ),
    )
    upgrade = _p(
        "<b>Uaktualnij do EPUB 3</b> — konwersja EPUB 2 → 3: "
        + _code("nav.xhtml")
        + " z NCX, "
        + _code("dcterms:modified")
        + ", landmarks z guide. Na wejściu EPUB 3 = brak zmian (no-op)."
    )
    recipes = _p(
        "<b>Uruchom recepturę…</b> — zapisany pipeline fixerów na jednym otwartym EPUB-ie (jeden "
        "zapis): wbudowane " + _code("kindle-pl") + " / " + _code("czytnik-epub") + ", a własne "
        "receptury TOML w katalogu konfiguracji przykrywają wbudowane po nazwie."
    )
    return _section(
        "Fixer (naprawa + CSS)",
        intro + hyphen + typo + css + fonts + images + upgrade + preset + recipes,
    )


def _kindle_tab() -> str:
    intro = _p("Wsadowy eksport EPUB do formatów Kindle: <b>KFX / MOBI / AZW3</b>.")
    kfx = _section(
        "Silnik KFX",
        _ul(
            "<b>Calibre + wtyczka KFX Output</b> — <b>ZALECANE</b>",
            "<b>Kindle Previewer 3</b> — eksperymentalny, wrażliwy na nieidealny EPUB",
        ),
    )
    mobi = _section(
        "Silnik MOBI / AZW3",
        _ul(
            "<b>Calibre " + _code("ebook-convert") + "</b> — ZALECANE (nowoczesny, rozwijany)",
            "<b>kindlegen</b> — generator MOBI Amazona, <b>oficjalnie wycofany</b> (2018); "
            "działa, ale przestarzały — preferuj Calibre",
        ),
    )
    tools = _p(
        "Czy Calibre (+ wtyczka KFX), Kindle Previewer 3 lub kindlegen są dostępne — "
        "zobaczysz w <b>dolnym pasku statusu</b>."
    )
    return _section("Eksport Kindle", intro) + kfx + mobi + tools


def _editor_tab() -> str:
    intro = _p("Szybki podgląd i edycja plików <b>wewnątrz</b> EPUB (quick-fix, nie pełny Sigil).")
    feats = _ul(
        "<b>Drzewo plików</b> — XHTML, CSS i obrazy z archiwum EPUB",
        "<b>Podgląd HTML na żywo</b> + przełącznik <b>tryb: tylko podgląd / edycja</b>",
        "<b>Inspektor CSS</b> — panel reguł CSS z podglądem na żywo",
        "<b>Szukaj i zamień</b> — w całym EPUB, literał lub <b>regex</b>; „Zamień wszystkie” "
        "raportuje liczbę podmian, a dwuklik wyniku ustawia kursor na trafieniu",
        "<b>Zapisz EPUB</b> — zapisuje zmiany z powrotem do pliku",
    )
    deeper = _p(
        "Do głębszej edycji użyj zewnętrznego <b>Sigil</b> lub <b>Calibre</b> "
        "(uruchamiane wprost z aplikacji, jeśli wykryte)."
    )
    return _section("Edytor EPUB", intro + feats + deeper)


def _validation_tab() -> str:
    intro = _p(
        "Walidacja przez <b>EpubCheck 5.x</b> — oficjalny walidator EPUB (W3C). "
        "Uruchamiany jako " + _code("java -jar epubcheck.jar") + "."
    )
    java = _p(
        "<b>Wymaga Javy ≥ 11</b> (np. <b>Eclipse Temurin / Adoptium</b>) oraz pliku "
        + _code("epubcheck.jar")
        + ". EpubForge wykrywa je automatycznie (PATH, App Paths, rejestr Adoptium, "
        "typowe katalogi); ręczny override ścieżek jest w konfiguracji."
    )
    levels = _section(
        "Poziomy wyników",
        _ul(
            "<b>FATAL / ERROR</b> — łamią standard; czytniki lub sklepy mogą plik odrzucić",
            "<b>WARNING</b> — zalecane poprawki",
            "<b>INFO</b> — informacyjne (w tym " + _code("usage") + ")",
        ),
    )
    click = _p(
        "Wyniki są <b>klikalne</b>: dwuklik wiersza z lokalizacją przeskakuje do miejsca "
        "w <b>Edytorze</b>."
    )
    ace = _section(
        "Dostępność (DAISY Ace)",
        _p(
            "<b>Sprawdź dostępność (Ace)</b> — audyt zgodności z WCAG / EPUB Accessibility "
            "(European Accessibility Act obowiązuje e-booki od 2025). Naruszenia trafiają do tej "
            "samej, <b>klikalnej</b> tabeli co EpubCheck. Wymaga narzędzia " + _code("ace") + " "
            "(" + _code("npm install -g @daisy/ace") + "); bez niego funkcja jest wyszarzona."
        ),
    )
    status = _p(
        "Czy Java / EpubCheck / Ace są wykryte <b>teraz</b> — sprawdzisz w <b>dolnym pasku statusu</b> "
        "(" + _code("Java: OK/brak") + " | " + _code("EpubCheck: OK/brak") + ")."
    )
    return _section("Walidacja (EpubCheck)", intro + java) + levels + click + ace + status


def _toc_tab() -> str:
    intro = _p(
        "Podgląd, generowanie, naprawa i edycja drzewa spisu treści (zapis jako "
        + _code("nav")
        + " + "
        + _code("ncx")
        + ")."
    )
    actions = _ul(
        "<b>Generuj</b> — buduje spis z nagłówków; konfigurowalny najgłębszy poziom",
        "<b>Napraw</b> — usuwa martwe wpisy (linki do nieistniejących miejsc)",
        "<b>Dodaj / Usuń</b> — ręczna edycja pozycji",
        "<b>Zapisz do EPUB</b> — zapisuje " + _code("nav") + " i " + _code("ncx"),
    )
    return _section("Spis treści (TOC)", intro + actions)


def _stats_tab() -> str:
    intro = _p("Liczby książki — przydatne przy korekcie i opisie.")
    metrics = _ul(
        "Liczba <b>słów</b> i <b>znaków</b>",
        "Szacowany <b>czas czytania</b>",
        "<b>Najczęstsze słowa</b>",
        "<b>Rozdziały</b> — tytuł i liczba słów",
    )
    report = _p(
        "<b>Eksport HTML</b> / <b>Otwórz raport</b> — zapis i podgląd raportu w przeglądarce."
    )
    return _section("Statystyki", intro + metrics + report)


def _tools_tab() -> str:
    intro = _p(
        "EpubForge korzysta z narzędzi zewnętrznych. Ich status (OK / brak) widać w "
        "<b>dolnym pasku</b>; wykrywanie jest cache'owane (ponowna detekcja co 7 dni)."
    )
    table = _table(
        ["Narzędzie", "Do czego", "Skąd"],
        [
            ["Java ≥ 11", "Uruchamia EpubCheck", "Eclipse Temurin (Adoptium)"],
            ["EpubCheck", "Walidacja EPUB (jar)", "github.com/w3c/epubcheck"],
            ["Pandoc", "Konwersje formatów", "pandoc.org"],
            ["pdf2md", "Zalecany silnik PDF → EPUB", "github.com/chodzkos/pdf2md"],
            ["Calibre", "Konwersje, MOBI/AZW3, KFX (z wtyczką)", "calibre-ebook.com"],
            ["calibredb", "Wzbogacanie biblioteki Calibre (enrich)", "część Calibre"],
            ["DAISY Ace", "Audyt dostępności (a11y)", "npm i -g @daisy/ace"],
            ["Sigil", "Zewnętrzny edytor EPUB", "sigil-ebook.com"],
            ["Kindle Previewer 3", "Eksperymentalny silnik KFX", "Amazon"],
            ["kindlegen", "Generator MOBI (wycofany)", "preferuj Calibre"],
        ],
    )
    setup = _p(
        "<b>EpubCheck:</b> rozpakuj wydanie do katalogu konfiguracji EpubForge albo wskaż jar "
        "w ustawieniach. <b>Java:</b> zainstaluj Temurin — EpubCheck bez Javy nie ruszy."
    )
    return _section("Narzędzia zewnętrzne", intro + table + setup)
