# Namespace XMP de TDM Seal para ISCC

- **URI:** `https://github.com/fabiangulla-pixel/tdm-seal/ns/iscc/1.0/`
- **Prefijo:** `tdmseal`
- **Dónde:** XMP de nivel de documento del PDF (`/Root /Metadata`), en un
  `rdf:Description rdf:about=""`.
- **PDF/A-1/2/3:** se declara en `pdfaExtension:schemas` con la plantilla
  `resources/tdmseal_iscc_pdfa_extension_schema.xml`.

## Por qué un namespace propio

Ni TDMRep ni la especificación ISCC (ISO 24138) definen dónde guardar un ISCC
en el XMP de un PDF. iscc-sdk (v0.9.7) solo escribe metadatos descriptivos en
claves `/iscc_*` del diccionario Info, no el código. Antes de usar uno propio
se comprobó que no existía uno estándar (19-nov-2026).

## Propiedades

| Propiedad | Tipo | Contenido |
|---|---|---|
| `tdmseal:isccContentCode` | Text | Text-Code (Content-Code de texto) calculado sobre el texto del documento. **No cambia al sellar.** |
| `tdmseal:isccSource` | Text | ISCC-CODE completo (Meta + Text + Data + Instance) del archivo **antes** de sellar. |
| `tdmseal:isccSourceDatahash` | Text | Hash BLAKE3 (multihash, hex) del archivo antes de sellar. |

Ejemplo:

```xml
<rdf:Description rdf:about=""
    xmlns:tdmseal="https://github.com/fabiangulla-pixel/tdm-seal/ns/iscc/1.0/">
  <tdmseal:isccContentCode>ISCC:EAATKCI547UG6QIL</tdmseal:isccContentCode>
  <tdmseal:isccSource>ISCC:KAC2B62QYNYJXSH7GUER3Z7IN5AQWAHRQIJA744FDPTHPCM3CQVZ6WA</tdmseal:isccSource>
  <tdmseal:isccSourceDatahash>1e20…</tdmseal:isccSourceDatahash>
</rdf:Description>
```

## Por qué no se escribe el ISCC del archivo sellado

El Data-Code y el Instance-Code son huellas de los bytes. Escribir el ISCC
del archivo sellado dentro de él cambiaría sus bytes y, con ellos, el propio
código. Por eso se guarda el del original y el Text-Code, que es estable. El
ISCC completo del archivo sellado va en el reporte JSON (`iscc.output`).

## Qué cambia y qué no al sellar

| Unidad | ¿Cambia al sellar? | Por qué |
|---|---|---|
| Text-Code | No | Se calcula sobre el texto; TDM Seal no toca las páginas. |
| Meta-Code | No, si el PDF tiene título | Se calcula sobre título y descripción, que no se tocan. **Si el PDF no tiene título**, iscc-sdk usa el nombre del archivo, y el sufijo `_TDM` lo cambia. |
| Data-Code | Sí | Huella de similitud de los bytes. |
| Instance-Code | Sí | Hash exacto de los bytes. |

## Re-sellado

Si un archivo ya sellado se vuelve a sellar y su Text-Code coincide con el
declarado, `isccSource` e `isccSourceDatahash` no se sobrescriben: siguen
apuntando al original de la primera vez.

## Compatibilidad

`tdmseal iscc` produce el mismo ISCC-CODE que `iscc_sdk.code_iscc` (v0.9.7)
para PDF: se comprobó con fixtures sintéticos y con PDF reales
(`tests/unit/test_iscc_content.py`, prueba opcional contra el SDK real con
`TDMSEAL_ISCC_SDK_PY` o `%USERPROFILE%\.venvs\iscc-sdk-ref`).

Única diferencia deliberada: en un PDF sin capa de texto, el SDK calcula el
Text-Code de un texto vacío (el mismo para todos los escaneos sin OCR); TDM
Seal lo omite y avisa.
