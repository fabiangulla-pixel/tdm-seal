# TDM Seal

> Sellado declarativo de derechos TDM para PDF editoriales

TDM Seal añade, verifica y documenta una declaración
[TDMRep](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/)
(`tdm:reservation`, `tdm:policy`) dentro de los metadatos XMP de nivel de
documento de un PDF, sin tocar páginas, tipografías, imágenes, marcadores,
enlaces, adjuntos ni otros metadatos.

TDMRep **no es DRM ni un bloqueo técnico**: es una señal declarativa,
legible por máquinas, de que los derechos de minería de textos y datos están
reservados. Ver `TDM_SEAL_ESPECIFICACION_IMPLEMENTACION.md` (en la carpeta
padre) para la especificación funcional y técnica completa.

## Estado actual (v0.2.1 — núcleo + GUI + PDF/A + políticas + ISCC)

Implementado y con pruebas automatizadas:

- **PDF/A-1/2/3**: al sellar, se declara el namespace TDMRep en el
  esquema de extensión XMP (`pdfaExtension:schemas`), conservando los
  esquemas que ya traía el archivo; PDF/A-4 no lo necesita y no se toca.
  La plantilla del esquema es una redacción propia (el archivo oficial de la
  PDF Association no se pudo descargar; ver `resources/SOURCES.md`);
- **validación PDF/A con veraPDF**, opcional: si `verapdf` está en el PATH
  se valida el resultado; si no, el reporte marca `SKIPPED` con un aviso que
  explica cómo instalarlo, y el sellado sigue;
- **Policy Builder**: `tdmseal policy build` (o el botón "Generar
  artefactos de política…" de la GUI) genera `policy.jsonld` (ODRL, perfil
  TDMRep), `policy.html` y `tdmrep.json` para publicar en el sitio;
- **identificador ISCC del archivo** (`tdmseal/iscc.py`, vía `iscc-core`):
  se calcula a partir del propio contenido binario del PDF, no de su nombre
  ni de su ubicación, por lo que reconoce el mismo archivo aunque cambie de
  nombre o de carpeta, y cambia si el contenido cambia. No sustituye al
  ISBN, al DOI ni a ONIX: los complementa. Visible en `inspect`, `show`,
  `audit` y en el reporte JSON. Primer paso hacia la visión SIMEH (registro
  de ISCC + declaración TDM + sello de tiempo RFC 3161 + historial de
  versiones — pendiente);
- inspección de PDF (versión, páginas, cifrado, firma digital, XMP, TDMRep);
- lectura y escritura de TDMRep en el XMP de nivel de documento, preservando
  todo lo demás;
- idempotencia (sellar dos veces no duplica; cambiar el valor lo actualiza);
- PDF firmado digitalmente → se omite por defecto (`TDM021`);
- PDF cifrado → se omite por defecto (`TDM020`);
- guardado en archivo nuevo (nunca sobrescribe el original);
- relectura y verificación del XMP escrito;
- verificación de integridad sintáctica (`pikepdf.Pdf.check_pdf_syntax`);
- comprobación de invariantes no-metadata (páginas, geometría, anotaciones,
  adjuntos);
- reporte JSON por archivo procesado, con datos opcionales de la editorial;
- valores por defecto (editorial, reserva, política) guardados en
  `~/.tdmseal/config.json` — `tdmseal config show|set` desde la CLI, o el
  botón "Guardar como valores por defecto" en la GUI;
- CLI: `tdmseal seal`, `inspect`, `show`, `audit`, `config`, `policy build`;
- **GUI de escritorio (PySide6)**: `TDM-Seal.bat` (doble clic, prepara su
  propio entorno virtual la primera vez) o `dist/TDM-Seal.exe` (standalone,
  sin Python instalado — ver `scripts/build_exe.bat`).

**Limitaciones conocidas de lo que ya existe:**

- el ISCC actual es solo Data-Code + Instance-Code, es decir, una huella de
  los **bytes** del archivo: cambia al sellar. Todavía no hay Content-Code
  (huella del texto), que es el que sobrevive al sellado y a otras
  conversiones;
