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


def _count_attachments(pdf: pikepdf.Pdf) -> int:
    names = pdf.Root.get("/Names")
    if not names:
        return 0
    embedded = names.get("/EmbeddedFiles")
    if not embedded:
        return 0
    entries = embedded.get("/Names")
    if not entries:
        return 0
    return len(entries) // 2


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

        if _count_attachments(before) != _count_attachments(after):
            issues.append("número de adjuntos (embedded files) cambió")

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
