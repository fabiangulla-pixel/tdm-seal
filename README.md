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

## Estado actual (v0.1.0 — núcleo)

Implementado y con pruebas automatizadas:

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
- reporte JSON por archivo procesado;
- CLI: `tdmseal seal`, `tdmseal inspect`, `tdmseal show`, `tdmseal audit`.

**Pendiente** (ver hoja de ruta completa en la especificación, sección 32):

- soporte PDF/A (XMP Extension Schema, detección de conformidad — v0.2.0);
- validación PDF/A con veraPDF (el hook existe en
  `validation/verapdf_validator.py` pero está marcado `SKIPPED`);
- GUI (v0.3.0);
- Policy Builder / ODRL / JSON-LD (v0.4.0);
- XMP Rights, CAWG, señales web (`/.well-known/tdmrep.json`) — fases
  posteriores.

## Instalación

Requiere Python 3.10+. **Importante:** si el proyecto vive en una carpeta
sincronizada con Google Drive (como aquí), crea el entorno virtual **fuera**
de esa carpeta — la sincronización en vivo puede corromper la instalación de
pip a mitad de escritura. Por ejemplo:

```bash
python -m venv "$HOME/.venvs/tdm-seal"
"$HOME/.venvs/tdm-seal/Scripts/python" -m pip install -e ".[dev]"
```

## Uso

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
