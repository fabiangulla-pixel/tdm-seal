"""Detección de firmas digitales en un PDF.

Un PDF con firma digital no debe modificarse por defecto: alterar sus bytes
puede invalidar la firma (ver TDM021 en la especificación). Comprobado con
firmas reales de pyHanko (tests/integration/test_firmas_reales.py).

Se considera firmado si:
- algún campo de formulario de tipo firma (`/FT /Sig`, propio o heredado del
  campo padre, ISO 32000-1 §12.7.3.1) tiene valor (`/V`); o
- el catálogo declara `/Perms` con `/DocMDP` (firma de certificación) o
  `/UR3` (derechos de uso de Reader), que también se rompen al reescribir.

Un campo de firma vacío (sin `/V`) no cuenta: es un hueco para firmar después.
"""

from __future__ import annotations

import pikepdf

_SIG = pikepdf.Name("/Sig")


def has_digital_signature(pdf: pikepdf.Pdf) -> bool:
    """True si el PDF tiene una firma aplicada (ver docstring del módulo)."""
    perms = pdf.Root.get("/Perms")
    if isinstance(perms, pikepdf.Dictionary) and ("/DocMDP" in perms or "/UR3" in perms):
        return True
    acroform = pdf.Root.get("/AcroForm")
    if not isinstance(acroform, pikepdf.Dictionary):
        return False
    fields = acroform.get("/Fields")
    if not isinstance(fields, pikepdf.Array):
        return False
    seen: set[tuple[int, int]] = set()
    return any(_field_has_signature(field, None, seen) for field in fields)


def _field_has_signature(
    field: pikepdf.Object, inherited_ft: pikepdf.Object | None, seen: set[tuple[int, int]]
) -> bool:
    if not isinstance(field, pikepdf.Dictionary):
        return False
    if field.is_indirect:
        if field.objgen in seen:  # /Kids cíclico en un PDF mal formado
            return False
        seen.add(field.objgen)
    field_type = field.get("/FT", inherited_ft)
    if field_type == _SIG and "/V" in field:
        return True
    kids = field.get("/Kids")
    if isinstance(kids, pikepdf.Array):
        return any(_field_has_signature(kid, field_type, seen) for kid in kids)
    return False
