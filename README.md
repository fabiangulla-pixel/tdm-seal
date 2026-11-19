# TDM Seal

> Reserva de derechos de minería de textos y datos (TDM) para PDF y EPUB
> editoriales: dentro del archivo, ligada al contenido, en el sitio web y
> como oferta de licencia. Gratis, de código abierto (MIT) y sin conexión.

TDM Seal declara que una editorial **reserva sus derechos de minería de
textos y datos**, incluido el entrenamiento de inteligencia artificial, por
todas las vías que hoy existen, y genera la política con la que invita a
licenciar. **No es DRM ni un bloqueo técnico:** es una señal declarativa,
legible por máquinas y por personas.

**Versión 1.0.0.** Guía rápida para editoriales:
[Cómo reservar su catálogo frente al entrenamiento de IA en 10 minutos](docs/guia-10-minutos.md).

## Qué hace

| Vía | Cómo | Estándar |
|---|---|---|
| **Dentro del archivo** | `tdm:reservation` / `tdm:policy` en el XMP del PDF o en el OPF del EPUB, sin tocar páginas, fuentes, imágenes ni el resto de metadatos | W3C TDMRep (2024) |
| **Ligada al contenido** | ISCC-CODE (Meta + Text + Data + Instance), idéntico al de iscc-sdk; el Text-Code **no cambia al sellar** y se guarda en el archivo | ISO 24138 (ISCC) |
| **Sitio web** | `/.well-known/tdmrep.json`, cabeceras HTTP para Apache y Nginx, robots.txt y metaetiquetas HTML | TDMRep, IETF AIPREF |
| **Oferta de licencia** | `policy.jsonld` y `policy.html`, con condiciones distintas para investigación y otros fines | ODRL 2.2, perfil TDMRep |
| **Usos de IA en detalle** | `train-ai`, `ai-use`, `search` (por defecto: entrenar y usar IA, reservado; búsqueda, permitida) | IETF AIPREF (borrador) |
| **Visible para personas** | Opcional y desactivado por defecto: página final (PDF) o documento final (EPUB) con el aviso en español e inglés | IPTC, buenas prácticas |
| **Catálogo** | Manifiesto CSV/JSON por obra (hashes, ISCC, ISBN, reserva, política), con firma opcional | Para registros ISCC y licencias en bloque |

Y en todo momento:

- nunca sobrescribe el original (guarda `archivo_TDM.pdf` / `.epub`);
- omite por defecto los PDF firmados o cifrados y los EPUB con DRM;
- mantiene PDF/A (declara los esquemas de extensión) y no rompe PDF/UA;
- relee y valida lo que escribe: TDMRep, invariantes de páginas, diccionario
  Info (incluido el heredado de actualizaciones incrementales), contenedor
  EPUB, estabilidad del ISCC y, si están instalados, veraPDF y EPUBCheck;
- es idempotente: sellar dos veces no duplica nada;
- deja un reporte JSON por archivo con todo lo que hizo.

## Qué cubre y qué no (comparación honesta)

| | TDM Seal | Servicios comerciales tipo TDM·AI / registro ISCC |
|---|---|---|
| Reserva TDMRep dentro del archivo | Sí (PDF, EPUB) | Según el servicio |
| Huella ISCC ligada al contenido | Sí, compatible con iscc-sdk | Sí |
| Declaración en un **registro público** consultable por terceros | No: genera el manifiesto para cargarlo donde se decida | Sí, es su núcleo |
| Señales del sitio web (`tdmrep.json`, cabeceras, robots.txt) | Sí | Según el servicio |
| Política de licencia legible por máquinas | Sí (ODRL) | Según el servicio |
| Sello de tiempo verificable por terceros | No (requiere red; la firma SSH prueba quién, no cuándo) | Normalmente sí |
| Funciona sin conexión y sin enviar los libros a nadie | Sí | Requiere conexión con el registro |
| Coste | Gratis, MIT | Licencia comercial |

**Lo que ninguna herramienta reemplaza:** el respaldo jurídico de la
reserva en cada jurisdicción, la gestión colectiva de derechos, la
negociación y el cobro de licencias, y el seguimiento de quién usa las
obras. Eso sigue siendo trabajo humano e institucional (editoriales,
sociedades de gestión como CDR, abogados).

## Instalación

**Sin Python:** use `TDM-Seal.exe` (carpeta padre del repositorio o `dist/`),
o el instalador que genera `scripts/installer.iss` con Inno Setup.

**Con Python 3.10+** (en Windows, cree el entorno virtual **fuera** de
carpetas sincronizadas con Google Drive u OneDrive):

```bash
python -m venv "%USERPROFILE%\.venvs\tdm-seal"
"%USERPROFILE%\.venvs\tdm-seal\Scripts\python" -m pip install -e ".[gui,iscc]"
```

Extras opcionales: `gui` (PySide6), `iscc` (Text-Code de PDF, pypdfium2),
`iscc-epub` (Text-Code de EPUB, iscc-tika, ~110 MB), `dev` (pruebas).
Validadores externos opcionales: veraPDF (`verapdf` en el PATH) y EPUBCheck
(`TDMSEAL_EPUBCHECK_JAR`), ambos requieren Java.

