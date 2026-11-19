@echo off
REM Genera TDM-Seal.exe (GUI standalone) con PyInstaller.
REM
REM El build se hace en disco local (no dentro de la carpeta sincronizada con
REM Google Drive): PyInstaller escribe miles de archivos intermedios y la
REM sincronizacion en vivo puede corromperlos a mitad de escritura (ver
REM AGENTS.md). Solo el .exe final se copia de vuelta al proyecto.

setlocal
set VENV_DIR=%USERPROFILE%\.venvs\tdm-seal
set PROJECT_DIR=%~dp0..
set BUILD_ROOT=%TEMP%\tdm-seal-build

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo No se encontro el entorno virtual en %VENV_DIR%
    echo Ejecuta TDM-Seal.bat una vez, o crea el venv manualmente ^(ver README.md^).
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    "%VENV_DIR%\Scripts\python.exe" -m pip install pyinstaller
)

echo Compilando TDM-Seal.exe (puede tardar varios minutos)...
"%VENV_DIR%\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name TDM-Seal ^
    --workpath "%BUILD_ROOT%\work" ^
    --distpath "%BUILD_ROOT%\dist" ^
    --specpath "%BUILD_ROOT%" ^
    --add-data "%PROJECT_DIR%\resources\*.xml;resources" ^
    --exclude-module iscc_tika ^
    "%PROJECT_DIR%\src\tdmseal\gui.py"

if errorlevel 1 (
    echo Fallo la compilacion.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\dist" mkdir "%PROJECT_DIR%\dist"
copy /Y "%BUILD_ROOT%\dist\TDM-Seal.exe" "%PROJECT_DIR%\dist\TDM-Seal.exe" >nul
copy /Y "%BUILD_ROOT%\dist\TDM-Seal.exe" "%PROJECT_DIR%\..\TDM-Seal.exe" >nul

echo.
echo [OK] TDM-Seal.exe generado en:
echo   %PROJECT_DIR%\dist\TDM-Seal.exe
echo   %PROJECT_DIR%\..\TDM-Seal.exe
