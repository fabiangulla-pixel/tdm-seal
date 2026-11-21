"""Escritura del XMP de nivel de documento y guardado del PDF resultante."""

from __future__ import annotations

from pathlib import Path

import pikepdf


def create_output_path(input_path: Path, suffix: str = "_TDM") -> Path:
    """Ruta de salida por defecto: copia junto al original con un sufijo."""
    input_path = Path(input_path)
    return input_path.with_name(f"{input_path.stem}{suffix}{input_path.suffix}")


def write_document_xmp_bytes(pdf: pikepdf.Pdf, xmp_bytes: bytes) -> None:
    """Reemplaza el stream /Metadata de nivel de documento por `xmp_bytes`."""
    stream = pikepdf.Stream(pdf, xmp_bytes)
    stream["/Type"] = pikepdf.Name("/Metadata")
    stream["/Subtype"] = pikepdf.Name("/XML")
    pdf.Root["/Metadata"] = stream


def save_pdf(pdf: pikepdf.Pdf, output_path: Path) -> None:
    """Guarda el PDF. Si estaba cifrado, conserva cifrado, claves y permisos.

    Sin `encryption=True`, pikepdf guarda la copia **descifrada y sin
    restricciones** (visto el 21-nov-2026: un PDF que prohibía copiar texto
    salía sellado sin protección).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf.save(output_path, encryption=True if pdf.is_encrypted else None)
