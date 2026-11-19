# Changelog

## [0.9.0] - 2026-11-19

### Añadido

- **Aviso visible opcional, desactivado por defecto** (`tdmseal/notice.py`,
  `docs/aviso-visible.md`): `tdmseal seal --visible-notice`, o la casilla de
  la GUI con confirmación explícita. En PDF, una página final del tamaño de la
  última; en EPUB, un XHTML al final del spine. Texto en español e inglés.
  **Nunca se modifican páginas ni documentos existentes** (lo comprueban las
  pruebas) y es idempotente.
- Código **`TDM023`**: aviso rechazado en PDF firmados (aun con
  `--force-signed`), PDF/A, PDF/UA y EPUB de maquetación fija. En PDF
  etiquetados la página se marca como *Artifact*.
- `compare_non_metadata_invariants(..., added_pages=N)` y
  `compare_container(..., added=…)` admiten solo esas adiciones al final.
- La plantilla del texto queda **pendiente de revisión de estilo** (una
  única constante en `notice.py`).

## [0.8.0] - 2026-11-19

### Añadido

- **Política ODRL completa** (perfil TDMRep, sec. 7): condiciones por
  finalidad con la restricción `purpose` (`tdm:research` /
  `tdm:non-research`). Cada una puede ser `free`, `consent`, `compensate`
  o `none`. Un uso que no se ofrece **no se convierte en `prohibition`**
  (el perfil la desaconseja): simplemente no aparece como permiso. Si no se
  ofrece nada, la política se rechaza, porque una oferta vacía no sirve.
- Titular con vCard (`fn`, `nickname`, `hasEmail`, `hasURL`) y página o
  formulario de licencias (`--license-url`). URL de publicación explícita
  (`--policy-url`), usada a la vez en `uid`, `tdmrep.json` y el HTML.
- **`policy.html` reescrito como invitación a licenciar**: resumen inicial
  ("la reserva no es una negativa definitiva, sino una invitación a pedir
  licencia"), tabla de condiciones por finalidad, qué incluir en la
  solicitud, tabla de preferencias AIPREF, señales legibles por máquinas,
  metaetiquetas TDMRep en el propio `<head>` y resumen en inglés.
- **`tdmseal policy check policy.jsonld`** y validador del perfil
  (`validate_policy_jsonld`): `@context`, `uid`, `Offer`, `profile`,
  `assigner` vCard, permisos `tdm:mine`, deberes y restricciones definidos,
  sin `obligation` ni `prohibition`. El Policy Builder lo aplica siempre
  antes de escribir.
- `tdmseal policy build`: opciones `--policy-url`, `--research`,
  `--non-research`, `--license-url`, `--aipref`.

## [0.7.0] - 2026-11-19

Fases 3 y 5 del plan, fusionadas: AIPREF solo puede expresarse a nivel de
sitio, así que van juntas.

### Añadido

- **`tdmseal site --base-url URL --out CARPETA`** (`tdmseal/site.py`):
  genera sin publicar nada
  - `.well-known/tdmrep.json` (TDMRep sec. 6.1);
  - `servidor/apache.conf` y `servidor/nginx.conf` con las cabeceras HTTP
    `tdm-reservation`, `tdm-policy` (sec. 6.2, la vía preferida) y
    `Content-Usage` (AIPREF), y el tipo JSON para `tdmrep.json`;
  - `servidor/robots-content-usage.txt`: líneas para **añadir** al robots.txt;
  - `servidor/html-meta.html`: metaetiquetas TDMRep (sec. 6.3);
  - `LEEME.txt` con dónde va cada archivo.
- **`tdmseal site --check tdmrep.json`**: valida un archivo existente contra
  TDMRep (arreglo, `location` con `/` o `*` y `$` solo al final,
  `tdm-reservation` 0/1 numérico, `tdm-policy` URL absoluta; avisa de
  política con reserva 0 y de propiedades desconocidas).
- **Vocabulario IETF AIPREF** (`tdmseal/aipref.py`), según
  draft-ietf-aipref-vocab-08 y attach-05: categorías `train-ai`, `ai-use`,
  `search`; por defecto `train-ai=n, ai-use=n, search=y` (el catálogo sigue
  apareciendo en buscadores). Se rechazan categorías que el borrador no
  define (`tdm`, `train-genai`…) para no emitir señales que nadie entiende.
  Aviso si se niegan usos de IA con `tdm-reservation` 0.
- `tdmseal seal --aipref` y `tdmseal config set --aipref`: la preferencia
  se registra en el reporte (`aipref`, con `embedded_in_file: false`).
  **Limitación documentada:** el borrador no define cómo incrustarla en PDF
  ni EPUB (attach-05 sec. 1.3.1), así que no se escribe en el archivo.

## [0.6.0] - 2026-11-19

### Añadido

- **EPUB 2 y 3** (`tdmseal/epub/`): `tdm:reservation` y `tdm:policy` en el
  paquete OPF según TDMRep (sec. 6.4-6.5): en EPUB 3,
  `<meta property="tdm:…">` con `prefix="tdm: http://www.w3.org/ns/tdmrep#"`
  en `<package>` (conservando los prefijos que ya hubiera); en EPUB 2,
  `<meta name="tdm:…" content="…"/>`. Si un EPUB 3 trae también la forma
  EPUB 2, se actualizan las dos para no dejar valores contradictorios.
- Mismos invariantes que en PDF: archivo nuevo `_TDM.epub`, idempotencia,
  relectura y verificación. El contenedor se reescribe cambiando **solo el
  OPF**: mismas entradas, orden, fechas y contenido (CRC) en todo lo demás,
  `mimetype` primero y sin comprimir (validación `container_unchanged`). Si
  el original no cumplía la regla del `mimetype`, se repara y se avisa.
- EPUB con DRM o recursos cifrados (`META-INF/encryption.xml` con algo
  distinto de la ofuscación de fuentes, Adobe ADEPT `rights.xml`, Readium
  LCP `license.lcpl`) se omiten con el código nuevo **`TDM022`**. La
  ofuscación de fuentes no es DRM: se sella y se avisa.
- **EPUBCheck opcional** (`validation/epubcheck_validator.py`): con
  `TDMSEAL_EPUBCHECK_JAR` + Java, o `epubcheck` en el PATH. Valida original y
  sellado y solo falla si el sellado añade errores nuevos (`TDM034`); si no
  está instalado, `SKIPPED` con instrucciones.
- **ISCC de EPUB**, idéntico al de iscc-sdk (comprobado con fixtures y con 3
  EPUB reales). El Text-Code requiere el extra aparte `tdm-seal[iscc-epub]`
  (iscc-tika, el mismo extractor del SDK, ~110 MB, fuera del `.exe`); sin
  él se calculan Meta, Data e Instance y se avisa.
- `discovery.iter_documents` (PDF + EPUB, sin distinguir mayúsculas) y
  `documents.py` (`inspect_document`, `seal_document`). CLI y GUI aceptan
  ambos formatos; columna "Formato" en la GUI.
- Códigos nuevos: `TDM005` (EPUB ilegible), `TDM022`, `TDM033` (el
  contenedor cambió en algo más que el OPF), `TDM034`.

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
