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

## Plantilla de texto (revisada el 21-nov-2026; falta el visto bueno del editor)

Vive en un solo lugar: `src/tdmseal/notice.py` (constantes `NOTICE_*`).
Variables: `{editorial}`, `{contacto}` (correo de derechos o sitio web),
`{politica}` (URL de la política; la línea se omite si no hay).

**Título:** Reserva de derechos: minería de textos y datos e inteligencia
artificial

> {editorial} se reserva expresamente el derecho a autorizar la minería de
> textos y datos sobre esta obra, incluido su uso para entrenar sistemas de
> inteligencia artificial o para que estos la consulten al generar
> respuestas, conforme a la legislación aplicable. La reserva no excluye esos
> usos: quien desee emplear la obra con tales fines puede solicitar una
> licencia a {contacto}.
>
> Esta reserva consta también en los metadatos del archivo, en un formato
> legible por máquina (protocolo TDMRep del W3C).
>
> Condiciones de licencia: {politica}

**Title:** Rights reservation: text and data mining and artificial
intelligence

> {editorial} expressly reserves the right to authorize text and data mining
> of this work, including its use to train artificial intelligence systems or
> as a source they consult when generating answers, as permitted by
> applicable law. The reservation does not rule out such uses: anyone wishing
> to use the work for these purposes may request a license from {contacto}.
>
> This reservation is also stated in the file's metadata in machine-readable
> form (W3C TDMRep protocol).
>
> Licensing terms: {politica}

Cambios de la revisión y por qué:
- **"se reserva expresamente el derecho a autorizar"** (antes "reserva los
  derechos"): fórmula jurídica usual en español y eco del requisito de
  reserva *expresa* del art. 4.3 de la Directiva (UE) 2019/790.
- **"o para que estos la consulten al generar respuestas"** (antes
  "alimentar", vago): cubre de forma explícita la consulta en el momento de
  responder (RAG), no solo el entrenamiento.
- **"La reserva no excluye esos usos: quien desee…"** (antes "no es una
  negativa definitiva: si desea…"): más natural, e impersonal, para no
  elegir entre tú y usted ante un lector desconocido.
- **Frase nueva sobre los metadatos legibles por máquina**: la ley pide la
  reserva "por medios adecuados, como los de lectura mecánica"; la página
  remite a esa declaración, que es la que leen los rastreadores.
- "conforme a la legislación aplicable" se mantiene: el catálogo puede
  circular en varias jurisdicciones (Directiva UE 2019/790, Decisión Andina
  351…). Si se prefiere citar una norma, se cambia en esa frase.
- La política HTML (`tdmseal policy build`) usa las mismas fórmulas.

## Composición en la página

El cuerpo empieza en 10,5 pt y baja hasta 7 pt si hace falta para que el
aviso quepa (A4, A5, 6×9 in y formato de bolsillo caben con los dos
idiomas). En una página más pequeña se deja solo el español y se advierte.
La URL de la política va en línea propia y solo se corta tras una barra.
