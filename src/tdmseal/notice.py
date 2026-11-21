"""Aviso visible opcional (desactivado por defecto).

Contradice a propósito el principio 1 ("no tocar el contenido visible"), por
eso solo se activa con `--visible-notice` o con confirmación explícita en la
GUI, y **nunca modifica páginas existentes**: añade una página final (PDF) o
un documento XHTML al final del spine (EPUB).

Se rechaza (código TDM023) cuando añadir contenido rompería algo:
- PDF firmado (invalidaría la firma);
- PDF/A (la página usa una fuente estándar no incrustada);
- PDF/UA (exige fuentes incrustadas y contenido etiquetado);
- EPUB de maquetación fija (una página fluida rompería la presentación).

En PDF etiquetados (no PDF/UA) la página se marca como *Artifact* para no
alterar el árbol de estructura; se avisa de que los lectores de pantalla
pueden omitirla.

PLANTILLA DE TEXTO: revisada y aprobada por el editor el 21-nov-2026 (ver
docs/aviso-visible.md). Se mantiene en este único lugar para que cualquier
cambio sea una sola constante.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from html import escape

NOTICE_TITLE_ES = "Reserva de derechos: minería de textos y datos e inteligencia artificial"
NOTICE_TITLE_EN = "Rights reservation: text and data mining and artificial intelligence"

NOTICE_ES = (
    "{editorial} se reserva expresamente el derecho a autorizar la minería de textos y "
    "datos sobre esta obra, incluido su uso para entrenar sistemas de inteligencia "
    "artificial o para que estos la consulten al generar respuestas, conforme a la "
    "legislación aplicable. La reserva no excluye esos usos: quien desee emplear la obra "
    "con tales fines puede solicitar una licencia a {contacto}."
)
NOTICE_MACHINE_ES = (
    "Esta reserva consta también en los metadatos del archivo, en un formato legible por "
    "máquina (protocolo TDMRep del W3C)."
)
NOTICE_POLICY_ES = "Condiciones de licencia: {politica}"
NOTICE_EN = (
    "{editorial} expressly reserves the right to authorize text and data mining of this "
    "work, including its use to train artificial intelligence systems or as a source they "
    "consult when generating answers, as permitted by applicable law. The reservation does "
    "not rule out such uses: anyone wishing to use the work for these purposes may request "
    "a license from {contacto}."
)
NOTICE_MACHINE_EN = (
    "This reservation is also stated in the file's metadata in machine-readable form "
    "(W3C TDMRep protocol)."
)
NOTICE_POLICY_EN = "Licensing terms: {politica}"

NOTICE_MARKER = "tdmseal-aviso"  # id del ítem del manifiesto EPUB
NOTICE_FILE = "tdmseal-aviso.xhtml"  # junto al OPF


@dataclass(frozen=True)
class NoticeOptions:
    editorial: str
    contact: str  # correo o URL
    policy_url: str | None = None
    include_english: bool = True

    def paragraphs(self) -> list[tuple[str, list[str]]]:
        """[(título, [párrafos])] en español y, si se pide, en inglés."""
        values = {"editorial": self.editorial, "contacto": self.contact}
        es = [NOTICE_ES.format(**values), NOTICE_MACHINE_ES]
        en = [NOTICE_EN.format(**values), NOTICE_MACHINE_EN]
        if self.policy_url:
            es.append(NOTICE_POLICY_ES.format(politica=self.policy_url))
            en.append(NOTICE_POLICY_EN.format(politica=self.policy_url))
        blocks = [(NOTICE_TITLE_ES, es)]
        if self.include_english:
            blocks.append((NOTICE_TITLE_EN, en))
        return blocks


def notice_from_publisher(publisher, policy_url: str | None) -> NoticeOptions:
    """Arma el aviso con los datos de la editorial. ValueError si faltan."""
    if not publisher or not publisher.name:
        raise ValueError("El aviso visible necesita el nombre de la editorial.")
    contact = publisher.rights_email or publisher.website
    if not contact:
        raise ValueError("El aviso visible necesita un correo de derechos o un sitio web.")
    return NoticeOptions(editorial=publisher.name, contact=contact, policy_url=policy_url)


# ---- Marca de idempotencia en el XMP del PDF --------------------------------------


def _notice_tag() -> str:
    from tdmseal.iscc.xmp import ISCC_XMP_NS

    return f"{{{ISCC_XMP_NS}}}visibleNotice"


def pdf_has_notice_marker(rdf_root) -> bool:
    from tdmseal.xmp.parser import get_simple_property_text, iter_descriptions

    tag = _notice_tag()
    return any(get_simple_property_text(d, tag) for d in iter_descriptions(rdf_root))


def write_pdf_notice_marker(rdf_root, page_number: int) -> None:
    """`tdmseal:visibleNotice` = número de la página de aviso (evita añadirla dos veces)."""
    from lxml import etree

    from tdmseal.iscc.xmp import ISCC_XMP_NS, ISCC_XMP_PREFIX
    from tdmseal.xmp.parser import RDF_NS

    desc = etree.SubElement(
        rdf_root,
        f"{{{RDF_NS}}}Description",
        nsmap={"rdf": RDF_NS, ISCC_XMP_PREFIX: ISCC_XMP_NS},
    )
    desc.set(f"{{{RDF_NS}}}about", "")
    etree.SubElement(desc, _notice_tag()).text = str(page_number)


def pdf_notice_rejection(info) -> str | None:
    """Motivo por el que no se puede añadir la página de aviso, o None."""
    if info.signed:
        return "el PDF está firmado: añadir una página invalidaría la firma"
    if info.pdfa_part is not None:
        return "el PDF es PDF/A: la página de aviso usa una fuente no incrustada"
    if info.pdfua_part is not None:
        return "el PDF es PDF/UA: exige fuentes incrustadas y contenido etiquetado"
    return None


def add_pdf_notice_page(pdf, options: NoticeOptions) -> list[str]:
    """Añade la página de aviso al final, del tamaño de la última. Devuelve avisos."""
    import pikepdf

    warnings = []
    last = pdf.pages[-1]
    box = [float(v) for v in last.MediaBox]
    width, height = box[2] - box[0], box[3] - box[1]
    tagged = "/StructTreeRoot" in pdf.Root
    if tagged:
        warnings.append(
            "El PDF está etiquetado: la página de aviso se marcó como Artifact para no "
            "alterar su estructura; los lectores de pantalla pueden omitirla."
        )

    def font(name: str):
        return pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name("/Font"),
                Subtype=pikepdf.Name("/Type1"),
                BaseFont=pikepdf.Name(name),
                Encoding=pikepdf.Name("/WinAnsiEncoding"),
            )
        )

    if layout_pdf_notice(options, width, height)[4]:
        warnings.append(
            "La página es pequeña: el aviso visible se puso solo en español (el texto en "
            "inglés no cabía)."
        )

    page = pdf.add_blank_page(page_size=(width, height))
    page.obj["/Resources"] = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(F1=font("/Helvetica"), F2=font("/Helvetica-Bold"))
    )
    page.obj["/Contents"] = pdf.make_stream(
        build_pdf_notice_stream(options, width, height, as_artifact=tagged)
    )
    return warnings


# ---- PDF ------------------------------------------------------------------------


def _pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _wrap_url(url: str, width: int) -> list[str]:
    """Parte una URL solo tras «/» (nunca en guiones ni a mitad de palabra si se puede)."""
    lines, current = [], ""
    for part in re.split(r"(?<=/)", url):
        while len(part) > width:  # segmento más largo que la línea: corte duro inevitable
            if current:
                lines.append(current)
                current = ""
            lines.append(part[:width])
            part = part[width:]
        if len(current) + len(part) > width:
            lines.append(current)
            current = part
        else:
            current += part
    if current:
        lines.append(current)
    return lines


def _wrap_blocks(blocks, size: float, text_width: float) -> list[tuple[str, bool]]:
    # Anchos medios de Helvetica (~0,5 em) y Helvetica-Bold (~0,58 em, título 1,5 pt mayor).
    chars_per_line = max(20, int(text_width / (size * 0.5)))
    title_chars = max(16, int(text_width / ((size + 1.5) * 0.58)))
    lines: list[tuple[str, bool]] = []
    for title, paragraphs in blocks:
        lines.extend((ln, True) for ln in textwrap.wrap(title, title_chars))
        lines.append(("", False))
        for paragraph in paragraphs:
            label, sep, url = paragraph.partition(": http")
            if sep:  # «Condiciones de licencia: URL» -> etiqueta y URL en líneas propias
                lines.append((label + ":", False))
                lines.extend((ln, False) for ln in _wrap_url("http" + url, chars_per_line))
            else:
                lines.extend((ln, False) for ln in textwrap.wrap(paragraph, chars_per_line))
            lines.append(("", False))
        lines.append(("", False))
    while lines and not lines[-1][0]:
        lines.pop()
    return lines


def layout_pdf_notice(options: NoticeOptions, width: float, height: float):
    """Elige margen y cuerpo para que el aviso quepa en la página.

    Devuelve (margen, cuerpo, interlineado, líneas, se_omitió_el_inglés). Prueba
    de 10,5 pt hacia abajo hasta 7 pt; si ni así cabe (páginas muy pequeñas),
    deja solo el bloque en español.
    """
    margin = max(24.0, min(56.0, width * 0.1))
    blocks = options.paragraphs()
    for drop_english in (False, True):
        current = blocks[:1] if drop_english else blocks
        size = 10.5
        while size >= 7.0:
            leading = round(size * 1.38, 2)
            lines = _wrap_blocks(current, size, width - 2 * margin)
            if len(lines) * leading <= height - 2 * margin:
                return margin, size, leading, lines, drop_english and len(blocks) > 1
            size -= 0.5
    # Último recurso: 7 pt sin inglés aunque desborde (no debería pasar en libros reales).
    return margin, 7.0, 9.66, _wrap_blocks(blocks[:1], 7.0, width - 2 * margin), len(blocks) > 1


def build_pdf_notice_stream(
    options: NoticeOptions, width: float, height: float, as_artifact: bool
) -> bytes:
    """Operadores de contenido de la página de aviso (Helvetica, WinAnsiEncoding)."""
    margin, size, leading, lines, _ = layout_pdf_notice(options, width, height)

    ops = [b"/Artifact BMC" if as_artifact else b"", b"BT"]
    ops.append(f"{leading} TL {margin} {height - margin} Td".encode())
    for text, bold in lines:
        font = b"/F2" if bold else b"/F1"
        ops.append(font + f" {size + (1.5 if bold else 0)} Tf".encode())
        ops.append(_pdf_string(text) + b" Tj T*")
    ops.append(b"ET")
    if as_artifact:
        ops.append(b"EMC")
    return b"\n".join(op for op in ops if op)


# ---- EPUB -----------------------------------------------------------------------


def build_epub_notice_xhtml(options: NoticeOptions, epub3: bool) -> bytes:
    # EPUB 2 es XHTML 1.1: no tiene <section> ni el atributo `lang` (solo
    # xml:lang). EPUBCheck lo rechaza (visto con EPUBCheck 5.4.0).
    tag = "section" if epub3 else "div"
    sections = []
    for i, (title, paragraphs) in enumerate(options.paragraphs()):
        lang = "es" if i == 0 else "en"
        lang_attrs = f'xml:lang="{lang}" lang="{lang}"' if epub3 else f'xml:lang="{lang}"'
        body = "\n".join(f"    <p>{escape(p)}</p>" for p in paragraphs)
        sections.append(f"  <{tag} {lang_attrs}>\n    <h1>{escape(title)}</h1>\n{body}\n  </{tag}>")
    if epub3:
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="es" lang="es">\n'
        )
    else:
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
            '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="es">\n'
        )
    return (
        head
        + f"<head>\n  <title>{escape(NOTICE_TITLE_ES)}</title>\n</head>\n<body>\n"
        + "\n".join(sections)
        + "\n</body>\n</html>\n"
    ).encode("utf-8")
