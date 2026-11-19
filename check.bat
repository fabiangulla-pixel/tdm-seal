@echo off
REM Corre lint, formato y pruebas. Falla si algo no pasa.
REM Requiere que TDMSEAL_PY apunte al Python del entorno virtual del proyecto,
REM o que "python" en PATH sea ese entorno.

setlocal
REM Ubicarse siempre en la carpeta del repo: si cmd arranca en otro sitio,
REM "ruff check ." recorreria esa carpeta (visto el 19-nov-2026).
cd /d "%~dp0"
if "%TDMSEAL_PY%"=="" set TDMSEAL_PY=python

echo [1/3] ruff check
%TDMSEAL_PY% -m ruff check .
if errorlevel 1 goto fail

echo [2/3] ruff format --check
%TDMSEAL_PY% -m ruff format --check .
if errorlevel 1 goto fail

echo [3/3] pytest
%TDMSEAL_PY% -m pytest -q
if errorlevel 1 goto fail

echo.
echo [OK] Todo paso.
exit /b 0

:fail
echo.
echo [FALLO] check.bat encontro errores.
exit /b 1
