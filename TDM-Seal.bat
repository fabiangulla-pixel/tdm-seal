@echo off
REM Lanzador de doble clic para la GUI de TDM Seal.
REM Usa el entorno virtual local (fuera de Google Drive, ver AGENTS.md).
REM Si no existe, lo crea e instala el proyecto en modo editable con soporte GUI.

setlocal
set VENV_DIR=%USERPROFILE%\.venvs\tdm-seal
set PROJECT_DIR=%~dp0

if not exist "%VENV_DIR%\Scripts\pythonw.exe" (
    echo Preparando TDM Seal por primera vez, un momento...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual. ^¿Esta Python instalado y en PATH?
        pause
        exit /b 1
    )
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV_DIR%\Scripts\python.exe" -m pip install -e "%PROJECT_DIR%.[gui,iscc]"
    if errorlevel 1 (
        echo Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )
)

start "" "%VENV_DIR%\Scripts\pythonw.exe" -m tdmseal.gui
