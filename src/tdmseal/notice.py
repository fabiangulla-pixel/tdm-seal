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

PLANTILLA DE TEXTO: pendiente de revisión de estilo por el editor
(ver docs/aviso-visible.md). Se mantiene en este único lugar para que la
revisión sea un cambio de una sola constante.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from html import escape

NOTICE_TITLE_ES = "Reserva de derechos de minería de textos y datos"
NOTICE_TITLE_EN = "Text and data mining rights reserved"

NOTICE_ES = (
    "{editorial} reserva los derechos de minería de textos y datos sobre esta obra, "
    "incluido su uso para entrenar o alimentar sistemas de inteligencia artificial, "
    "conforme a la legislación aplicable. Esta reserva no es una negativa definitiva: "
    "si desea usar la obra con esos fines, puede solicitar una licencia a {contacto}."
)
NOTICE_POLICY_ES = "Condiciones de licencia: {politica}"
NOTICE_EN = (
    "{editorial} reserves its text and data mining rights over this work, including "
    "its use to train or feed artificial intelligence systems. This is an invitation "
    "to license, not a final refusal: to request a license, contact {contacto}."
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
        es = [NOTICE_ES.format(**values)]
        en = [NOTICE_EN.format(**values)]
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


def build_pdf_notice_stream(
    options: NoticeOptions, width: float, height: float, as_artifact: bool
) -> bytes:
    """Operadores de contenido de la página de aviso (Helvetica, WinAnsiEncoding)."""
    margin = 56.0
    size, leading = 10.5, 14.5
    chars_per_line = max(30, int((width - 2 * margin) / (size * 0.5)))
    lines: list[tuple[str, bool]] = []
    for title, paragraphs in options.paragraphs():
        lines.append((title, True))
        lines.append(("", False))
        for paragraph in paragraphs:
            lines.extend((ln, False) for ln in textwrap.wrap(paragraph, chars_per_line))
            lines.append(("", False))
        lines.append(("", False))

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
