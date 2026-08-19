"""Relectura del PDF de salida para confirmar que la declaración TDMRep escrita
coincide exactamente con la solicitada (sección 13 del algoritmo principal)."""

from __future__ import annotations

from pathlib import Path

import pikepdf

from tdmseal.models import TDMPolicy
from tdmseal.pdf.inspector import read_document_xmp_bytes
from tdmseal.xmp.parser import find_rdf_root, parse_xmp
from tdmseal.xmp.tdmrep import read_tdmrep


def verify_tdmrep_by_rereading(output_path: Path, expected: TDMPolicy) -> dict:
    """Vuelve a abrir `output_path` y comprueba que TDMRep quedó escrito tal cual."""
    with pikepdf.open(output_path) as pdf:
        xmp_bytes = read_document_xmp_bytes(pdf)

    if xmp_bytes is None:
        return {"status": "FAIL", "issues": ["el PDF de salida no tiene XMP de documento"]}

    rdf_root = find_rdf_root(parse_xmp(xmp_bytes))
    declaration = read_tdmrep(rdf_root)

    issues = []
    if declaration.reservation != expected.reservation:
        issues.append(
            f"tdm:reservation esperado={expected.reservation} leído={declaration.reservation}"
        )
    if (expected.policy_url or None) != (declaration.policy_url or None):
        issues.append(
            f"tdm:policy esperado={expected.policy_url!r} leído={declaration.policy_url!r}"
        )

    return {"status": "PASS" if not issues else "FAIL", "issues": issues}
