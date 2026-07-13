"""Runtime hook PyInstaller — oznacza build ONEFILE jako portable.

Dołączany WYŁĄCZNIE przez ``epubforge-portable.spec`` (wariant jednoplikowy),
nie przez ``epubforge-dir.spec`` (onedir/instalator). Uruchamia się przy starcie
zamrożonego procesu, zanim wystartuje kod aplikacji, i ustawia atrybut na
``sys``. ``epubforge.core.config`` czyta go (``_epubforge_portable``), by trzymać
``config.json`` OBOK ``epubforge.exe`` — bez pliku-sidecara ``portable.flag``.

Onedir/instalator hooka nie ma → atrybut nieustawiony → config trafia do
lokalizacji systemowej (``%APPDATA%\\epubforge``).
"""

import sys

sys._epubforge_portable = True  # marker builda portable czytany przez core.config
