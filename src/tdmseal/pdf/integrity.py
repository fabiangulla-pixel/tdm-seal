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


def compare_non_metadata_invariants(input_path: Path, output_path: Path) -> dict:
    """Compara `input_path` y `output_path`; devuelve {"status", "issues"}."""
    issues: list[str] = []
    with pikepdf.open(input_path) as before, pikepdf.open(output_path) as after:
        if len(before.pages) != len(after.pages):
            issues.append(f"número de páginas cambió: {len(before.pages)} -> {len(after.pages)}")
        elif _page_geometry(before) != _page_geometry(after):
            issues.append("geometría o rotación de alguna página cambió")

        if _count_annotations(before) != _count_annotations(after):
            issues.append("número de anotaciones cambió")

        if _count_attachments(before) != _count_attachments(after):
            issues.append("número de adjuntos (embedded files) cambió")

    return {"status": "PASS" if not issues else "FAIL", "issues": issues}
