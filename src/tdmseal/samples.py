"""PDF y EPUB de ejemplo generados por programa.

Los usan las pruebas (tests/conftest.py) y la autoprueba del programa
(`tdmseal selftest`, `TDM-Seal.exe --autoprueba`), para verificar que la
instalación funciona de punta a punta sin depender de archivos externos.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pikepdf


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
        '    <dc:identifier id="uid">urn:isbn:9789580000006</dc:identifier>\n'
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
        '<head><meta name="dtb:uid" content="urn:isbn:9789580000006"/></head>\n'
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
