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
