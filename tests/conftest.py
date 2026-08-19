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
