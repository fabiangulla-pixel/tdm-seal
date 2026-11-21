"""Actualización incremental del XMP: añade una revisión al final del PDF.

Para PDF firmados. Reescribir el archivo (pikepdf `save`) cambia los bytes que
cubre la firma y la invalida. Una actualización incremental (ISO 32000-1
§7.5.6) deja intactos todos los bytes originales y solo añade al final:

- el stream de metadatos XMP nuevo (si el documento ya tenía `/Metadata`
  indirecto, se reemplaza ese mismo objeto; si no, se crea uno y se añade una
  versión nueva del catálogo que lo enlaza);
- una sección de referencias cruzadas del mismo tipo que la última del
  archivo (tabla clásica o stream `/XRef`, para no subir la versión de PDF ni
  romper PDF/A-1) y su tráiler con `/Prev`.

Así la firma sigue validando la revisión firmada, como cuando un lector
añade una segunda firma. Comprobado con pyHanko en
tests/integration/test_firmas_reales.py.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pikepdf

from tdmseal.pdf.docinfo import find_inherited_info

_STARTXREF_RE = re.compile(rb"startxref\s+(\d+)\s+%%EOF\s*$")


class IncrementalUpdateError(ValueError):
    """El PDF no admite una actualización incremental segura."""


def _last_xref_offset(data: bytes) -> int:
    match = _STARTXREF_RE.search(data[-2048:])
    if not match:
        raise IncrementalUpdateError("no se encontró 'startxref' al final del PDF")
    return int(match.group(1))


def _ref(obj: pikepdf.Object) -> bytes:
    num, gen = obj.objgen
    return f"{num} {gen} R".encode()


def _metadata_stream_body(xmp_bytes: bytes) -> bytes:
    # Sin /Filter: PDF/A-1 exige el XMP de documento sin comprimir.
    return (
        f"<< /Type /Metadata /Subtype /XML /Length {len(xmp_bytes)} >>\nstream\n".encode()
        + xmp_bytes
        + b"\nendstream"
    )


def append_xmp_update(input_path: Path, output_path: Path, xmp_bytes: bytes) -> None:
    """Escribe en `output_path` el original intacto más una revisión con `xmp_bytes`."""
    data = Path(input_path).read_bytes()
    prev = _last_xref_offset(data)
    classic = data[prev : prev + 4] == b"xref"

    with pikepdf.open(input_path) as pdf:
        if pdf.is_encrypted:
            raise IncrementalUpdateError("los PDF cifrados no se actualizan de forma incremental")
        trailer = pdf.trailer
        size = int(trailer["/Size"])
        root = pdf.Root
        if not root.is_indirect:
            raise IncrementalUpdateError("el catálogo no es un objeto indirecto")

        bodies: dict[tuple[int, int], bytes] = {}
        metadata = root.get("/Metadata")
        if metadata is not None and metadata.is_indirect:
            bodies[metadata.objgen] = _metadata_stream_body(xmp_bytes)
        else:
            # Se enlaza en memoria (el PDF abierto no se guarda) solo para que
            # pikepdf asigne el número de objeto y serialice el catálogo nuevo.
            placeholder = pdf.make_indirect(pikepdf.Stream(pdf, b""))
            root["/Metadata"] = placeholder
            meta_ref = placeholder.objgen
            size = max(size, meta_ref[0] + 1)
            bodies[meta_ref] = _metadata_stream_body(xmp_bytes)
            bodies[root.objgen] = root.unparse(resolved=True)

        info = trailer.get("/Info")
        if info is None:
            info = find_inherited_info(pdf, Path(input_path))
        extra = b""
        if info is not None and info.is_indirect:
            extra += b" /Info " + _ref(info)
        if "/ID" in trailer:
            extra += b" /ID " + trailer["/ID"].unparse(resolved=True)
        root_ref = _ref(root)

    out = bytearray(data)
    if not out.endswith((b"\n", b"\r")):
        out += b"\n"
    offsets: dict[tuple[int, int], int] = {}
    for (num, gen), body in sorted(bodies.items()):
        offsets[(num, gen)] = len(out)
        out += f"{num} {gen} obj\n".encode() + body + b"\nendobj\n"

    if classic:
        xref_offset = len(out)
        out += b"xref\n"
        for (num, gen), off in sorted(offsets.items()):
            out += f"{num} 1\n{off:010d} {gen:05d} n\r\n".encode()
        out += (
            f"trailer\n<< /Size {size} /Root ".encode()
            + root_ref
            + extra
            + f" /Prev {prev} >>\n".encode()
        )
    else:
        xref_num = size
        size += 1
        xref_offset = len(out)
        offsets[(xref_num, 0)] = xref_offset
        index = b""
        rows = b""
        for (num, gen), off in sorted(offsets.items()):
            index += f"{num} 1 ".encode()
            rows += struct.pack(">BIH", 1, off, gen)
        out += (
            f"{xref_num} 0 obj\n<< /Type /XRef /Size {size} /W [1 4 2] ".encode()
            + b"/Index ["
            + index.strip()
            + b"] /Root "
            + root_ref
            + extra
            + f" /Prev {prev} /Length {len(rows)} >>\nstream\n".encode()
            + rows
            + b"\nendstream\nendobj\n"
        )
    out += f"startxref\n{xref_offset}\n%%EOF\n".encode()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(bytes(out))
