"""Fixtures compartidos: genera PDFs mínimos en tiempo de prueba con pikepdf.

No se versionan PDF binarios reales en el repositorio; los fixtures se
construyen programáticamente para que la suite sea reproducible y no dependa
de archivos externos.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest


def _new_pdf_bytes(*, page_count: int = 1) -> bytes:
    pdf = pikepdf.Pdf.new()
    for _ in range(page_count):
        pdf.add_blank_page(page_size=(200, 200))
    import io

    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture
def make_pdf(tmp_path: Path):
    """Factory: crea un PDF de N páginas sin XMP en tmp_path y devuelve su ruta."""

    def _make(name: str = "plain.pdf", *, page_count: int = 1) -> Path:
        path = tmp_path / name
        path.write_bytes(_new_pdf_bytes(page_count=page_count))
        return path

    return _make


@pytest.fixture
def make_pdf_with_xmp(tmp_path: Path):
    """Factory: crea un PDF con un XMP arbitrario (bytes) de nivel de documento."""

    def _make(name: str, xmp_bytes: bytes, *, page_count: int = 1) -> Path:
        pdf = pikepdf.Pdf.new()
        for _ in range(page_count):
            pdf.add_blank_page(page_size=(200, 200))
        stream = pikepdf.Stream(pdf, xmp_bytes)
        stream["/Type"] = pikepdf.Name("/Metadata")
        stream["/Subtype"] = pikepdf.Name("/XML")
        pdf.Root["/Metadata"] = stream
        path = tmp_path / name
        pdf.save(path)
        return path

    return _make


def _escape_pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build_text_pdf(
    path: Path,
    pages: list[str],
    *,
    title: str | None = None,
    xmp_bytes: bytes | None = None,
) -> Path:
    """PDF con texto real extraíble (Helvetica, WinAnsiEncoding), una línea por renglón."""
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/Font"),
            Subtype=pikepdf.Name("/Type1"),
            BaseFont=pikepdf.Name("/Helvetica"),
            Encoding=pikepdf.Name("/WinAnsiEncoding"),
        )
    )
    for page_text in pages:
        ops = [b"BT /F1 11 Tf 14 TL 40 760 Td"]
        for line in page_text.splitlines():
            ops.append(b"(" + _escape_pdf_string(line) + b") Tj T*")
        ops.append(b"ET")
        page = pdf.add_blank_page(page_size=(595, 842))
        page.obj["/Resources"] = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.obj["/Contents"] = pdf.make_stream(b"\n".join(ops))
    if title is not None:
        pdf.docinfo["/Title"] = title
    if xmp_bytes is not None:
        stream = pikepdf.Stream(pdf, xmp_bytes)
        stream["/Type"] = pikepdf.Name("/Metadata")
        stream["/Subtype"] = pikepdf.Name("/XML")
        pdf.Root["/Metadata"] = stream
    pdf.save(path)
    return path


SAMPLE_TEXT = [
    "La minería de textos y datos sobre esta obra está reservada.\n"
    "Capítulo primero. De cómo el editor declaró sus derechos\n"
    "frente al entrenamiento de modelos de inteligencia artificial.",
    "Segunda página: el contenido no cambia al sellar el archivo,\n"
    "porque TDM Seal solo modifica los metadatos XMP del documento.",
]


@pytest.fixture
def make_text_pdf(tmp_path: Path):
    """Factory: PDF con texto extraíble (para el ISCC de contenido)."""

    def _make(
        name: str = "texto.pdf",
        pages: list[str] | None = None,
        *,
        title: str | None = None,
        xmp_bytes: bytes | None = None,
    ) -> Path:
        return build_text_pdf(
            tmp_path / name, pages or SAMPLE_TEXT, title=title, xmp_bytes=xmp_bytes
        )

    return _make


def build_incremental_without_info(path: Path, *, title: str, subject: str) -> Path:
    """PDF con Info en el tráiler original y una actualización incremental que no lo repite.

    Reproduce lo que hace MuPDF al guardar de forma incremental (caso real
    encontrado el 19-nov-2026: al sellar, el título y el asunto se perdían).
    """
    import re

    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Title"] = title
    pdf.docinfo["/Subject"] = subject
    pdf.save(path, object_stream_mode=pikepdf.ObjectStreamMode.disable)
    data = path.read_bytes()

    prev_xref = int(re.findall(rb"startxref\s+(\d+)", data)[-1])
    root_num = int(re.search(rb"/Root\s+(\d+)\s+\d+\s+R", data).group(1))
    size = int(re.search(rb"/Size\s+(\d+)", data).group(1))
    with pikepdf.open(path) as reopened:
        pages_num, pages_gen = reopened.Root.Pages.objgen

    obj = (
        f"{root_num} 0 obj\n<< /Type /Catalog /Pages {pages_num} {pages_gen} R >>\nendobj\n"
    ).encode()
    body = data if data.endswith(b"\n") else data + b"\n"
    obj_offset = len(body)
    xref_offset = obj_offset + len(obj)
    update = (
        obj
        + f"xref\n{root_num} 1\n{obj_offset:010d} 00000 n \n".encode()
        + f"trailer\n<< /Size {size} /Root {root_num} 0 R /Prev {prev_xref} >>\n".encode()
        + f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    path.write_bytes(body + update)
    return path


@pytest.fixture
def make_incremental_pdf(tmp_path: Path):
    """Factory: PDF cuyo último tráiler no repite /Info (ver build_incremental_without_info)."""

    def _make(name: str = "incremental.pdf", *, title: str = "T", subject: str = "S") -> Path:
        return build_incremental_without_info(tmp_path / name, title=title, subject=subject)

    return _make


CONTAINER_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    "  <rootfiles>\n"
    '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
    "  </rootfiles>\n"
    "</container>\n"
)


def _chapter_xhtml(title: str, text: str) -> str:
    paragraphs = "\n".join(f"    <p>{line}</p>" for line in text.splitlines())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        f"  <head><title>{title}</title></head>\n"
        f"  <body>\n    <h1>{title}</h1>\n{paragraphs}\n  </body>\n</html>\n"
    )


def build_epub(
    path: Path,
    *,
    version: int = 3,
    title: str = "Derechos y minería",
    chapters: list[str] | None = None,
    extra_meta: str = "",
    package_prefix: str | None = None,
    extra_files: dict[str, bytes] | None = None,
    mimetype_first: bool = True,
) -> Path:
    """EPUB 2 o 3 mínimo pero válido, generado por programa (sin binarios versionados)."""
    import zipfile

    chapters = chapters or SAMPLE_TEXT
    manifest = [
        f'    <item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(len(chapters))
    ]
    spine = [f'    <itemref idref="c{i}"/>' for i in range(len(chapters))]
    if version == 3:
        manifest.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
        )
        modified = '    <meta property="dcterms:modified">2026-11-19T00:00:00Z</meta>\n'
        spine_attr = ""
    else:
        manifest.append('    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        modified = ""
        spine_attr = ' toc="ncx"'
    prefix_attr = f' prefix="{package_prefix}"' if package_prefix else ""
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" '
        f'unique-identifier="uid"{prefix_attr}>\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">urn:isbn:9789580000000</dc:identifier>\n'
        f"    <dc:title>{title}</dc:title>\n"
        "    <dc:language>es</dc:language>\n"
        f"{modified}{extra_meta}"
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest) + "\n  </manifest>\n"
        f"  <spine{spine_attr}>\n" + "\n".join(spine) + "\n  </spine>\n"
        "</package>\n"
    )
    nav = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Índice</title></head><body>\n"
        '<nav epub:type="toc"><ol>'
        + "".join(f'<li><a href="c{i}.xhtml">Cap. {i}</a></li>' for i in range(len(chapters)))
        + "</ol></nav>\n</body></html>\n"
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        '<head><meta name="dtb:uid" content="urn:isbn:9789580000000"/></head>\n'
        f"<docTitle><text>{title}</text></docTitle>\n<navMap>"
        + "".join(
            f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>Cap. {i}</text>'
            f'</navLabel><content src="c{i}.xhtml"/></navPoint>'
            for i in range(len(chapters))
        )
        + "</navMap>\n</ncx>\n"
    )

    entries: list[tuple[str, bytes, int]] = [
        ("META-INF/container.xml", CONTAINER_XML.encode(), zipfile.ZIP_DEFLATED),
        ("OEBPS/content.opf", opf.encode(), zipfile.ZIP_DEFLATED),
    ]
    for i, text in enumerate(chapters):
        entries.append(
            (f"OEBPS/c{i}.xhtml", _chapter_xhtml(f"Cap. {i}", text).encode(), zipfile.ZIP_DEFLATED)
        )
    if version == 3:
        entries.append(("OEBPS/nav.xhtml", nav.encode(), zipfile.ZIP_DEFLATED))
    else:
        entries.append(("OEBPS/toc.ncx", ncx.encode(), zipfile.ZIP_DEFLATED))
    for name, data in (extra_files or {}).items():
        entries.append((name, data, zipfile.ZIP_DEFLATED))

    mimetype = ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
    ordered = [mimetype, *entries] if mimetype_first else [*entries[:1], mimetype, *entries[1:]]
    with zipfile.ZipFile(path, "w") as zf:
        for name, data, compression in ordered:
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 19, 12, 0, 0))
            info.compress_type = compression
            zf.writestr(info, data)
    return path


@pytest.fixture
def make_epub(tmp_path: Path):
    """Factory: EPUB 2/3 generado por programa (ver build_epub)."""

    def _make(name: str = "libro.epub", **kwargs) -> Path:
        return build_epub(tmp_path / name, **kwargs)

    return _make


def _pdfa_xmp(part: int, conformance: str | None) -> bytes:
    conformance_attr = f' pdfaid:conformance="{conformance}"' if conformance else ""
    return (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" '
        b'xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
        + f'pdfaid:part="{part}"{conformance_attr}/>'.encode()
        + b"</rdf:RDF></x:xmpmeta>"
    )


@pytest.fixture
def make_pdfa(make_pdf_with_xmp):
    """Factory: crea un PDF cuyo XMP declara conformidad PDF/A (pdfaid:part/conformance).

    No es un PDF/A válido en sentido estricto (perfil de color, fuentes
    embebidas, etc. no se configuran) — sirve para probar la lógica de
    detección y de merge del Extension Schema, no para pasar veraPDF.
    """

    def _make(name: str, part: int, conformance: str | None = "B") -> Path:
        return make_pdf_with_xmp(name, _pdfa_xmp(part, conformance))

    return _make


@pytest.fixture
def make_signed_pdf(tmp_path: Path):
    """Factory: crea un PDF con un campo de firma (/FT /Sig) real y con valor.

    La firma no es criptográficamente válida (no hay clave privada de
    prueba), pero la estructura es la misma que revisa el detector de
    firmas: un campo AcroForm con /FT /Sig y /V presente.
    """

    def _make(name: str = "signed.pdf") -> Path:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(200, 200))
        sig_dict = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name("/Sig"),
                Filter=pikepdf.Name("/Adobe.PPKLite"),
                SubFilter=pikepdf.Name("/adbe.pkcs7.detached"),
                Contents=pikepdf.String(b"\x00" * 16),
                ByteRange=pikepdf.Array([0, 0, 0, 0]),
            )
        )
        sig_field = pdf.make_indirect(
            pikepdf.Dictionary(
                FT=pikepdf.Name("/Sig"),
                T=pikepdf.String("Signature1"),
                Rect=pikepdf.Array([0, 0, 0, 0]),
                V=sig_dict,
            )
        )
        pdf.Root.AcroForm = pdf.make_indirect(
            pikepdf.Dictionary(Fields=pikepdf.Array([sig_field]), SigFlags=3)
        )
        path = tmp_path / name
        pdf.save(path)
        return path

    return _make


@pytest.fixture
def make_encrypted_pdf(tmp_path: Path):
    """Factory: crea un PDF realmente cifrado con pikepdf.Encryption.

    `user_password=""` produce un PDF que se abre sin contraseña (pero con
    `is_encrypted=True`); una contraseña no vacía produce uno que
    `pikepdf.open()` no puede leer sin ella (dispara `PasswordError`).
    """

    def _make(name: str = "encrypted.pdf", user_password: str = "") -> Path:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(200, 200))
        path = tmp_path / name
        pdf.save(
            path,
            encryption=pikepdf.Encryption(owner="owner-secret", user=user_password),
        )
        return path

    return _make
