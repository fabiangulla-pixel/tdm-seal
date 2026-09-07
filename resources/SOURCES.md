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

Instalado localmente para desarrollo/pruebas en `C:\build_rf\tools\` (fuera
del repositorio, no versionado): JDK Temurin 21 (Eclipse Adoptium) +
veraPDF (`https://software.verapdf.org/releases/verapdf-installer.zip`).
El repositorio no asume que veraPDF esté disponible en el entorno de quien
lo use — `validation/verapdf_validator.py` detecta si el binario existe y
degrada a `SKIPPED` si no.
