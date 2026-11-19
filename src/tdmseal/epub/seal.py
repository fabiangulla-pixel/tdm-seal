"""Orquestador del sellado de un EPUB (mismos invariantes que el de PDF).

1. Inspeccionar; omitir EPUB con DRM o recursos cifrados (TDM022).
2. Escribir en archivo nuevo `_TDM.epub`; nunca sobrescribir.
3. Cambiar solo el paquete OPF (tdm:reservation, tdm:policy y, con --iscc,
   el ISCC); copiar el resto del contenedor tal cual.
4. Releer y verificar; comprobar que el contenedor no cambió en nada más;
   EPUBCheck opcional.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from tdmseal.config import SealConfig
from tdmseal.epub.inspector import inspect_epub, read_opf_bytes
from tdmseal.epub.opf import parse_opf, serialize_opf, write_iscc, write_tdm
from tdmseal.epub.writer import compare_container, rewrite_epub
from tdmseal.errors import (
    TDM022_EPUB_DRM,
    TDM033_EPUB_CONTAINER_CHANGED,
    TDM034_EPUBCHECK_NEW_ERRORS,
    TDM050_OUTPUT_EXISTS,
    TDMSealError,
)
from tdmseal.models import SealResult
from tdmseal.pdf.writer import create_output_path
from tdmseal.validation.epubcheck_validator import run_epubcheck


def seal_epub(input_path: Path, config: SealConfig) -> SealResult:
    """Sella un EPUB. Nunca lanza excepción: los fallos se reflejan en el resultado."""
    # Import diferido: seal.py (PDF) importa este módulo para despachar.
    from tdmseal.seal import _safe_content_iscc, verify_declared_iscc

    input_path = Path(input_path)
    try:
        before = inspect_epub(input_path)
    except TDMSealError as exc:
        return SealResult(input_path, None, "failed", reason_code=exc.code, errors=[exc.message])

    if before.drm is not None:
        # --allow-encrypted no aplica a EPUB: sin la clave no hay forma segura de tocarlo.
        return SealResult(
            input_path,
            None,
            "skipped",
            reason_code=TDM022_EPUB_DRM,
            before=before,
            errors=[
                f"El EPUB tiene DRM o recursos cifrados ({before.drm}). No se puede leer "
                "ni modificar sin la clave. El archivo no será alterado."
            ],
        )

    output_path = create_output_path(input_path, config.output_suffix)
    if output_path.exists():
        return SealResult(
            input_path,
            output_path,
            "failed",
            reason_code=TDM050_OUTPUT_EXISTS,
            before=before,
            errors=[f"La salida ya existe: {output_path}"],
        )

    warnings: list[str] = []
    validations: dict = {}
    if before.obfuscated_fonts:
        warnings.append(
            f"El EPUB tiene {before.obfuscated_fonts} fuente(s) ofuscada(s) (no es DRM); "
            "se copian sin tocar."
        )

    iscc_input = None
    if config.compute_iscc:
        iscc_input = _safe_content_iscc(input_path, warnings)
        if iscc_input is not None:
            warnings.extend(iscc_input.warnings)

    try:
        original_opf = read_opf_bytes(input_path, before.opf_path)
        opf_root = parse_opf(original_opf)
        operation = write_tdm(opf_root, config.policy)
        if iscc_input is not None:
            write_iscc(
                opf_root,
                content_code=iscc_input.text_code,
                source_iscc=iscc_input.iscc,
                source_datahash=iscc_input.datahash,
            )
        new_opf = serialize_opf(opf_root, original_opf)
        repaired = rewrite_epub(input_path, output_path, {before.opf_path: new_opf})
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        if output_path.exists():
            output_path.unlink()
        return SealResult(
            input_path,
            None,
            "failed",
            reason_code="TDM002",
            before=before,
            errors=[f"No se pudo escribir el EPUB sellado: {exc}"],
        )
    if repaired:
        warnings.append(
            "La entrada 'mimetype' del original no era la primera o estaba comprimida "
            "(EPUB no conforme); en la salida se escribió primera y sin comprimir."
        )

    after = inspect_epub(output_path)

    tdm_issues = []
    if after.tdm.reservation != config.policy.reservation:
        tdm_issues.append(
            f"tdm:reservation esperado={config.policy.reservation} leído={after.tdm.reservation}"
        )
    if (config.policy.policy_url or None) != (after.tdm.policy_url or None):
        tdm_issues.append(
            f"tdm:policy esperado={config.policy.policy_url!r} leído={after.tdm.policy_url!r}"
        )
    validations["opf_re_read"] = "PASS" if not tdm_issues else "FAIL"
    warnings.extend(tdm_issues)

    container = compare_container(input_path, output_path, {before.opf_path})
    validations["container_unchanged"] = container["status"]
    warnings.extend(container["issues"])

    epubcheck = run_epubcheck(input_path, output_path)
    validations["epubcheck"] = epubcheck["status"]
    warnings.extend(epubcheck["issues"])

    iscc_output = None
    iscc_ok = True
    if iscc_input is not None:
        iscc_output = _safe_content_iscc(output_path, warnings)
        reread = verify_declared_iscc(after.declared_iscc, iscc_input)
        validations["iscc_opf_re_read"] = reread["status"]
        warnings.extend(reread["issues"])
        if iscc_input.text_code is None or iscc_output is None:
            validations["iscc_content_stable"] = "SKIPPED"
        elif iscc_output.text_code == iscc_input.text_code:
            validations["iscc_content_stable"] = "PASS"
        else:
            validations["iscc_content_stable"] = "FAIL"
            warnings.append("El Text-Code del EPUB sellado no coincide con el del original.")
        iscc_ok = reread["status"] == "PASS" and validations["iscc_content_stable"] != "FAIL"

    failed = (
        validations["opf_re_read"] != "PASS"
        or container["status"] != "PASS"
        or epubcheck["status"] == "FAIL"
        or not iscc_ok
    )
    reason = None
    if container["status"] != "PASS":
        reason = TDM033_EPUB_CONTAINER_CHANGED
    elif epubcheck["status"] == "FAIL":
        reason = TDM034_EPUBCHECK_NEW_ERRORS

    return SealResult(
        input_path=input_path,
        output_path=output_path,
        status="failed" if failed else "success",
        operation=operation,
        reason_code=reason,
        before=before,
        after=after,
        validations=validations,
        warnings=warnings,
        iscc_input=iscc_input,
        iscc_output=iscc_output,
    )
