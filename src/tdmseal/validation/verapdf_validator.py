"""Validación PDF/A con veraPDF.

No implementado todavía: el manejo de PDF/A (PDF/A XMP Extension Schema,
sección 6 de la especificación) es la fase siguiente del roadmap (v0.2.0),
posterior al núcleo TDMRep para PDF genérico. Esta función existe como punto
de extensión para no romper la forma del reporte cuando se integre veraPDF.
"""

from __future__ import annotations

from pathlib import Path


def run_verapdf(output_path: Path) -> dict:
    return {
        "status": "SKIPPED",
        "issues": ["validación PDF/A con veraPDF no implementada aún (roadmap v0.2.0)"],
    }
