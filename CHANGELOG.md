# Changelog

## [Sin publicar]

### Añadido

- **Registro público propio** (`tdmseal registry`, `registry.py`): sitio
  estático generado desde el manifiesto, que la editorial aloja donde quiera
  (sin intermediarios ni cuotas). Una ficha por obra con la declaración en
  español e inglés (texto del aviso aprobado), tipo de declaración (minería
  autorizada / todos los derechos reservados / reservado con licencia
  disponible), identificadores (ISBN, ISCC completo y por unidades,
  SHA-256), base jurídica, JSON-LD schema.org `Book` y metaetiquetas TDMRep;
  `registro.json` legible por máquina; y, si el manifiesto tiene sello RFC
  3161, la prueba enlazada (se rechaza un sello que no corresponda al
  manifiesto). El índice incluye un buscador y un verificador que calcula la
  huella SHA-256 en el navegador: el archivo no se sube.
- **¿Es este archivo uno de mis libros?** (`tdmseal match`, `match.py`):
  reconoce una copia frente al manifiesto o al `registro.json` aunque esté
  renombrada, re-guardada o sin metadatos, por distancia de Hamming del
  ISCC de contenido. Con *Los días biches*: la copia sin XMP ni `/Info`,
  linealizada, y la copia sin la última página dan "mismo texto" (0/64 bits).
  Limitación conocida: un extracto (20 de 164 páginas) todavía no se
  reconoce.
- **Sello de tiempo RFC 3161** (`tdmseal timestamp create|verify`,
  `timestamp.py`): prueba ante terceros de la fecha de la reserva (lo ideal:
  sellar el manifiesto del catálogo, una sola petición para todas las obras).
  Es lo único que usa la red y solo bajo orden explícita: a la TSA (FreeTSA,
  DigiCert, Sectigo o cualquier URL) se envía solo la huella SHA-256, nunca
  el archivo. Deja `ARCHIVO.tsr` y un recibo `ARCHIVO.tsr.json`. La
  verificación es local: la huella y el nonce siempre; la firma de la TSA con
  OpenSSL (el de Git para Windows sirve) y su certificado raíz (`--ca`). DER
  escrito a mano, sin dependencias nuevas. Probado contra una TSA local
  montada con `openssl ts -reply` (sin red): sello, archivo alterado, CA
  equivocada y rechazo de la TSA.
- **Reserva TDM en ONIX 3.0** (`tdmseal onix add` / `tdmseal onix build`,
  `onix.py`): `EpubUsageConstraint` con `EpubUsageType` 11 (minería de textos
  y datos, incluido el entrenamiento de IA generativa, lista 145) y
  `EpubUsageStatus` 03 (prohibido) o 01 (permitido). `add` la inserta en el
  ONIX que la editorial ya tiene (etiquetas de referencia o cortas, misma
  codificación, en el orden del XSD, sin tocar nada más, idempotente; los
  impresos se dejan igual salvo `--all-products`). `build` crea un ONIX
  mínimo desde PDF/EPUB (ISBN, título, ISCC). Validado contra el XSD oficial
  de EDItEUR (Issue 75), que `instalar_herramientas.ps1 -ConGhostscript`
  descarga para las pruebas.
- **Pruebas con libros reales** (`tests/integration/test_libros_reales.py`):
  cada PDF/EPUB de `%LOCALAPPDATA%\TDMSeal\libros_prueba` (fuera del
  repositorio: tienen derechos reservados) se sella en una copia y se
  comprueba píxel a píxel, contra iscc-sdk, firmado con pyHanko y cifrado.
  Primer libro: *Los días biches* (164 pp.): páginas idénticas al píxel,
  ISCC igual a iscc-sdk, `/Info` heredado conservado, firma de certificación
  válida tras sellar y cifrado conservado.

### Corregido

- El helper de firmas abre los PDF en modo tolerante: pyHanko estricto
  rechazaba el libro real por una generación huérfana que dejó MuPDF.

## [1.3.0] - 2026-11-21

### Añadido

- **Sellar PDF ya firmados sin invalidar la firma.** `--force-signed` (y la
  casilla nueva de la GUI "Sellar también PDF ya firmados") añade el sello
  como actualización incremental (`pdf/incremental.py`): los bytes
  firmados no cambian. Comprobado con pyHanko: firmas de aprobación y de
  certificación siguen válidas (cambio de nivel `LTA_UPDATES`), con xref
  clásica y con stream `/XRef`, y un PDF/A-2b firmado sigue conforme en
  veraPDF. Por defecto los firmados se siguen omitiendo (`TDM021`), ahora
  con un mensaje que explica esta opción.
