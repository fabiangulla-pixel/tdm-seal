# TDM Seal

> Reserva de derechos de minería de textos y datos (TDM) para PDF y EPUB
> editoriales: dentro del archivo, ligada al contenido, en el sitio web y
> como oferta de licencia. Gratis, de código abierto (MIT) y sin conexión
> (lo que usa internet es opcional y nunca envía los libros).

TDM Seal declara que una editorial **reserva sus derechos de minería de
textos y datos**, incluido el entrenamiento de inteligencia artificial, por
todas las vías que hoy existen, y genera la política con la que invita a
licenciar. **No es DRM ni un bloqueo técnico:** es una señal declarativa,
legible por máquinas y por personas.

**Versión 1.4.0.** Guía rápida para editoriales:
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
| **Distribución** | Restricción TDM en el ONIX que la editorial ya envía a librerías (o un ONIX mínimo nuevo) | ONIX 3.0, lista 145 código 11 |
| **Prueba de fecha** | Sello de tiempo de una autoridad externa sobre el manifiesto (solo viaja la huella) | RFC 3161 |
| **Registro público** | Sitio estático con una ficha por obra (JSON-LD, TDMRep), alojado por la editorial | schema.org, TDMRep |
| **Red ISCC** | Declaración directa en un hub ISCC con identidad propia `did:web`, sin intermediarios | ISO 24138, ISCC-SIG |
| **Vigilancia** | ¿Este archivo es mío? Copias renombradas o sin metadatos, extractos y libros dentro de volcados de texto (conjuntos de entrenamiento) | ISCC + huellas por fragmentos |

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

Comparado con los servicios comerciales de registro TDM con ISCC (p. ej.
Signal / S-PLIA de Hipertexto-Netizen, según lo que publican en
noviembre de 2026):

| | TDM Seal | Servicio comercial de registro |
|---|---|---|
| Reserva TDMRep **dentro del archivo** (PDF, EPUB) | Sí, con conservación verificada (píxeles, PDF/A, PDF/UA, firmas, cifrado) | No lo detallan |
| ISCC | Completo, calculado sobre el contenido; idéntico a iscc-sdk | En la ficha pública, un código sobre los metadatos; el del archivo en niveles superiores |
| Señales del sitio (`tdmrep.json`, cabeceras, robots.txt, metaetiquetas) | Sí | Sí |
| Restricción TDM en ONIX | Sí (añadirla a su ONIX o crearlo); valida contra el XSD oficial | Sí |
| Sello de tiempo RFC 3161 | Sí, opcional (solo viaja la huella) | Sí |
| Registro público consultable | Sí, alojado por la editorial (sin cuota) | Sí, alojado por el proveedor |
| Declaración en la red de hubs ISCC | Sí, directa, con identidad propia `did:web`, en el hub que elija | Sí, a través de su hub |
| Reconocer copias, extractos y libros en volcados de texto | Sí, sin conexión | No lo ofrecen |
| Política de licencia legible por máquinas | Sí (ODRL) | Declaración de licencia voluntaria |
| Privacidad | Los libros nunca salen del equipo | Se suben para analizarlos |
| Coste | Gratis, MIT | De pago (sin tarifas públicas) |

**Lo que ninguna herramienta reemplaza:** el respaldo jurídico de la
reserva en cada jurisdicción, la gestión colectiva de derechos, la
negociación y el cobro de licencias, y el seguimiento de quién usa las
obras. Eso sigue siendo trabajo humano e institucional (editoriales,
asociaciones, sociedades de gestión, abogados). Tampoco una red de
adopción: un proveedor con cientos de editoriales tiene un peso colectivo
que un programa no da.

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

**Validadores (opcionales, recomendados):** veraPDF comprueba que los
PDF/A y los PDF/UA sigan conformes tras sellar y EPUBCheck que los EPUB
sigan válidos.
Para instalarlos con Java, sin permisos de administrador:

```bash
powershell -ExecutionPolicy Bypass -File scripts\instalar_herramientas.ps1
tdmseal tools        # qué encontró
```

**¿Funciona todo?** `tdmseal selftest`, o `TDM-Seal.exe --autoprueba
informe.json` con el ejecutable: sella un PDF y un EPUB de ejemplo y recorre
todas las vías sin tocar sus archivos.

## GUI

Doble clic en `TDM-Seal.exe` o en `TDM-Seal.bat`. Seis pestañas:

1. **Sellar**: datos de la editorial, reserva, archivos PDF/EPUB, ISCC y
   aviso visible (pide confirmación).
2. **Política**: condiciones de licencia por finalidad, preferencias de IA y
   vista previa de la página de la política.
