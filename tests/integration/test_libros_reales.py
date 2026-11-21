"""Libros reales de la editorial (no versionados: tienen derechos reservados).

Se toman de `%LOCALAPPDATA%\\TDMSeal\\libros_prueba` (o `TDMSEAL_LIBROS_PRUEBA`),
fuera del repositorio. Cada PDF o EPUB de esa carpeta se sella en una copia
temporal y se comprueba lo que una editorial necesita saber:

- el sellado sale bien y la reserva se lee de vuelta;
- (PDF) cada página original queda idéntica al píxel;
- (PDF) el ISCC coincide con iscc-sdk, si su entorno de referencia existe;
- (PDF) firmado de verdad con pyHanko, se rechaza por defecto y con
  --force-signed la firma sigue válida;
- (PDF) cifrado con permisos, la copia sigue cifrada con los mismos permisos.

Si la carpeta no existe o está vacía, las pruebas se omiten.
Primer libro: «Los días biches» (164 pp., 120×165 mm, sin XMP, con /Info
heredado de una actualización incremental de MuPDF), 21-nov-2026.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pikepdf
import pytest

from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.models import TDMPolicy
from tdmseal.tools import tools_dir

pytestmark = pytest.mark.real_tools

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")
HELPER = Path(__file__).with_name("pyhanko_helper.py")


def _books_dir() -> Path:
    configured = os.environ.get("TDMSEAL_LIBROS_PRUEBA")
    return Path(configured) if configured else tools_dir().parent / "libros_prueba"


def _books(suffix: str) -> list[Path]:
    folder = _books_dir()
    return sorted(folder.glob(f"*{suffix}")) if folder.is_dir() else []


def _ids(paths: list[Path]) -> list[str]:
    return [p.stem[:30] for p in paths]


PDFS = _books(".pdf")
EPUBS = _books(".epub")
needs_pdf = pytest.mark.skipif(not PDFS, reason="sin PDF reales en libros_prueba")


def _venv_python(name: str) -> Path | None:
    exe = Path.home() / ".venvs" / name / "Scripts" / "python.exe"
    return exe if exe.exists() else None


def _copy(book: Path, tmp_path: Path) -> Path:
    target = tmp_path / ("libro" + book.suffix)
    shutil.copyfile(book, target)
    return target


def _page_hashes(path: Path, count: int) -> list[str]:
    pdfium = pytest.importorskip("pypdfium2")
    doc = pdfium.PdfDocument(str(path))
    try:
        return [
            hashlib.sha256(doc[i].render(scale=0.5).to_pil().tobytes()).hexdigest()
            for i in range(count)
        ]
    finally:
        doc.close()


@needs_pdf
@pytest.mark.parametrize("book", PDFS, ids=_ids(PDFS))
def test_real_pdf_sealed_pixel_identical(book, tmp_path):
    from tdmseal.pdf.inspector import inspect_pdf

    path = _copy(book, tmp_path)
    with pikepdf.open(path) as pdf:
        pages = len(pdf.pages)

    result = seal_document(path, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", (result.errors, result.warnings)
    failed = {k: v for k, v in result.validations.items() if v == "FAIL"}
    assert not failed, result.warnings
    assert inspect_pdf(result.output_path).tdm.reservation == 1
    assert _page_hashes(path, pages) == _page_hashes(result.output_path, pages)


@needs_pdf
@pytest.mark.parametrize("book", PDFS, ids=_ids(PDFS))
def test_real_pdf_iscc_matches_iscc_sdk(book):
    sdk = _venv_python("iscc-sdk-ref")
    if sdk is None:
        pytest.skip("iscc-sdk de referencia no instalado")
    from tdmseal.iscc.content import compute_content_iscc

    ours = compute_content_iscc(book).iscc
    theirs = subprocess.run(
        [
            str(sdk),
            "-c",
            "import sys, iscc_sdk as i; print(i.code_iscc(sys.argv[1]).iscc)",
            str(book),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    ).stdout.strip()

    assert ours == theirs


@needs_pdf
@pytest.mark.parametrize("book", PDFS, ids=_ids(PDFS))
def test_real_pdf_signed_keeps_signature(book, tmp_path):
    hanko = _venv_python("pyhanko-ref")
    if hanko is None:
        pytest.skip("pyHanko de referencia no instalado")
    keys = tmp_path / "claves"
    signed = tmp_path / "firmado.pdf"
    subprocess.run(
        [str(hanko), "-I", str(HELPER), "certify", str(book), str(signed), str(keys)],
        check=True,
        capture_output=True,
        timeout=300,
    )

    refused = seal_document(signed, SealConfig(policy=POLICY))
    forced = seal_document(signed, SealConfig(policy=POLICY, force_signed=True))

    assert refused.reason_code == "TDM021"
    assert forced.status == "success", (forced.errors, forced.warnings)
    detail = subprocess.run(
        [str(hanko), "-I", str(HELPER), "detail", str(forced.output_path), str(keys)],
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    ).stdout
    assert "intacta=True valida=True" in detail
    assert "veredicto=True" in detail


@needs_pdf
@pytest.mark.parametrize("book", PDFS, ids=_ids(PDFS))
def test_real_pdf_encrypted_stays_protected(book, tmp_path):
    enc = tmp_path / "cifrado.pdf"
    with pikepdf.open(book) as pdf:
        pdf.save(
            enc,
            encryption=pikepdf.Encryption(
                owner="propietario", user="", allow=pikepdf.Permissions(extract=False)
            ),
        )

    result = seal_document(enc, SealConfig(policy=POLICY, allow_encrypted=True))

    assert result.status == "success", (result.errors, result.warnings)
    with pikepdf.open(result.output_path) as out:
        assert out.is_encrypted
        assert not out.allow.extract


@pytest.mark.skipif(not EPUBS, reason="sin EPUB reales en libros_prueba")
@pytest.mark.parametrize("book", EPUBS, ids=_ids(EPUBS))
def test_real_epub_sealed(book, tmp_path):
    result = seal_document(_copy(book, tmp_path), SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", (result.errors, result.warnings)
    failed = {k: v for k, v in result.validations.items() if v == "FAIL"}
    assert not failed, result.warnings
