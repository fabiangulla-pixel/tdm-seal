# Recursos de terceros

## TDMRepSchema (PDF/A XMP Extension Schema)

**Estado: redactado internamente, NO es una copia del archivo oficial.**

El archivo oficial de la PDF Association
(`https://pdfa.org/download-area/TDMRepSchema-2025_02.xml`) está protegido
por Cloudflare y devuelve HTTP 403 a cualquier descarga automatizada (curl,
PowerShell `Invoke-WebRequest` con user-agent de navegador, y la herramienta
de fetch del propio agente lo confirmaron). Un humano con navegador normal
probablemente sí puede descargarlo.

Mientras tanto, `resources/tdmrep_pdfa_extension_schema.xml` es una
**redacción propia**, siguiendo la estructura estándar de PDF/A Extension
Schema (ISO 19005-2 Annex B / ISO 19005-3 Annex B — el mecanismo
`pdfaExtension:schemas` / `pdfaSchema:*` / `pdfaProperty:*` es público y
está documentado de forma idéntica por múltiples fuentes, no es contenido
propietario de la PDF Association). Declara el namespace TDMRep
(`http://www.w3.org/ns/tdmrep/`, prefijo `tdm`) con sus dos propiedades:
`reservation` (Integer) y `policy` (URI).

**Pendiente:** si se consigue el archivo oficial `TDMRepSchema-2025_02.xml`,
reemplazar `resources/tdmrep_pdfa_extension_schema.xml` por ese contenido
(mismo nombre de archivo esperado por `tdmseal/xmp/pdfa_extension.py`, o
actualizar la ruta en ese módulo) y completar aquí:

- URL de origen: https://pdfa.org/download-area/TDMRepSchema-2025_02.xml
- Fecha de descarga:
- Checksum SHA-256:
- Versión de la plantilla:
- Licencia / condiciones publicadas por la fuente:

## veraPDF

Se instaló para desarrollo en `C:\build_rf\tools\` (fuera del repositorio,
no versionado): JDK Temurin 21 (Eclipse Adoptium) + veraPDF
(`https://software.verapdf.org/releases/verapdf-installer.zip`). **A 19-nov-2026
esa carpeta ya no existe** (equipo nuevo); hay que reinstalarlo para validar
PDF/A de verdad.
El repositorio no asume que veraPDF esté disponible en el entorno de quien
lo use — `validation/verapdf_validator.py` detecta si el binario existe y
degrada a `SKIPPED` si no.

## Especificaciones consultadas (19-nov-2026)

Consultadas en fuente primaria antes de planificar v0.5-v1.0. Si pasa mucho
tiempo antes de implementar una fase, volver a revisarlas.

### TDMRep (W3C Community Group)

- URL: https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/
  (Final Report del 10-may-2024, versión vigente; la página del grupo,
  https://www.w3.org/community/tdmrep/, no lista ninguna posterior).
- `tdmrep.json` (sec. 6.1): arreglo JSON de reglas `location` (patrón con
  `*` y `$`), `tdm-reservation` (1/0) y `tdm-policy` (URL, opcional).
- Cabeceras HTTP (sec. 6.2): `tdm-reservation`, `tdm-policy`; tienen
  prioridad sobre `tdmrep.json`.
- EPUB (sec. 6.4-6.5): EPUB 2 usa `<meta name="tdm:reservation" content="1"/>`;
  EPUB 3 usa `<meta property="tdm:reservation">1</meta>` y exige declarar
  `prefix="tdm: http://www.w3.org/ns/tdmrep#"` en `<package>`.
- XMP (sec. 6.6): namespace `http://www.w3.org/ns/tdmrep/` (con barra, no
  `#` como en EPUB 3).
- ODRL (sec. 7): `@context` = [odrl.jsonld, tdmrep.jsonld], `@type` Offer,
  `profile` http://www.w3.org/ns/tdmrep, `assigner` con vCard, `permission`
  con acción `tdm:mine`; duties `obtainConsent`/`compensate`; restricción
  experimental de `purpose` (`tdm:research` / `tdm:non-research`).
  `obligation` y `prohibition` NO deberían aparecer.

### IETF AIPREF

- Vocabulario: https://datatracker.ietf.org/doc/draft-ietf-aipref-vocab/
  (revisión -08, 14-sep-2026; borrador de grupo de trabajo, no es RFC; el
  propio texto dice que las secciones 3 y 4 aún no tienen consenso).
  Categorías: `train-ai`, `ai-use`, `search`. Sintaxis: diccionario de
  Structured Fields (RFC 9651), p. ej. `train-ai=n, search=y`.
- Adjunto: https://datatracker.ietf.org/doc/draft-ietf-aipref-attach/
  (revisión -05, 19-ago-2026). Define la cabecera HTTP `Content-Usage` y la
  regla `Content-Usage:` en robots.txt. **No define cómo incrustar la
  preferencia en archivos** (sec. 1.3.1).

### ISCC

- iscc-core 1.5.0 (PyPI, requires-python >=3.9): implementación de
  referencia; `gen_text_code_v0(texto)` calcula el Text-Code a partir de
  texto ya extraído. Es la dependencia que ya usa `tdmseal/iscc.py`.
- iscc-sdk 0.9.7 (PyPI, 21-oct-2026, requires-python >=3.11): extrae texto
  de PDF con pypdfium2 (`idk.code_text`). Arrastra muchas dependencias
  (numpy, pillow-heif, exiv2, pytaglib, iscc-tika, pypdfium2, ebookmeta,
  python-docx…). Docs: https://sdk.iscc.codes, https://core.iscc.codes.
