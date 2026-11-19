"""Punto de entrada común para PDF y EPUB (CLI y GUI usan solo esto)."""

from __future__ import annotations

from pathlib import Path

from tdmseal.config import SealConfig
from tdmseal.discovery import document_kind
from tdmseal.epub.inspector import inspect_epub
from tdmseal.epub.seal import seal_epub
from tdmseal.models import EPUBInfo, PDFInfo, SealResult
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.seal import seal_pdf


def inspect_document(path: Path) -> PDFInfo | EPUBInfo:
    """Inspecciona un PDF o un EPUB según su extensión. Lanza TDMSealError si falla."""
    if document_kind(path) == "epub":
        return inspect_epub(path)
    return inspect_pdf(path)


def seal_document(path: Path, config: SealConfig) -> SealResult:
    """Sella un PDF o un EPUB según su extensión.

    Las preferencias AIPREF de `config` se registran en el resultado (y por
    tanto en el reporte), con un aviso si contradicen la reserva TDMRep.
    """
    if document_kind(path) == "epub":
        result = seal_epub(path, config)
    else:
        result = seal_pdf(path, config)
    if config.aipref is not None:
        result.aipref = config.aipref
        result.warnings.extend(config.aipref.check_consistency(config.policy.reservation))
    return result
