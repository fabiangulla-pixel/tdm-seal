"""Validación de integridad sintáctica del PDF de salida (equivalente a `qpdf --check`).

Usa `pikepdf.Pdf.check_pdf_syntax()`, que se apoya en la misma librería qpdf
que usa pikepdf internamente, evitando depender de que el binario `qpdf` esté
instalado por separado. Si esa API no está disponible en la versión de
pikepdf instalada, la validación se marca como SKIPPED en lugar de fallar
el sellado completo.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf


def qpdf_check(output_path: Path) -> dict:
    """Devuelve {"status": "PASS"|"FAIL"|"SKIPPED", "issues": [...]}."""
    try:
        with pikepdf.open(output_path) as pdf:
            checker = getattr(pdf, "check_pdf_syntax", None)
            if checker is None:
                return {
                    "status": "SKIPPED",
                    "issues": ["pikepdf.Pdf.check_pdf_syntax() no disponible en esta versión"],
                }
            problems = list(checker())
    except (pikepdf.PdfError, OSError) as exc:
        return {"status": "FAIL", "issues": [str(exc)]}

    return {"status": "PASS" if not problems else "FAIL", "issues": [str(p) for p in problems]}
