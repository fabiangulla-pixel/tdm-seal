"""Construcción del reporte JSON de auditoría (sección 17 de la especificación)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tdmseal import __version__
from tdmseal.models import EPUBInfo, PDFInfo, PublisherInfo, SealResult


def _publisher_to_dict(publisher: PublisherInfo | None) -> dict | None:
    if publisher is None or publisher.is_empty():
        return None
    return {
        "name": publisher.name,
        "acronym": publisher.acronym,
        "website": publisher.website,
        "rights_email": publisher.rights_email,
    }


def _pdf_info_to_dict(info: PDFInfo | EPUBInfo | None) -> dict | None:
    if info is None:
        return None
    if isinstance(info, EPUBInfo):
        return {
            "file": str(info.path),
            "format": "epub",
            "sha256": info.sha256,
            "iscc": info.iscc,
            "epub_version": info.epub_version,
            "opf_path": info.opf_path,
            "drm": info.drm,
            "obfuscated_fonts": info.obfuscated_fonts,
            "mimetype_ok": info.mimetype_ok,
            "tdm_reservation": info.tdm.reservation,
            "tdm_policy": info.tdm.policy_url,
            "declared_iscc": info.declared_iscc.to_dict() if info.declared_iscc else None,
        }
    pdfa = None
    if info.pdfa_part is not None:
        conformance = info.pdfa_conformance or ""
        pdfa = f"PDF/A-{info.pdfa_part}{conformance.lower()}"
    return {
        "file": str(info.path),
        "format": "pdf",
        "sha256": info.sha256,
        "iscc": info.iscc,
        "pdf_version": info.pdf_version,
        "page_count": info.page_count,
        "pdfa": pdfa,
        "pdfua_part": info.pdfua_part,
        "encrypted": info.encrypted,
        "signed": info.signed,
        "has_xmp": info.has_xmp,
        "tdm_reservation": info.tdm.reservation,
        "tdm_policy": info.tdm.policy_url,
        "declared_iscc": info.declared_iscc.to_dict() if info.declared_iscc else None,
    }


def _iscc_block(result: SealResult) -> dict | None:
    """Bloque ISCC del reporte (solo si se pidió con --iscc)."""
    if result.iscc_input is None and result.iscc_output is None:
        return None
    before = result.iscc_input
    after = result.iscc_output
    stable = None
    if before is not None and after is not None and before.text_code:
        stable = before.text_code == after.text_code
    return {
        "input": before.to_dict() if before else None,
        "output": after.to_dict() if after else None,
        "content_code_unchanged_by_sealing": stable,
    }


def build_report(result: SealResult, publisher: PublisherInfo | None = None) -> dict:
    return {
        "tool": "TDM Seal",
        "tool_version": __version__,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "publisher": _publisher_to_dict(publisher),
        "status": result.status,
        "operation": result.operation,
        "reason_code": result.reason_code,
        "input": _pdf_info_to_dict(result.before),
        "output": _pdf_info_to_dict(result.after),
        "iscc": _iscc_block(result),
        "aipref": result.aipref.to_report() if result.aipref is not None else None,
        "validation": result.validations,
        "warnings": result.warnings,
        "errors": result.errors,
    }


def write_report(result: SealResult, path: Path, publisher: PublisherInfo | None = None) -> None:
    report = build_report(result, publisher)
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