- Pruebas con PDF cifrados (AES-256, AES-128, RC4), con adjuntos (también
  en árbol de nombres con `/Kids`), con formularios rellenos y con un
  PDF/A-3b con XML adjunto validado en veraPDF.
- La autoprueba (`--autoprueba`, `tdmseal selftest`) tiene un séptimo
  paso: sellar un PDF firmado sin tocar un byte del original.
- Invariantes nuevas: el **contenido** de cada adjunto y los **valores de
  los campos de formulario** deben quedar iguales tras sellar.

### Corregido

- **`--allow-encrypted` entregaba la copia descifrada y sin restricciones**:
  pikepdf guarda sin cifrado por defecto, así que un PDF que prohibía copiar
  texto salía abierto. Ahora se conserva el cifrado (método, claves,
  contraseña de propietario y permisos) y se comprueba
  (`encryption_preserved`); si se perdiera, el sellado falla.
- Los adjuntos en un árbol de nombres con `/Kids` no se contaban (la
  comprobación decía 0 antes y 0 después).
- **La página de aviso desbordaba en libros pequeños** (A5, bolsillo): el
  texto salía por debajo del borde. Ahora el cuerpo se ajusta (10,5 a 7 pt)
  y, si ni así cabe, queda solo el español con una advertencia. El título se
  parte en líneas y la URL de la política solo se corta tras «/».

### Cambiado

- **Texto del aviso visible y de la política HTML revisado** (ver
  `docs/aviso-visible.md`): "se reserva expresamente el derecho a
  autorizar…", mención explícita del uso como fuente de respuestas de IA
  (RAG), forma impersonal y una frase que remite a la declaración legible
  por máquina (TDMRep). Aprobado por el editor.

## [1.2.0] - 2026-11-20

PDF/UA y PDF firmados probados con archivos reales, no con dobles.

### Añadido

- **Validación PDF/UA**: si el original declara `pdfuaid:part`, veraPDF
  valida original y sellado con el perfil `ua1`/`ua2` (validación
  `verapdf_ua`) y solo falla ante incumplimientos nuevos. Prueba real con un
  PDF/UA-1 (Ghostscript + etiquetado con pikepdf): sigue conforme tras
  sellar con ISCC.
- PDF/A-3b real (Ghostscript) añadido a las pruebas de veraPDF: sigue
  conforme tras sellar.
- Pruebas con **firmas criptográficas reales** de pyHanko (de aprobación y
  de certificación), en un entorno aparte (`~\.venvs\pyhanko-ref`);
  pyHanko no es dependencia del proyecto.

### Corregido

- **`--force-signed` invalidaba la firma sin decirlo**: el resultado salía
  `[OK]`. pyHanko confirma que la firma de la copia sellada ya no valida;
  ahora se advierte y se registra `signature_preserved=FAIL` en el reporte.
