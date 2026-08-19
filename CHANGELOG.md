# Changelog

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