3. **Sitio web**: archivos para publicar en el servidor.
4. **Catálogo**: manifiesto (JSON o CSV), sello de tiempo, registro público
   y ONIX.
5. **Buscar copias**: ¿este archivo o volcado de texto contiene uno de mis
   libros?
6. **Red ISCC**: identidad de la editorial y declaración en un hub ISCC
   (por defecto en la red de pruebas).

Solo el sello de tiempo y la red ISCC usan internet, y antes de hacerlo
piden confirmación y dicen qué se envía (nunca los libros).

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

# ONIX 3.0: añadir la reserva al ONIX existente, o crear uno
tdmseal onix add catalogo_onix.xml          # deja catalogo_onix_TDM.xml
tdmseal onix build ./catalogo --out onix.xml

# Prueba de fecha (USA LA RED: envía solo la huella SHA-256) y verificación local
tdmseal timestamp create catalogo_tdm.json --tsa freetsa
tdmseal timestamp verify catalogo_tdm.json --ca freetsa-cacert.pem

# Registro público (sitio estático para publicar donde quiera)
tdmseal registry catalogo_tdm.json --out ./registro --base-url https://editorial.ejemplo/registro/

# ¿Este archivo es uno de mis libros? (PDF, EPUB, .txt, .jsonl…)
tdmseal match descarga_sospechosa.pdf --catalog catalogo_tdm.json
tdmseal match dataset.jsonl --catalog catalogo_tdm.json

# Red de hubs ISCC (USA LA RED al declarar)
tdmseal iscc-hub keygen --domain editorial.ejemplo   # publique did.json en /.well-known/
tdmseal iscc-hub prepare libro_TDM.pdf               # firma sin enviar, para revisar
tdmseal iscc-hub declare libro_TDM.pdf --hub 1 --network testnet

# Auditar sin modificar
tdmseal inspect libro_TDM.pdf
tdmseal show libro_TDM.epub
tdmseal audit ./catalogo --recursive

# Valores por defecto (editorial, reserva, política, AIPREF)
tdmseal config show
tdmseal config set --publisher-name "Editorial" --aipref "train-ai=n, ai-use=n, search=y"
```

Códigos de omisión o error frecuentes: `TDM020` cifrado, `TDM021` firmado,
`TDM022` EPUB con DRM, `TDM023` aviso visible no aplicable, `TDM050` ya
sellado (existe la salida; se omite sin sobrescribir). Al recorrer una
carpeta se ignoran los `*_TDM.*`, así que se puede volver a sellar la misma
carpeta tras añadir libros nuevos.

**PDF firmados:** por defecto se omiten (`TDM021`); lo ideal es sellar
*antes* de firmar. Si ya están firmados, `--force-signed` (en la GUI,
"Sellar también PDF ya firmados") añade el sello como **actualización
incremental**: los bytes firmados no cambian y la firma sigue siendo válida
(comprobado con firmas reales, de aprobación y de certificación, y con un
PDF/A-2b firmado que sigue conforme). Algunos lectores indicarán que hubo
cambios después de firmar (solo metadatos). Un campo de firma vacío no
impide sellar.

## Limitaciones conocidas

- AIPREF es un borrador del IETF y no define cómo incrustarlo en archivos:
  va en el sitio web y en los reportes.
- En un PDF sin título, el Meta-Code se deriva del nombre del archivo (como
  en iscc-sdk) y cambia con el sufijo `_TDM`; el Text-Code no. Los PDF
  escaneados sin OCR no tienen Text-Code.
- El esquema de extensión PDF/A de TDMRep es una redacción propia (el
  archivo oficial de la PDF Association no se pudo descargar); veraPDF
  confirma que PDF/A-1b, 2b y 3b y PDF/UA-1 reales siguen conformes tras
  sellar.
- La firma del manifiesto prueba quién firmó, no cuándo; para el cuándo,
  `tdmseal timestamp`.
- La búsqueda de copias reconoce el mismo texto, no paráfrasis ni
  traducciones; en volcados enormes conviene partir el archivo (se lee
  entero en memoria).
- La declaración en la red ISCC se probó contra las reglas del validador
  oficial del hub y contra iscc-crypto, no todavía contra un hub en vivo
  (requiere publicar `did.json` en un dominio de la editorial).

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
registries and collective licensing. Since 1.4 it also adds the TDM
restriction to ONIX 3.0 feeds, obtains RFC 3161 timestamps (only the hash
leaves the computer), builds a self-hosted public registry, declares works
directly on the federated ISCC hub network with the publisher's own
`did:web` identity, and recognises copies, excerpts and books inside text
dumps such as training datasets. It never overwrites originals, skips
signed, encrypted or DRM-protected files, preserves PDF/A, and validates
everything it writes. It does not replace legal advice, collective rights
management or licence negotiation.