- **La CLI no mostraba los avisos de los sellados correctos** (p. ej. "el
  original ya incumplía N reglas PDF/A"). Ahora los imprime bajo cada `[OK]`.
- Detector de firmas: ahora reconoce `/FT /Sig` heredado del campo padre y
  las firmas de `/Perms` (`/DocMDP` de certificación, `/UR3` de derechos de
  uso), y no se cuelga con `/Kids` cíclicos.

## [1.1.0] - 2026-11-20

Ronda de uso real: probar el programa como lo usaría una editorial, con las
herramientas de validación instaladas de verdad.

### Corregido

- **Volver a sellar una carpeta** daba error en cada original ("la salida
  ya existe") y creaba copias `_TDM_TDM`. Ahora, al recorrer una carpeta, se
  omiten las salidas `*_TDM.*`, y una salida ya existente se informa como
  **omitida ("ya sellado")**, no como error.
- **Aviso visible en EPUB 2 inválido**: usaba `<section>` y `lang`, que
  XHTML 1.1 no admite. Lo detectó EPUBCheck real; ahora usa `<div>` y
  `xml:lang`.
- **`pip install` no editable rompía PDF/A**: las plantillas del esquema de
  extensión estaban fuera del paquete. Ahora viven en
  `src/tdmseal/resources/` como datos del paquete (y en el `.exe`).
- veraPDF solo juzgaba el archivo sellado: un PDF/A que ya venía defectuoso
  se atribuía al sello. Ahora compara original y sellado y solo falla ante
  incumplimientos nuevos (igual que EPUBCheck). Admite las dos formas de
  JSON de veraPDF.
- `TDM-Seal.bat` solo instalaba dependencias la primera vez: con una
  versión nueva arrancaba sin ellas. Ahora reinstala si cambia
  `pyproject.toml`.
- Desde la GUI y el `.exe`, las llamadas a Java/veraPDF/ssh-keygen ya no
  abren ventanas de consola.

### Añadido

- **`scripts\instalar_herramientas.ps1`**: instala Java (Temurin 21),
  EPUBCheck y veraPDF en `%LOCALAPPDATA%\TDMSeal\tools`, sin permisos de
  administrador ni tocar el PATH (`-ConGhostscript` añade Ghostscript para
  las pruebas). Idempotente.
- `tdmseal/tools.py` encuentra solas esas herramientas; **`tdmseal tools`**
  muestra qué hay. La GUI indica si hay validadores.
- **Autoprueba de punta a punta**: `tdmseal selftest` y
  `TDM-Seal.exe --autoprueba [informe.json]` (sin ventana) sellan un PDF y
  un EPUB de ejemplo, comprueban el esquema PDF/A, la política, el sitio y
  el manifiesto.
- GUI: la celda de estado explica por qué se omitió o falló cada archivo
  (errores, avisos, validaciones, reporte).
- Pruebas `real_tools` con veraPDF, EPUBCheck y Ghostscript reales (se
  omiten donde no están): PDF/A-1b y PDF/A-2b reales siguen conformes tras
  sellar con ISCC; EPUB 2 y 3, con y sin aviso, sin errores de EPUBCheck.

### Verificado en este equipo

- `TDM-Seal.exe` congelado: autoprueba completa OK (incluye EPUBCheck real).
- `TDM-Seal-Setup.exe`: instalación silenciosa sin administrador,
  autoprueba del programa instalado y desinstalación limpia.
- 3 EPUB reales sellados sin errores nuevos de EPUBCheck (uno ya traía 5).

## [1.0.0] - 2026-11-19

### Añadido

- **GUI en cuatro pestañas** (Sellar, Política, Sitio web, Catálogo) con
  estilo propio (Fusion + hoja de estilos: tarjetas, acento verde, controles
  redondeados). La pestaña **Política** tiene condiciones por finalidad,
  preferencias AIPREF y **vista previa** de la página de la política, que se
  refresca al abrirla. Sitio web y Catálogo exponen `tdmseal site` y
  `tdmseal manifest`; el manifiesto corre en segundo plano.
- `docs/guia-10-minutos.md`: "Cómo reservar su catálogo frente al
  entrenamiento de IA en 10 minutos".
- README reescrito: qué hace por vía, comparación honesta con servicios de
  registro comerciales, qué no reemplaza (respaldo jurídico, gestión
  colectiva, negociación) y resumen en inglés.
- `scripts/installer.iss` 1.0.0, con la guía, la documentación y la licencia.

### Corregido

- `scripts/build_exe.bat` no se podía ejecutar: un `echo … (ver README.md).`
  dentro de un bloque `if ( … )` cerraba el bloque antes de tiempo.
- `pyproject.toml`: `license = "MIT"` (SPDX); la forma de tabla quedará sin
  soporte en setuptools el 18-feb-2027.

### Verificado

- `TDM-Seal.exe` (70,8 MB) reconstruido; contiene las dos plantillas del
  esquema PDF/A y pypdfium2, excluye iscc-tika, y abre su ventana en ~6 s.

## [0.10.0] - 2026-11-19

### Añadido

- **`tdmseal manifest CARPETA --out catalogo_tdm.csv|.json`**
  (`tdmseal/manifest.py`): una fila por obra con archivo, formato, título,
  ISBN, SHA-256, tamaño, ISCC completo y sus unidades, ISCC declarado,
  reserva TDM, política, preferencias AIPREF, fecha y estado. CSV en UTF-8
  con BOM (Excel en Windows); JSON con datos de la editorial. Una obra
  ilegible se marca con error y no detiene el catálogo. `--no-iscc` para ir
  más rápido.
- ISBN tomado **solo de los metadatos** (XMP: `prism:isbn`, `dc:identifier`,
  `/ISBN` del Info; OPF: `dc:identifier`) y validado: dígito de control,
  prefijo 978/979 en ISBN-13 y rechazo de rellenos como `0000000000000`
  (que pasan el dígito de control y aparecieron en EPUB reales).
- **Firma opcional** del manifiesto con `--sign-key` (`ssh-keygen -Y sign`,
  incluido en Windows; sin dependencias nuevas): crea `ARCHIVO.sig` e indica
  el comando de verificación. Prueba quién firmó; la fecha es la declarada
  (un sello de tiempo RFC 3161 requeriría red y no se hace).

### Corregido

- `datetime.UTC` (solo existe desde Python 3.11) en el reporte JSON: el
  proyecto admite Python 3.10. Ahora se usa `timezone.utc`.

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
