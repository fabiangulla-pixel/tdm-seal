"""Inspección de un PDF: versión, PDF/A, PDF/UA, cifrado, firma, XMP y TDMRep."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pikepdf

from tdmseal.errors import TDM001_PDF_UNREADABLE, TDM020_ENCRYPTED, TDMSealError
from tdmseal.iscc import compute_iscc
from tdmseal.models import PDFInfo, TDMRepDeclaration
from tdmseal.pdf.encryption import is_encrypted
from tdmseal.pdf.signatures import has_digital_signature
from tdmseal.xmp.parser import find_rdf_root, find_simple_property, parse_xmp
from tdmseal.xmp.tdmrep import read_tdmrep

PDFAID_NS = "http://www.aiim.org/pdfa/ns/id/"
PDFUAID_NS = "http://www.aiim.org/pdfua/ns/id/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_document_xmp_bytes(pdf: pikepdf.Pdf) -> bytes | None:
    """Lee los bytes crudos del XMP de nivel de documento, si existe."""
    metadata_obj = pdf.Root.get("/Metadata")
    if metadata_obj is None:
        return None
    return bytes(metadata_obj.read_bytes())


def _detect_pdfa(rdf_root) -> tuple[int | None, str | None]:
    part_text = find_simple_property(rdf_root, PDFAID_NS, "part")
    conformance = find_simple_property(rdf_root, PDFAID_NS, "conformance")
    if part_text is None:
        return None, None
    try:
        part = int(part_text)
    except ValueError:
        part = None
    return part, conformance


def _detect_pdfua(rdf_root) -> int | None:
    part_text = find_simple_property(rdf_root, PDFUAID_NS, "part")
    if part_text is None:
        return None
    try:
        return int(part_text)
    except ValueError:
        return None


def inspect_pdf(path: Path) -> PDFInfo:
    """Inspecciona un PDF sin modificarlo. Lanza TDMSealError si no puede leerlo."""
    path = Path(path)
    try:
        pdf = pikepdf.open(path)
    except pikepdf.PasswordError as exc:
        msg = f"PDF cifrado, requiere contraseña: {path}"
        raise TDMSealError(TDM020_ENCRYPTED, msg) from exc
    except (pikepdf.PdfError, OSError) as exc:
        msg = f"No se pudo leer el PDF: {path} ({exc})"
        raise TDMSealError(TDM001_PDF_UNREADABLE, msg) from exc

    with pdf:
        xmp_bytes = read_document_xmp_bytes(pdf)
        if xmp_bytes:
            xmp_root = find_rdf_root(parse_xmp(xmp_bytes))
            pdfa_part, pdfa_conformance = _detect_pdfa(xmp_root)
            pdfua_part = _detect_pdfua(xmp_root)
            tdm = read_tdmrep(xmp_root)
        else:
            pdfa_part, pdfa_conformance = None, None
            pdfua_part = None
            tdm = TDMRepDeclaration(reservation=None, policy_url=None, present=False)

        return PDFInfo(
            path=path,
            pdf_version=str(pdf.pdf_version),
            page_count=len(pdf.pages),
            pdfa_part=pdfa_part,
            pdfa_conformance=pdfa_conformance,
            pdfua_part=pdfua_part,
            encrypted=is_encrypted(pdf),
            signed=has_digital_signature(pdf),
            has_xmp=xmp_bytes is not None,
            tdm=tdm,
            sha256=sha256_file(path),
            iscc=compute_iscc(path).iscc,
        )
