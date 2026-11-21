"""Comprobación de que un PDF sellado conserva sus invariantes no-metadata.

Ver sección 14 de la especificación: número de páginas, geometría, rotación,
anotaciones y adjuntos deben coincidir antes y después del sellado.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf


def _page_geometry(pdf: pikepdf.Pdf) -> list[tuple[float, float, int]]:
    geometry = []
    for page in pdf.pages:
        box = page.MediaBox
        width = float(box[2]) - float(box[0])
        height = float(box[3]) - float(box[1])
        rotation = int(page.get("/Rotate", 0))
        geometry.append((round(width, 3), round(height, 3), rotation))
    return geometry


def _count_annotations(pdf: pikepdf.Pdf) -> int:
    return sum(len(page.get("/Annots", [])) for page in pdf.pages)


def _attachments(pdf: pikepdf.Pdf) -> dict[str, bytes]:
    """Adjuntos (nombre -> contenido). Recorre el árbol de nombres completo (con /Kids)."""
    result = {}
    for name, spec in pdf.attachments.items():
        try:
            result[name] = spec.get_file().read_bytes()
        except (pikepdf.PdfError, AttributeError, ValueError):
            result[name] = b""
    return result


def _form_fields(pdf: pikepdf.Pdf) -> dict[str, str]:
    """Campos de formulario (nombre completo -> valor serializado)."""
    acroform = pdf.Root.get("/AcroForm")
    if not isinstance(acroform, pikepdf.Dictionary):
        return {}
    result: dict[str, str] = {}
    seen: set[tuple[int, int]] = set()

    def walk(field, prefix: str) -> None:
        if not isinstance(field, pikepdf.Dictionary):
            return
        if field.is_indirect:
            if field.objgen in seen:
                return
            seen.add(field.objgen)
        name = str(field.get("/T", ""))
        full = f"{prefix}.{name}" if prefix and name else (name or prefix)
        if "/V" in field:
            value = field["/V"]
            # Firmas: basta con saber que siguen; su contenido no se compara.
            result[full] = "<firma>" if isinstance(value, pikepdf.Dictionary) else str(value)
        for kid in field.get("/Kids", []) or []:
            walk(kid, full)

    for field in acroform.get("/Fields", []) or []:
        walk(field, "")
    return result


def compare_non_metadata_invariants(
    input_path: Path, output_path: Path, added_pages: int = 0
) -> dict:
    """Compara `input_path` y `output_path`; devuelve {"status", "issues"}.

    `added_pages` admite páginas nuevas **al final** (aviso visible): las
    existentes deben seguir idénticas en número, geometría y rotación.
    """
    issues: list[str] = []
    with pikepdf.open(input_path) as before, pikepdf.open(output_path) as after:
        expected = len(before.pages) + added_pages
        if len(after.pages) != expected:
            issues.append(
                f"número de páginas cambió: {len(before.pages)} -> {len(after.pages)} "
                f"(se esperaban {expected})"
            )
        elif _page_geometry(before) != _page_geometry(after)[: len(before.pages)]:
            issues.append("geometría o rotación de alguna página cambió")

        if _count_annotations(before) != _count_annotations(after):
            issues.append("número de anotaciones cambió")

        att_before, att_after = _attachments(before), _attachments(after)
        if set(att_before) != set(att_after):
            issues.append("los adjuntos (embedded files) cambiaron")
        elif any(att_before[k] != att_after[k] for k in att_before):
            issues.append("el contenido de algún adjunto cambió")

        if _form_fields(before) != _form_fields(after):
            issues.append("los campos de formulario o sus valores cambiaron")

    return {"status": "PASS" if not issues else "FAIL", "issues": issues}


def compare_encryption(input_path: Path, output_path: Path) -> dict:
    """Un PDF cifrado debe seguir cifrado, con el mismo método y los mismos permisos."""
    with pikepdf.open(input_path) as before, pikepdf.open(output_path) as after:
        if not before.is_encrypted:
            return {"status": "PASS", "issues": []}
        if not after.is_encrypted:
            return {
                "status": "FAIL",
                "issues": ["el PDF original estaba cifrado y la copia sellada no lo está"],
            }
        issues = []
        if before.allow != after.allow:
            issues.append("los permisos del PDF cifrado cambiaron (imprimir, copiar…)")
        if before.encryption.bits != after.encryption.bits:
            issues.append(
                f"la fuerza del cifrado cambió ({before.encryption.bits} -> "
                f"{after.encryption.bits} bits)"
            )
    return {"status": "PASS" if not issues else "FAIL", "issues": issues}


def compare_docinfo(input_path: Path, output_path: Path) -> dict:
    """Comprueba que el diccionario Info (título, autor…) no se perdió ni cambió.

    Compara el Info efectivo, incluido el heredado de tráileres anteriores
    (ver `pdf/docinfo.py`). Se ignora `/ModDate`/`/Producer`, que algunos
    flujos actualizan legítimamente.
    """
    from tdmseal.pdf.docinfo import effective_docinfo

    ignored = {"/ModDate", "/Producer"}
    before = {k: v for k, v in effective_docinfo(input_path).items() if k not in ignored}
    after = {k: v for k, v in effective_docinfo(output_path).items() if k not in ignored}
    issues = []
    for key, value in before.items():
        if key not in after:
            issues.append(f"el diccionario Info perdió {key}")
        elif after[key] != value:
            issues.append(f"el diccionario Info cambió {key}")
    return {"status": "PASS" if not issues else "FAIL", "issues": issues}
