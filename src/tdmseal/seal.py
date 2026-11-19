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
from tdmseal.iscc.content import compute_content_iscc
from tdmseal.iscc.xmp import write_declared_iscc
from tdmseal.models import SealResult
from tdmseal.pdf.docinfo import restore_inherited_info
from tdmseal.pdf.inspector import inspect_pdf, read_document_xmp_bytes
from tdmseal.pdf.integrity import compare_docinfo, compare_non_metadata_invariants
from tdmseal.pdf.writer import create_output_path, save_pdf, write_document_xmp_bytes
from tdmseal.validation.qpdf_validator import qpdf_check
from tdmseal.validation.tdmrep_validator import verify_tdmrep_by_rereading
from tdmseal.validation.verapdf_validator import run_verapdf
from tdmseal.xmp.parser import find_rdf_root, parse_xmp
from tdmseal.xmp.pdfa_extension import (
    merge_iscc_extension_schema,
    merge_tdmrep_extension_schema,
)
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
    validations: dict = {}

    iscc_input = None
    if config.compute_iscc:
        iscc_input = _safe_content_iscc(input_path, warnings)
        if iscc_input is not None:
            warnings.extend(iscc_input.warnings)

    try:
        with pikepdf.open(input_path) as pdf:
            xmp_bytes = read_document_xmp_bytes(pdf)
            xmp_tree = parse_xmp(xmp_bytes)
            rdf_root = find_rdf_root(xmp_tree)

            operation = write_tdmrep(rdf_root, config.policy)

            if iscc_input is not None:
                write_declared_iscc(
                    rdf_root,
                    content_code=iscc_input.text_code,
                    source_iscc=iscc_input.iscc,
                    source_datahash=iscc_input.datahash,
                )

            if before.pdfa_part in (1, 2, 3):
                merge_tdmrep_extension_schema(rdf_root)
                if iscc_input is not None:
                    merge_iscc_extension_schema(rdf_root)

            new_xmp_bytes = serialize_xmp(xmp_tree)
            write_document_xmp_bytes(pdf, new_xmp_bytes)

            if restore_inherited_info(pdf, input_path):
                warnings.append(
                    "El último tráiler del PDF no declaraba /Info (actualización "
                    "incremental); se volvió a enlazar el diccionario Info heredado "
                    "para no perder título, autor ni asunto."
                )

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

    docinfo_result = compare_docinfo(input_path, output_path)
    validations["docinfo_preserved"] = docinfo_result["status"]
    if docinfo_result["status"] != "PASS":
        warnings.extend(docinfo_result["issues"])

    after = inspect_pdf(output_path)

    iscc_output = None
    iscc_ok = True
    if iscc_input is not None:
        iscc_output = _safe_content_iscc(output_path, warnings)
        reread = verify_declared_iscc(after.declared_iscc, iscc_input)
        validations["iscc_xmp_re_read"] = reread["status"]
        warnings.extend(reread["issues"])
        if iscc_input.text_code is None or iscc_output is None:
            validations["iscc_content_stable"] = "SKIPPED"
        elif iscc_output.text_code == iscc_input.text_code:
            validations["iscc_content_stable"] = "PASS"
        else:
            validations["iscc_content_stable"] = "FAIL"
            warnings.append(
                "El Text-Code del archivo sellado no coincide con el del original: "
                "el texto extraíble cambió al sellar."
            )
        iscc_ok = reread["status"] == "PASS" and validations["iscc_content_stable"] != "FAIL"

    status = "success"
    if (
        tdm_result["status"] != "PASS"
        or integrity_result["status"] != "PASS"
        or docinfo_result["status"] != "PASS"
        or not iscc_ok
    ):
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
        iscc_input=iscc_input,
        iscc_output=iscc_output,
    )


def _safe_content_iscc(path: Path, warnings: list[str]):
    """Calcula el ISCC completo; si falla, avisa y devuelve None (el sellado sigue)."""
    try:
        return compute_content_iscc(path)
    except Exception as exc:  # noqa: BLE001 — el ISCC es un añadido, no debe tumbar el sello
        warnings.append(f"No se pudo calcular el ISCC de {path.name}: {exc}")
        return None


def verify_declared_iscc(declared, expected) -> dict:
    """Compara las propiedades tdmseal:iscc* releídas con lo calculado del original.

    Si el archivo ya traía una procedencia de un sellado anterior del mismo
    contenido, `isccSource` conserva ese valor (ver `iscc/xmp.py`), así que
    solo se exige que exista.
    """
    if declared is None:
        return {"status": "FAIL", "issues": ["no se encontró el ISCC en el XMP releído"]}
    issues = []
    if expected.text_code and declared.content_code != expected.text_code:
        issues.append(
            f"tdmseal:isccContentCode esperado={expected.text_code} leído={declared.content_code}"
        )
    if not declared.source_iscc:
        issues.append("falta tdmseal:isccSource en el XMP releído")
    return {"status": "PASS" if not issues else "FAIL", "issues": issues}
