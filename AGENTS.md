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

## Qué falta (roadmap, ver spec sección 32)

- **v0.2.0 — PDF/A**: descargar `TDMRepSchema-2025_02.xml` de la PDF
  Association a `resources/` y documentar procedencia/checksum en
  `resources/SOURCES.md`; implementar `xmp/pdfa_extension.py` (merge del
  esquema de extensión para PDF/A-1/2/3, sección 6.2); integrar veraPDF en
  `validation/verapdf_validator.py` (hoy siempre `SKIPPED`).
- **v0.3.0 — GUI**: tkinter o PySide6 sobre el mismo núcleo (`seal.py`),
  siguiendo el mockup de la sección 12 de la especificación.
- **v0.4.0 — Policy Builder**: generación de `policy.jsonld` (ODRL),
  `policy.html`, `tdmrep.json` (secciones 26-27).
- Fixtures de integración con PDF/A-1/2/3/4, PDF/UA, firmados, cifrados,
  con adjuntos y formularios reales (hoy los tests usan PDFs mínimos
  generados con pikepdf; faltan los fixtures reales de la sección 19).
