"""Diccionario Info del PDF (título, autor, asunto…), incluido el heredado.

Algunos programas (p. ej. MuPDF) guardan una actualización incremental cuyo
último tráiler no repite la entrada `/Info`: el diccionario sigue en el
archivo y lo referencia un tráiler anterior (`/Prev`). Lectores como PDFBox
(y por tanto Tika e iscc-sdk) heredan ese `/Info`; qpdf/pikepdf solo miran
el último tráiler y no lo ven.

Consecuencia sin este módulo: al guardar con pikepdf se escribe un archivo
nuevo con el último tráiler, y el título y el asunto **desaparecían** del
PDF sellado (visto el 19-nov-2026 con un PDF real editado con MuPDF).
"""

from __future__ import annotations

import re
from pathlib import Path

import pikepdf

_INFO_REF_RE = re.compile(rb"/Info\s+(\d+)\s+(\d+)\s+R")


def find_inherited_info(pdf: pikepdf.Pdf, path: Path) -> pikepdf.Dictionary | None:
    """Devuelve el `/Info` de un tráiler anterior si el último no lo declara.

    Devuelve None si el último tráiler ya tiene `/Info` (caso normal) o si no
    hay ningún `/Info` recuperable.
    """
    if "/Info" in pdf.trailer:
        return None
    data = Path(path).read_bytes()
    for match in reversed(list(_INFO_REF_RE.finditer(data))):
        objnum, gen = int(match.group(1)), int(match.group(2))
        try:
            obj = pdf.get_object((objnum, gen))
        except (pikepdf.PdfError, ValueError, KeyError):
            continue
        if isinstance(obj, pikepdf.Dictionary) and len(obj.keys()) > 0:
            return obj
    return None


def restore_inherited_info(pdf: pikepdf.Pdf, path: Path) -> bool:
    """Vuelve a enlazar en el tráiler el `/Info` heredado. True si lo hizo."""
    info = find_inherited_info(pdf, path)
    if info is None:
        return False
    pdf.trailer["/Info"] = info
    return True


def effective_docinfo(path: Path) -> dict[str, str]:
    """Info tal como lo ve un lector que hereda tráileres (claves -> texto)."""
    with pikepdf.open(path) as pdf:
        info = pdf.trailer.get("/Info")
        if info is None:
            info = find_inherited_info(pdf, path)
        if info is None:
            return {}
        result = {}
        for key in info.keys():
            try:
                result[str(key)] = str(info[key])
            except (pikepdf.PdfError, ValueError):
                continue
        return result
