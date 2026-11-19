# Instrucciones para agentes (Claude Code / Codex)

Especificación completa: `../TDM_SEAL_ESPECIFICACION_IMPLEMENTACION.md`.

## Prioridades absolutas (no negociables)

1. Preservar el PDF: no tocar contenido visible, tipografías, imágenes,
   marcadores, enlaces, adjuntos, accesibilidad.
2. Insertar TDMRep únicamente en el XMP de nivel de documento.
3. Preservar todo XMP ajeno a TDMRep (no reconstruir desde cero).
4. Mantener conformidad PDF/A cuando exista.
5. Detectar y rechazar PDF firmados por defecto (`TDM021`).
6. Validar el resultado después de escribirlo (releer XMP, `check_pdf_syntax`,
   invariantes no-metadata).
7. No dar por terminado ningún paso sin un test reproducible en `tests/`.

## Entorno

El proyecto vive en una carpeta sincronizada con Google Drive. **No crear el
`.venv` dentro de esta carpeta**: la sincronización en vivo corrompe pip a
mitad de instalación (visto en la sesión que creó este repositorio). Crear el
entorno virtual en disco local, p. ej. `%USERPROFILE%\.venvs\tdm-seal`, e
instalar el proyecto en modo editable desde ahí.

Antes de tocar código: `check.bat` (con `TDMSEAL_PY` apuntando al Python del
venv) debe pasar limpio. Después de cada cambio, vuelve a correrlo.

Al generar el `.exe` (`scripts\build_exe.bat`), PyInstaller también debe
correr fuera de la carpeta sincronizada con Drive (usa `%TEMP%`): escribe
miles de archivos intermedios y corre el mismo riesgo que `pip install`. Solo
el `.exe` final se copia de vuelta al proyecto (`dist/`, gitignorado — no se
versiona un binario de ~60 MB).

## GUI (v0.1.1, implementada)

`gui.py` usa **PySide6**, no tkinter — decisión explícita del usuario por
acabado visual (tkinter se veía "limitada en estilo"; se evaluaron tkinter,
PySide6 y CustomTkinter, se eligió PySide6). El trabajo de sellado corre en
un `QThread` con workers (`_AuditWorker`, `_SealWorker`) para no bloquear la
interfaz. `TDM-Seal.bat` es el lanzador de doble clic (autoinstala su venv la
primera vez); `dist/TDM-Seal.exe` es el standalone.

Al modificar la GUI, probarla con un guion que dirija `MainWindow`
directamente (sin depender de `QFileDialog`, que es modal) — ver el patrón de
sondeo con `QTimer` usado para verificar la sesión que la creó: conectar a
señales *después* de iniciar un `QThread` es una carrera (el hilo puede
terminar y emitir antes de que el `connect()` se ejecute); sondear un efecto
observable (p. ej. `btn_open_folder.isEnabled()`) es más fiable que confiar en
el orden de conexión de señales entre hilos.

**Bug real encontrado y corregido en esta sesión:** en el `.exe` de
PyInstaller, `QFileDialog.getOpenFileNames()`/`getExistingDirectory()` con el
diálogo nativo de Windows (COM `IFileOpenDialog`) nunca mostraban ninguna
ventana — el clic no producía error ni excepción, simplemente no pasaba nada
(el proceso seguía vivo). Problema conocido de PySide6 congelado con
PyInstaller. Solución: pasar `options=QFileDialog.Option.DontUseNativeDialog`
(ver `gui.py`, `_select_file`/`_select_folder`) para forzar el diálogo propio
de Qt, que no depende de COM y funciona igual congelado que sin congelar. Se
verificó con clics y tecleo reales (pywinauto + `SendInput`, no llamadas
directas a métodos de Python) contra el `.exe` compilado, no solo contra el
script sin congelar — probar solo lo segundo NO habría detectado este bug.

## Estado (v0.5.0, 19-nov-2026)

Hecho y probado: PDF/A-1/2/3 (`xmp/pdfa_extension.py`), veraPDF opcional
(`SKIPPED` si no está), Policy Builder (`policy/`, `tdmseal policy build`),
ISCC (`iscc/`: `data.py` de bytes; `content.py` completo, compatible con
iscc-sdk; `xmp.py` namespace propio), Info heredado (`pdf/docinfo.py`),
tests de GUI con `pytest-qt` (`tests/integration/test_gui.py`).

ISCC: para comparar contra iscc-sdk real hay un venv aparte en
`%USERPROFILE%\.venvs\iscc-sdk-ref` (iscc-sdk 0.9.7, Python 3.12); si existe,
`test_full_iscc_code_matches_live_iscc_sdk` lo usa, si no se omite. iscc-sdk
NO debe ser dependencia del proyecto (pesado: Tika embebido, numpy, exiv2).

Regla nueva: todo lo que escriba en el PDF debe comprobar después que el
diccionario Info sigue igual (`compare_docinfo`). pikepdf no ve el `/Info`
de tráileres anteriores; ver `pdf/docinfo.py`.

Para correr `check.bat` desde PowerShell usar
`cmd.exe /d /c "<ruta completa>\check.bat"`: sin `/d` y sin ruta completa,
cmd no lo encontró (arrancaba en `%USERPROFILE%`, visto el 19-nov-2026).
`check.bat` hace `cd /d "%~dp0"` para no correr ruff fuera del repo.

veraPDF ya no está instalado en este equipo (`C:\build_rf\tools\` no
existe tras la migración al MSI): sus pruebas corren solo con mocks.

## Qué falta

- Hoja de ruta v0.5–v1.0 (ISCC de contenido, EPUB, `tdmseal site`, ODRL
  completo, AIPREF, aviso visible, manifiesto, 1.0): ver el prompt de la
  sesión del 19-nov-2026 y las decisiones que se tomen en cada fase.
- Fixtures de integración con PDF/A-1/2/3/4, PDF/UA, firmados, cifrados,
  con adjuntos y formularios reales (hoy los tests usan PDFs mínimos
  generados con pikepdf; faltan los fixtures reales de la sección 19).
- Reemplazar el esquema de extensión PDF/A redactado por el oficial de la
  PDF Association cuando alguien lo descargue a mano.
