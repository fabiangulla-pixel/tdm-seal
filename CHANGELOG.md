# Changelog

## [0.1.2] - 2026-08-19

### Corregido

- **Bug crítico en `TDM-Seal.exe`**: los diálogos "Seleccionar PDF" /
  "Seleccionar carpeta" nunca aparecían al correr desde el ejecutable
  compilado con PyInstaller (el diálogo nativo de Windows se quedaba
  colgado sin error). Se fuerza `QFileDialog.Option.DontUseNativeDialog`.
  Verificado con clics y tecleo reales contra el `.exe`, no solo contra el
  script sin congelar.

## [0.1.1] - 2026-08-19

### Añadido

- **GUI de escritorio (PySide6)** (`tdmseal/gui.py`): carga de PDF/carpeta,
  auditoría automática, sellado por lotes en hilo de fondo (no bloquea la
  interfaz), reporte visible, botón "Abrir carpeta". Elegida sobre tkinter
  por acabado visual (decisión del usuario).
- `TDM-Seal.bat`: lanzador de doble clic que prepara su propio entorno
  virtual local la primera vez.
- `scripts/build_exe.bat` + `dist/TDM-Seal.exe`: ejecutable standalone con
  PyInstaller (~62 MB, sin dependencia de Python instalado). El build se
  hace fuera de la carpeta sincronizada con Drive; solo el `.exe` final se
  copia de vuelta.
- `PublisherInfo` (datos de la editorial/titular de derechos: nombre, sigla,
  sitio web, correo de derechos) — puramente informativo, se incluye en el
  reporte JSON pero **no** se escribe en el PDF ni en TDMRep (que solo
  admite `reservation`/`policy_url`).
- `tdmseal/appconfig.py`: valores por defecto persistidos en
  `~/.tdmseal/config.json` (editorial, reserva, política), compartidos entre
  CLI (`tdmseal config show|set`) y GUI (botón "Guardar como valores por
  defecto").
- `tdmseal/discovery.py`: `iter_pdfs()` compartido entre CLI y GUI (antes
  duplicado).

## [0.1.0] - 2026-08-19

Núcleo inicial de TDM Seal, siguiendo los pasos A-G de la instrucción de
arranque de la especificación.

### Añadido

- Inspector de PDF: versión, páginas, PDF/A, PDF/UA, cifrado, firma digital,
  XMP y declaración TDMRep existente.
- Editor XMP controlado (lxml) que preserva todos los namespaces y
  propiedades ajenos a TDMRep.
- Lectura y escritura de `tdm:reservation` / `tdm:policy` en el XMP de nivel
  de documento, en forma de elemento o de atributo.
- Orquestador `seal_pdf`: detecta y omite PDF firmados (`TDM021`) o cifrados
  (`TDM020`) por defecto, guarda siempre en archivo nuevo, releé y verifica
  el XMP escrito, comprueba integridad sintáctica y no-metadata.
- Idempotencia verificada: sellar dos veces no duplica declaraciones.
- Reporte JSON de auditoría por archivo.
- CLI: `tdmseal seal`, `inspect`, `show`, `audit`.
- 21 pruebas automatizadas (unitarias + integración) con fixtures generados
  con pikepdf.
- Entorno de calidad: ruff (lint + formato), `check.bat` como CI local, git
  inicializado con `.gitignore`/`.gitattributes`.

### Pendiente para v0.2.0

- Soporte PDF/A completo (PDF/A XMP Extension Schema, plantilla de la PDF
  Association, validación veraPDF).
