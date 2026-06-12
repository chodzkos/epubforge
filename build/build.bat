@echo off
REM Lokalny build EpubForge dla Windows: portable .exe + instalator.
REM Wymaga: pip install -e ".[build,gui]"  oraz (dla instalatora) Inno Setup (ISCC w PATH).

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo === Wybor Pythona 3.10+ ===
set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.10) do (
        if not defined PYTHON_CMD (
            py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
            if not errorlevel 1 set "PYTHON_CMD=py -%%V"
        )
    )
)

if not defined PYTHON_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [BLAD] EpubForge wymaga Pythona 3.10 lub nowszego.
    echo Domyslne polecenie python jest za stare albo Python 3.10+ nie jest zainstalowany.
    echo Zainstaluj Python 3.12 z python.org i upewnij sie, ze dziala: py -3.12 --version
    exit /b 1
)

for /f "delims=" %%P in ('!PYTHON_CMD! -c "import sys; print(sys.executable + chr(32) + sys.version.split()[0])"') do echo Uzywam: %%P

echo === Przygotowanie zaleznosci buildu ===
pushd ..
!PYTHON_CMD! -m pip install -e ".[build,gui]"
if errorlevel 1 (
    echo [BLAD] Nie udalo sie zainstalowac zaleznosci buildu.
    exit /b 1
)
popd

!PYTHON_CMD! check_build_env.py
if errorlevel 1 (
    exit /b 1
)

echo === Czyszczenie poprzednich buildow ===
if exist dist rmdir /s /q dist
if exist build-tmp rmdir /s /q build-tmp

REM Ikona: generuj placeholder tylko gdy nie ma ani prawdziwej, ani wczesniejszej.
if exist "..\src\epubforge\gui\assets\icon.ico" (
    echo Uzywam icon.ico z assets.
) else (
    if not exist icon.ico (
        echo Generuje placeholder icon.ico...
        !PYTHON_CMD! create_icon.py
    )
)

echo === [1/3] Build PORTABLE (onefile) ===
!PYTHON_CMD! -m PyInstaller epubforge-portable.spec --clean --noconfirm --distpath dist --workpath build-tmp
if not exist "dist\epubforge.exe" (
    echo [BLAD] Portable build nie powiodl sie.
    exit /b 1
)
REM Marker wariantu portable — obecnosc obok exe przelacza config na katalog
REM obok exe (GUI_STANDARD v2.0 sekcja 8). Dystrybuuj exe RAZEM z tym plikiem.
echo portable > "dist\portable.flag"
echo [OK] dist\epubforge.exe (+ portable.flag)

echo === [2/3] Build ONEDIR (do instalatora) ===
!PYTHON_CMD! -m PyInstaller epubforge-dir.spec --clean --noconfirm --distpath dist --workpath build-tmp
if not exist "dist\epubforge\epubforge.exe" (
    echo [BLAD] Onedir build nie powiodl sie.
    exit /b 1
)
echo [OK] dist\epubforge\

echo === [3/3] Instalator (Inno Setup) ===
set "ISCC_CMD="
where ISCC >nul 2>nul
if not errorlevel 1 set "ISCC_CMD=ISCC"
if not defined ISCC_CMD (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
        set "ISCC_CMD=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    )
)
if not defined ISCC_CMD (
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
        set "ISCC_CMD=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    )
)

if defined ISCC_CMD (
    echo Uzywam Inno Setup: !ISCC_CMD!
    REM Odczytaj wersje z pakietu do zmiennej.
    !PYTHON_CMD! -c "import epubforge; print(epubforge.__version__)" > _ver.tmp
    set /p EF_VERSION=<_ver.tmp
    del _ver.tmp
    "!ISCC_CMD!" /DMyAppVersion=!EF_VERSION! installer.iss
    if exist "dist\epubforge-setup.exe" (
        echo [OK] dist\epubforge-setup.exe
    ) else (
        echo [BLAD] Inno Setup nie utworzyl instalatora.
        exit /b 1
    )
) else (
    echo [POMINIETO] Nie znaleziono ISCC.exe - instalator nie zbudowany.
    echo Zainstaluj Inno Setup 6 lub dodaj ISCC.exe do PATH, aby zbudowac dist\epubforge-setup.exe.
)

echo.
echo === GOTOWE ===
echo Portable:   dist\epubforge.exe
echo Instalator: dist\epubforge-setup.exe (jesli ISCC dostepny)
endlocal
