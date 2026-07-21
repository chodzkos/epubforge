# Informacje o komponentach zewnętrznych w pełnym buildzie

EpubForge jest udostępniany na licencji MIT. Pełne artefakty Windows zawierają
również biblioteki Qt dostarczane przez PySide6 oraz Qt WebEngine z Chromium.
Niniejszy plik jest informacją techniczną, a nie poradą prawną i nie zastępuje
tekstów licencji dołączanych przez dystrybuowane komponenty.

## Qt for Python / PySide6 i Qt

PySide6 jest oficjalnym bindingiem Qt dla Pythona. Qt jest oferowane na licencji
komercyjnej albo na właściwych licencjach open source, w tym LGPLv3/GPLv3,
zależnie od modułu i sposobu dystrybucji. Szczegóły i obowiązujące teksty:

- https://doc.qt.io/qt-6/licensing.html
- https://www.qt.io/licensing/open-source-lgpl-obligations
- https://code.qt.io/cgit/pyside/pyside-setup.git/tree/LICENSES

## Qt WebEngine i Chromium

Qt WebEngine integruje Chromium. Przy dystrybucji trzeba spełnić zarówno warunki
Qt WebEngine, jak i licencji komponentów Chromium. Część Qt jest dostępna m.in.
na LGPLv3/GPL, a kod Chromium obejmuje wiele licencji zewnętrznych; oficjalna,
wersjonowana lista znajduje się w dokumentacji Qt użytej wersji:

- https://doc.qt.io/qt-6/qtwebengine-licensing.html
- https://doc.qt.io/qt-6/qtwebengine-overview.html

Wydawca artefaktu powinien przed publikacją zachować pliki licencyjne pochodzące
z użytych kół PySide6 oraz wynik wygenerowanej listy third-party dla dokładnie
przypiętej wersji Qt/Chromium. Sam ten skrót nie jest pełną listą atrybucji.
