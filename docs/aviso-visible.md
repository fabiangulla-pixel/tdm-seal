# Aviso visible (opcional)

**Desactivado por defecto.** Se activa con `tdmseal seal --visible-notice` o
con la casilla de la GUI, que pide confirmación explícita.

## Qué hace

- **PDF:** añade **una página final** del mismo tamaño que la última, con el
  aviso en español y en inglés. Las páginas existentes no se modifican (una
  prueba compara sus flujos de contenido byte a byte). Se marca en el XMP
  (`tdmseal:visibleNotice` = número de página) para no añadirla dos veces.
- **EPUB:** añade `tdmseal-aviso.xhtml` junto al OPF, al manifiesto y al
  **final del spine**. Los demás documentos no se modifican (mismo CRC).

## Cuándo se rechaza (código `TDM023`, el archivo no se toca)

| Caso | Motivo |
|---|---|
| PDF firmado (aun con `--force-signed`) | Añadir una página invalida la firma. |
| PDF/A-1/2/3/4 | La página usa Helvetica estándar, no incrustada. |
| PDF/UA | Exige fuentes incrustadas y contenido etiquetado. |
| EPUB de maquetación fija | Una página fluida rompería la presentación. |

En un PDF etiquetado que no es PDF/UA, la página se marca como *Artifact*
para no alterar el árbol de estructura; se avisa de que los lectores de
pantalla pueden omitirla.

## ISCC

El aviso añade texto, así que el Text-Code del archivo sellado cambia a
propósito. El XMP u OPF declara el Text-Code de la **obra original**, que es
el que identifica la obra; la validación `iscc_content_stable` queda
`SKIPPED` con una explicación.

## Plantilla de texto — PENDIENTE DE REVISIÓN DE ESTILO

Vive en un solo lugar: `src/tdmseal/notice.py` (constantes `NOTICE_*`).
Variables: `{editorial}`, `{contacto}` (correo de derechos o sitio web),
`{politica}` (URL de la política; la línea se omite si no hay).

**Título:** Reserva de derechos de minería de textos y datos

> {editorial} reserva los derechos de minería de textos y datos sobre esta
> obra, incluido su uso para entrenar o alimentar sistemas de inteligencia
> artificial, conforme a la legislación aplicable. Esta reserva no es una
> negativa definitiva: si desea usar la obra con esos fines, puede solicitar
> una licencia a {contacto}.
>
> Condiciones de licencia: {politica}

**Title:** Text and data mining rights reserved

> {editorial} reserves its text and data mining rights over this work,
> including its use to train or feed artificial intelligence systems. This
> is an invitation to license, not a final refusal: to request a license,
> contact {contacto}.
>
> Licensing terms: {politica}

Notas para la revisión:
- "conforme a la legislación aplicable" evita citar una norma concreta
  (Directiva UE 2019/790, Decisión Andina 351, etc.), porque el catálogo
  puede circular en varias jurisdicciones. Si se prefiere citar una, se
  cambia en esa frase.
- El texto en inglés es una traducción funcional, no literal.
