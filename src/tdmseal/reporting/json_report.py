"""Construcción del reporte JSON de auditoría (sección 17 de la especificación)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tdmseal import __version__
from tdmseal.models import PDFInfo, SealResult


def _pdf_info_to_dict(info: PDFInfo | None) -> dict | None:
    if info is None:
        return None
    pdfa = None
    if info.pdfa_part is not None:
        conformance = info.pdfa_conformance or ""
        pdfa = f"PDF/A-{info.pdfa_part}{conformance.lower()}"
    return {
        "file": str(info.path),
        "sha256": info.sha256,
        "pdf_version": info.pdf_version,
        "page_count": info.page_count,
        "pdfa": pdfa,
        "pdfua_part": info.pdfua_part,
        "encrypted": info.encrypted,
        "signed": info.signed,
        "has_xmp": info.has_xmp,
        "tdm_reservation": info.tdm.reservation,
        "tdm_policy": info.tdm.policy_url,
    }


def build_report(result: SealResult) -> dict:
    return {
        "tool": "TDM Seal",
        "tool_version": __version__,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": result.status,
        "operation": result.operation,
        "reason_code": result.reason_code,
        "input": _pdf_info_to_dict(result.before),
        "output": _pdf_info_to_dict(result.after),
        "validation": result.validations,
        "warnings": result.warnings,
        "errors": result.errors,
    }


def write_report(result: SealResult, path: Path) -> None:
    report = build_report(result)
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
