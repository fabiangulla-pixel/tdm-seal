"""Fixtures compartidos: genera PDFs mínimos en tiempo de prueba con pikepdf.

No se versionan PDF binarios reales en el repositorio; los fixtures se
construyen programáticamente para que la suite sea reproducible y no dependa
de archivos externos.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from tdmseal.samples import SAMPLE_TEXT, build_epub, build_text_pdf  # noqa: F401


@pytest.fixture(autouse=True)
def _no_external_tools_by_default(request, monkeypatch):
    """veraPDF y EPUBCheck (Java) solo corren en pruebas marcadas `real_tools`.

    Así la suite es rápida y da lo mismo en un equipo con o sin las
    herramientas instaladas.
    """
    if request.node.get_closest_marker("real_tools"):
        return
    from tdmseal import tools

    monkeypatch.setattr(tools, "find_verapdf", lambda: None)
    monkeypatch.setattr(tools, "find_epubcheck", lambda: None)


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