- el esquema de extensión PDF/A no es el archivo oficial de la PDF
  Association;
- los PDF de prueba se generan con pikepdf; faltan fixtures reales de
  PDF/A, PDF/UA, firmados y con formularios.

**Pendiente** (hoja de ruta v0.5–v1.0): ISCC de contenido, EPUB, señales
de sitio (`tdmrep.json` con `tdmseal site`, cabeceras HTTP), política ODRL
completa, preferencias IETF AIPREF, aviso visible opcional, manifiesto de
catálogo y empaquetado 1.0.

## Instalación

Requiere Python 3.10+. **Importante:** si el proyecto vive en una carpeta
sincronizada con Google Drive (como aquí), crea el entorno virtual **fuera**
de esa carpeta — la sincronización en vivo puede corromper la instalación de
pip a mitad de escritura. Por ejemplo:

```bash
python -m venv "$HOME/.venvs/tdm-seal"
"$HOME/.venvs/tdm-seal/Scripts/python" -m pip install -e ".[dev]"

# Para usar la GUI, añade el extra "gui" (PySide6):
"$HOME/.venvs/tdm-seal/Scripts/python" -m pip install -e ".[dev,gui]"
```

## GUI de escritorio

La forma más simple es hacer doble clic en **`TDM-Seal.bat`**: la primera vez
crea el entorno virtual e instala las dependencias automáticamente; las
siguientes veces abre la GUI directamente.

También existe **`dist/TDM-Seal.exe`** (y una copia en la carpeta padre,
junto a la especificación), un ejecutable standalone que no requiere Python
instalado. Para regenerarlo tras un cambio de código:

```bash
scripts\build_exe.bat
```

La GUI permite: cargar un PDF o una carpeta, auditar automáticamente (PDF/A,
firma, cifrado, TDM actual), completar los datos de la editorial y la
política TDM, y aplicar el sello a todo el lote con un botón. Los valores de
editorial/política pueden guardarse como valores por defecto para no
reescribirlos cada vez.

## Uso (línea de comandos)

```bash
# Sellar un PDF (reserva por defecto = 1)
tdmseal seal libro.pdf

# Con política pública
tdmseal seal libro.pdf --reservation 1 --policy "https://editorial.example.edu/tdm/policy.jsonld"

# Carpeta completa
tdmseal seal ./pdf-finales --recursive

# Solo auditar, sin modificar
tdmseal inspect libro.pdf

# Extraer la declaración TDMRep
tdmseal show libro_TDM.pdf

# Auditar un catálogo completo
tdmseal audit ./catalogo --recursive

# Ver / guardar valores por defecto (editorial, reserva, política)
tdmseal config show
tdmseal config set --publisher-name "Editorial Universidad Ejemplo" --publisher-acronym EUE

# Generar policy.jsonld, policy.html y tdmrep.json para el sitio web
tdmseal policy build --output-dir ./publicar \
  --publisher-name "Editorial Universidad Ejemplo" \
  --publisher-website https://editorial.example.edu \
  --publisher-email derechos@example.edu
```

Cada `seal` genera `archivo_TDM.pdf` junto al original y
`archivo_TDM.pdf.report.json` con la auditoría completa (hashes, validaciones,
avisos).

## Desarrollo

```bash
set TDMSEAL_PY=C:\ruta\a\tu\venv\Scripts\python.exe
check.bat
```

Corre `ruff check`, `ruff format --check` y la suite de `pytest`. Los
fixtures de prueba se generan programáticamente con pikepdf (no se versionan
PDF binarios).

## Principios de diseño (manifiesto, sección 37 de la especificación)

1. No tocar el contenido visible.
2. No borrar metadatos que no pertenezcan a TDM Seal.
3. No romper PDF/A ni PDF/UA.
4. No modificar archivos firmados por defecto.
5. No subir archivos a servicios externos.
6. No afirmar que TDMRep bloquea técnicamente la IA.
7. Registrar exactamente qué se modificó.
8. Ser idempotente.
9. Permitir verificar la declaración sin depender del propio programa.
