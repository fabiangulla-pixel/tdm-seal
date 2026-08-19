"""Orquestador principal: sella un único PDF con una declaración TDMRep.

Implementa el algoritmo de la sección 13 de la especificación. Prioridades,
en este orden: preservar el PDF, no tocar PDF firmados por defecto, insertar
TDMRep solo en el XMP de nivel de documento, preservar todo lo demás, validar
el resultado después de escribirlo.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf

from tdmseal.config import SealConfig
from tdmseal.errors import TDMSealError
from tdmseal.models import SealResult
from tdmseal.pdf.inspector import inspect_pdf, read_document_xmp_bytes
from tdmseal.pdf.integrity import compare_non_metadata_invariants
from tdmseal.pdf.writer import create_output_path, save_pdf, write_document_xmp_bytes
from tdmseal.validation.qpdf_validator import qpdf_check
from tdmseal.validation.tdmrep_validator import verify_tdmrep_by_rereading
from tdmseal.validation.verapdf_validator import run_verapdf
from tdmseal.xmp.parser import find_rdf_root, parse_xmp
from tdmseal.xmp.serializer import serialize_xmp
from tdmseal.xmp.tdmrep import write_tdmrep


def seal_pdf(input_path: Path, config: SealConfig) -> SealResult:
    """Sella un único PDF. Nunca lanza excepción: los fallos se reflejan en el resultado."""
    input_path = Path(input_path)

    try:
        before = inspect_pdf(input_path)
    except TDMSealError as exc:
        return SealResult(
            input_path=input_path,
            output_path=None,
            status="failed",
            reason_code=exc.code,
            errors=[exc.message],
        )

    if before.signed and not config.force_signed:
        return SealResult(
            input_path=input_path,
            output_path=None,
            status="skipped",
            reason_code="TDM021",
            before=before,
            errors=[
                "El PDF contiene una o más firmas digitales. Modificar sus metadatos "
                "puede invalidarlas. El archivo no será alterado. Aplique TDM Seal "
                "antes de firmar el documento."
            ],
        )

    if before.encrypted and not config.allow_encrypted:
        return SealResult(
            input_path=input_path,
            output_path=None,
            status="skipped",
            reason_code="TDM020",
            before=before,
            errors=["El PDF está cifrado. El archivo no será alterado por defecto."],
        )

    output_path = create_output_path(input_path, config.output_suffix)
    if output_path.exists():
        return SealResult(
            input_path=input_path,
            output_path=output_path,
            status="failed",
            reason_code="TDM050",
            before=before,
            errors=[f"La salida ya existe: {output_path}"],
        )

    warnings: list[str] = []
    try:
        with pikepdf.open(input_path) as pdf:
            xmp_bytes = read_document_xmp_bytes(pdf)
            xmp_tree = parse_xmp(xmp_bytes)
            rdf_root = find_rdf_root(xmp_tree)

            operation = write_tdmrep(rdf_root, config.policy)

            new_xmp_bytes = serialize_xmp(xmp_tree)
            write_document_xmp_bytes(pdf, new_xmp_bytes)

            save_pdf(pdf, output_path)
    except (pikepdf.PdfError, OSError) as exc:
        return SealResult(
            input_path=input_path,
            output_path=None,
            status="failed",
            reason_code="TDM002",
            before=before,
            errors=[f"No se pudo escribir el PDF sellado: {exc}"],
        )

    validations: dict = {}

    tdm_result = verify_tdmrep_by_rereading(output_path, config.policy)
    validations["xmp_re_read"] = tdm_result["status"]
    if tdm_result["status"] != "PASS":
        warnings.extend(tdm_result["issues"])

    if config.run_qpdf_check:
        qpdf_result = qpdf_check(output_path)
        validations["qpdf"] = qpdf_result["status"]
        if qpdf_result["status"] == "FAIL":
            warnings.extend(qpdf_result["issues"])

    if before.is_pdfa and config.run_verapdf:
        verapdf_result = run_verapdf(output_path)
        validations["verapdf"] = verapdf_result["status"]
        warnings.extend(verapdf_result["issues"])

    integrity_result = compare_non_metadata_invariants(input_path, output_path)
    validations["non_metadata_invariants"] = integrity_result["status"]
    if integrity_result["status"] != "PASS":
        warnings.extend(integrity_result["issues"])

    after = inspect_pdf(output_path)

    status = "success"
    if tdm_result["status"] != "PASS" or integrity_result["status"] != "PASS":
        status = "failed"

    return SealResult(
        input_path=input_path,
        output_path=output_path,
        status=status,
        operation=operation,
        before=before,
        after=after,
        validations=validations,
        warnings=warnings,
    )
