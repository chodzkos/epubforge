@echo off
REM Lokalny build EpubForge dla Windows: portable .exe + instalator.
REM Wymaga: pip install -e ".[build,gui]"  oraz (dla instalatora) Inno Setup (ISCC w PATH).

setlocal
cd /d "%~dp0"

echo === Czyszczenie poprzednich buildow ===
if exist dist rmdir /s /q dist
if exist build-tmp rmdir /s /q build-tmp

REM Ikona: generuj placeholder tylko gdy nie ma ani prawdziwej, ani wczesniejszej.
if exist "..\src\epubforge\gui\assets\icon.ico" (
    echo Uzywam icon.ico z assets.
) else (
    if not exist icon.ico (
        echo Generuje placeholder icon.ico...
        python create_icon.py
    )
)

echo === [1/3] Build PORTABLE (onefile) ===
python -m PyInstaller epubforge-portable.spec --clean --noconfirm --distpath dist --workpath build-tmp
if not exist "dist\epubforge.exe" (
    echo [BLAD] Portable build nie powiodl sie.
    exit /b 1
)
echo [OK] dist\epubforge.exe

echo === [2/3] Build ONEDIR (do instalatora) ===
python -m PyInstaller epubforge-dir.spec --clean --noconfirm --distpath dist --workpath build-tmp
if not exist "dist\epubforge\epubforge.exe" (
    echo [BLAD] Onedir build nie powiodl sie.
    exit /b 1
)
echo [OK] dist\epubforge\

echo === [3/3] Instalator (Inno Setup) ===
where ISCC >nul 2>nul
if %errorlevel%==0 (
    REM Odczytaj wersje z pakietu do zmiennej.
    python -c "import epubforge; print(epubforge.__version__)" > _ver.tmp
    set /p EF_VERSION=<_ver.tmp
    del _ver.tmp
    ISCC /DMyAppVersion=%EF_VERSION% installer.iss
    if exist "dist\epubforge-setup.exe" (
        echo [OK] dist\epubforge-setup.exe
    ) else (
        echo [BLAD] Inno Setup nie utworzyl instalatora.
        exit /b 1
    )
) else (
    echo [POMINIETO] Brak ISCC w PATH - instalator nie zbudowany.
    echo Zainstaluj Inno Setup, aby zbudowac dist\epubforge-setup.exe.
)

echo.
echo === GOTOWE ===
echo Portable:   dist\epubforge.exe
echo Instalator: dist\epubforge-setup.exe (jesli ISCC dostepny)
endlocal
