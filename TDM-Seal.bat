@echo off
REM Lanzador de doble clic para la GUI de TDM Seal.
REM Usa el entorno virtual local (fuera de Google Drive, ver AGENTS.md).
REM La primera vez lo crea; y cada vez que cambia pyproject.toml (version
REM nueva, dependencias nuevas) reinstala el proyecto antes de abrir la GUI.

setlocal
set VENV_DIR=%USERPROFILE%\.venvs\tdm-seal
set PROJECT_DIR=%~dp0
set PY=%VENV_DIR%\Scripts\python.exe

if not exist "%VENV_DIR%\Scripts\pythonw.exe" (
    echo Preparando TDM Seal por primera vez, un momento...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual. Instale Python 3.10 o superior.
        pause
        exit /b 1
    )
    "%PY%" -m pip install --upgrade pip
)

REM Huella de pyproject.toml: si cambio, hay que reinstalar.
"%PY%" -c "import hashlib,pathlib,sys;p=pathlib.Path(r'%PROJECT_DIR%pyproject.toml');s=pathlib.Path(r'%VENV_DIR%\tdmseal.huella');sys.exit(0 if s.exists() and s.read_text()==hashlib.sha256(p.read_bytes()).hexdigest() else 1)"
if errorlevel 1 (
    echo Instalando o actualizando dependencias de TDM Seal...
    "%PY%" -m pip install -e "%PROJECT_DIR%.[gui,iscc]"
    if errorlevel 1 (
        echo Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )
    "%PY%" -c "import hashlib,pathlib;p=pathlib.Path(r'%PROJECT_DIR%pyproject.toml');pathlib.Path(r'%VENV_DIR%\tdmseal.huella').write_text(hashlib.sha256(p.read_bytes()).hexdigest())"
)

start "" "%VENV_DIR%\Scripts\pythonw.exe" -m tdmseal.gui
