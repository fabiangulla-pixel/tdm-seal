"""Detección de firmas digitales en un PDF.

Un PDF con firma digital no debe modificarse por defecto: alterar sus bytes
puede invalidar la firma (ver TDM021 en la especificación).
"""

from __future__ import annotations

import pikepdf


def has_digital_signature(pdf: pikepdf.Pdf) -> bool:
    """True si el PDF tiene al menos un campo de formulario de tipo firma con valor."""
    acroform = pdf.Root.get("/AcroForm")
    if not acroform:
        return False
    fields = acroform.get("/Fields")
    if not fields:
        return False
    return any(_field_has_signature(field) for field in fields)


def _field_has_signature(field: pikepdf.Object) -> bool:
    if field.get("/FT") == pikepdf.Name("/Sig") and "/V" in field:
        return True
    kids = field.get("/Kids")
    if kids:
        return any(_field_has_signature(kid) for kid in kids)
    return False