## GUI

Doble clic en `TDM-Seal.exe` o en `TDM-Seal.bat`. Cuatro pestañas:

1. **Sellar**: datos de la editorial, reserva, archivos PDF/EPUB, ISCC y
   aviso visible (pide confirmación).
2. **Política**: condiciones de licencia por finalidad, preferencias de IA y
   vista previa de la página de la política.
3. **Sitio web**: archivos para publicar en el servidor.
4. **Catálogo**: manifiesto CSV/JSON.

## Línea de comandos

```bash
# Sellar (reserva por defecto = 1), con ISCC
tdmseal seal libro.pdf --iscc
tdmseal seal ./catalogo --recursive --iscc --policy https://editorial.ejemplo/tdm/policies/1

# Aviso visible opcional (página final en PDF, documento final en EPUB)
tdmseal seal libro.pdf --visible-notice --publisher-name "Editorial" --publisher-email derechos@editorial.ejemplo

# ISCC sin modificar nada
tdmseal iscc ./catalogo --recursive --json

# Política de licencia (ODRL + página HTML)
tdmseal policy build --output-dir ./publicar --publisher-name "Editorial" \
  --publisher-website https://editorial.ejemplo --publisher-email derechos@editorial.ejemplo \
  --research consent --non-research compensate
tdmseal policy check ./publicar/policy.jsonld

# Señales del sitio web
tdmseal site --base-url https://editorial.ejemplo/ --out ./publicar \
  --policy https://editorial.ejemplo/tdm/policies/1 --aipref "train-ai=n, ai-use=n, search=y"
tdmseal site --check ./publicar/.well-known/tdmrep.json

# Manifiesto del catálogo (firma opcional con clave SSH)
tdmseal manifest ./catalogo --recursive --out catalogo_tdm.csv
tdmseal manifest ./catalogo --out catalogo_tdm.json --sign-key ~/.ssh/id_ed25519

# Auditar sin modificar
tdmseal inspect libro_TDM.pdf
tdmseal show libro_TDM.epub
tdmseal audit ./catalogo --recursive

# Valores por defecto (editorial, reserva, política, AIPREF)
tdmseal config show
tdmseal config set --publisher-name "Editorial" --aipref "train-ai=n, ai-use=n, search=y"
```

Códigos de omisión o error frecuentes: `TDM020` cifrado, `TDM021` firmado,
`TDM022` EPUB con DRM, `TDM023` aviso visible no aplicable, `TDM050` la
salida ya existe.

## Limitaciones conocidas

- AIPREF es un borrador del IETF y no define cómo incrustarlo en archivos:
  va en el sitio web y en los reportes.
- En un PDF sin título, el Meta-Code se deriva del nombre del archivo (como
  en iscc-sdk) y cambia con el sufijo `_TDM`; el Text-Code no. Los PDF
  escaneados sin OCR no tienen Text-Code.
- El esquema de extensión PDF/A de TDMRep es una redacción propia (el
  archivo oficial de la PDF Association no se pudo descargar).
- La firma del manifiesto prueba quién firmó, no cuándo.
- El texto del aviso visible está pendiente de revisión de estilo
  (`docs/aviso-visible.md`).

## Desarrollo

```bash
set TDMSEAL_PY=%USERPROFILE%\.venvs\tdm-seal\Scripts\python.exe
check.bat                  # ruff + formato + pytest
scripts\build_exe.bat      # TDM-Seal.exe (compila fuera de Drive)
```

Las pruebas generan sus PDF y EPUB por programa; no se versionan binarios.
Fuentes de los estándares consultados: `resources/SOURCES.md`.

## Principios

1. No tocar el contenido visible (salvo el aviso opcional, que solo añade).
2. No borrar metadatos que no pertenezcan a TDM Seal.
3. No romper PDF/A ni PDF/UA.
4. No modificar archivos firmados ni con DRM.
5. No subir archivos a servicios externos.
6. No afirmar que TDMRep bloquea técnicamente la IA.
7. Registrar exactamente qué se modificó.
8. Ser idempotente.
9. Permitir verificar la declaración sin depender del propio programa.

---

## Summary in English

**TDM Seal** is a free, open-source (MIT), offline tool that lets publishers
reserve their text and data mining rights, including AI training, over PDF
and EPUB catalogues through every available channel: W3C TDMRep metadata
inside each file (XMP / OPF), an ISO 24138 ISCC content fingerprint that
survives sealing (compatible with iscc-sdk), site-level signals
(`/.well-known/tdmrep.json`, HTTP headers, robots.txt, IETF AIPREF
`Content-Usage`), an ODRL licensing offer with a human-readable policy page,
an optional visible notice, and a signed catalogue manifest for ISCC
registries and collective licensing. It never overwrites originals, skips
signed, encrypted or DRM-protected files, preserves PDF/A, and validates
everything it writes. It does not replace legal advice, collective rights
management or licence negotiation.
