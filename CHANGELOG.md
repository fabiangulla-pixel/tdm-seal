# Changelog

## [0.5.0] - 2026-11-19

### Añadido

- **ISCC de contenido** (`tdmseal/iscc/`): ISCC-CODE completo (Meta-Code +
  Text-Code + Data-Code + Instance-Code), idéntico al de iscc-sdk 0.9.7 para
  PDF (comprobado con fixtures y con PDF reales). El **Text-Code** se calcula
  sobre el texto y **no cambia al sellar**; una prueba lo exige.
  - Extra opcional `pip install tdm-seal[iscc]` (pypdfium2, la misma
    extracción de texto que usa iscc-sdk). Sin él, se calculan Meta, Data e
    Instance y se avisa de que falta el de contenido.
  - PDF sin capa de texto (escaneo sin OCR): se omite el Text-Code y se avisa
    (el SDK calcularía el de un texto vacío, que no identifica nada).
- **ISCC en el XMP** con namespace propio
  `https://github.com/fabiangulla-pixel/tdm-seal/ns/iscc/1.0/` (prefijo
  `tdmseal`): `isccContentCode`, `isccSource`, `isccSourceDatahash`.
  Declarado en el esquema de extensión PDF/A. Re-sellar conserva la
  procedencia original. Ver `docs/xmp-namespace-iscc.md`.
- CLI: `tdmseal iscc ARCHIVO|CARPETA [--recursive] [--json]` y
  `tdmseal seal --iscc`. `inspect` y `show` muestran el ISCC declarado.
- Reporte JSON: bloque `iscc` (entrada, salida y
  `content_code_unchanged_by_sealing`) y validaciones `iscc_xmp_re_read` e
  `iscc_content_stable`.
- GUI: casilla "Calcular ISCC" (activada por defecto) y columna ISCC con las
  unidades en la ayuda emergente.
- `scripts/iscc_sdk_codes.py`: herramienta de desarrollo para comparar contra
  iscc-sdk.

### Corregido

- **Al sellar se perdían el título, el autor y el asunto** de los PDF con
  actualización incremental cuyo último tráiler no repite `/Info` (lo hace
  MuPDF; visto con un PDF real). pikepdf solo lee el último tráiler y
  guardaba el archivo sin `/Info`, y el sellado se daba por correcto. Ahora
  se vuelve a enlazar el Info heredado (`pdf/docinfo.py`) y una validación
  nueva, `docinfo_preserved`, marca el sellado como fallido si el Info se
  pierde o cambia.
- `scripts/build_exe.bat` no empaquetaba `resources/`: un `.exe` nuevo habría
  fallado al sellar PDF/A por no encontrar la plantilla del esquema.

### Cambiado

- `tdmseal/iscc.py` pasa a ser el paquete `tdmseal/iscc/` (`data.py`
  conserva el ISCC de bytes de la v0.2.0; misma API pública).
- `TDM-Seal.bat` instala `[gui,iscc]`.

## [0.2.1] - 2026-11-19

Puesta al día de la documentación con lo que de verdad hay en el código.
Las funciones de abajo entraron en el commit `ecbf31b` (7-sep-2026), pero el
CHANGELOG y el README las seguían dando por pendientes.

### Documentado (ya existía en el código, con pruebas)

- **PDF/A-1/2/3**: al sellar un PDF/A de esas partes se declara el namespace
  TDMRep en `pdfaExtension:schemas` (`xmp/pdfa_extension.py`), sin tocar los
  esquemas que ya traía el archivo (p. ej. los de InDesign) y sin duplicar
  la entrada si se sella dos veces. PDF/A-4 no usa este mecanismo y no se
  toca. La plantilla del esquema (`resources/tdmrep_pdfa_extension_schema.xml`)
  es una redacción propia: el archivo oficial de la PDF Association no se
  pudo descargar (ver `resources/SOURCES.md`).
- **Validación veraPDF** (`validation/verapdf_validator.py`): si `verapdf`
  está en el PATH, valida el PDF/A sellado; si no, queda `SKIPPED` y el
  sellado sigue.
- **Policy Builder** (`policy/`): `tdmseal policy build` y el botón
  "Generar artefactos de política…" de la GUI generan `policy.jsonld`
  (ODRL, perfil TDMRep), `policy.html` y `tdmrep.json`.
- Pruebas de la GUI con `pytest-qt` (`tests/integration/test_gui.py`).

### Cambiado

- El aviso de veraPDF ausente ahora explica qué significa `SKIPPED` y cómo
  instalarlo, en vez de remitir al código fuente (inútil para quien usa el
  `.exe`).

### Corregido

- `check.bat` se ubica en la carpeta del repo (`cd /d "%~dp0"`): si cmd
  arrancaba en otra carpeta, `ruff check .` recorría esa carpeta y fallaba.

### Fuentes

- `resources/SOURCES.md` registra las especificaciones consultadas el
  19-nov-2026 (TDMRep, IETF AIPREF, ISCC) para las fases siguientes.

## [0.2.0] - 2026-10-27

### Añadido

- **Identificador ISCC del archivo** (`tdmseal/iscc.py`, vía `iscc-core`):
  cada PDF inspeccionado o sellado recibe ahora un código ISCC (Data-Code +
  Instance-Code compuestos) calculado a partir de su contenido binario, no
  de su nombre ni de su ubicación — el mismo archivo conserva el mismo ISCC
  si se renombra o se mueve de carpeta, y cualquier cambio de contenido
  produce un ISCC distinto. No sustituye al ISBN, al DOI ni a ONIX: los
  complementa. Se añade a `PDFInfo.iscc`, al reporte JSON (`input.iscc`,
  `output.iscc`) y a la salida de `tdmseal inspect`, `show` y `audit`.
  Primer paso hacia la visión SIMEH (registro de ISCC + declaración TDM +
  sello de tiempo RFC 3161 + historial de versiones); el registro externo y
  el sellado de tiempo quedan pendientes.

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
