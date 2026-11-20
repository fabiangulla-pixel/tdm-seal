"""Validación con las herramientas reales (veraPDF, EPUBCheck, Ghostscript).

Se omiten si no están instaladas. En el equipo de desarrollo se instalan con
`scripts\\instalar_herramientas.ps1` en `%LOCALAPPDATA%\\TDMSeal\\tools`.
Estas pruebas detectaron un error real que los dobles no veían: el aviso
visible de EPUB 2 usaba `<section>`, que XHTML 1.1 no admite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tdmseal import tools
from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.models import TDMPolicy
from tdmseal.notice import NoticeOptions
from tdmseal.validation.epubcheck_validator import epubcheck_errors
from tdmseal.validation.verapdf_validator import run_verapdf

pytestmark = pytest.mark.real_tools

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")
NOTICE = NoticeOptions("Editorial Ejemplo", "derechos@ejemplo.org", POLICY.policy_url)


def _epubcheck():
    cmd = tools.find_epubcheck()
    if cmd is None:
        pytest.skip("EPUBCheck no instalado")
    return cmd


def _ghostscript() -> Path:
    gs = tools.tools_dir() / "gs"
    exe = gs / "bin" / "gswin64c.exe"
    if not exe.exists() or tools.find_verapdf() is None:
        pytest.skip("Ghostscript o veraPDF no instalados")
    return gs


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("with_notice", [False, True])
def test_sealed_epub_passes_epubcheck(make_epub, version, with_notice):
    cmd = _epubcheck()
    path = make_epub(f"v{version}_{with_notice}.epub", version=version)
    config = SealConfig(policy=POLICY, notice=NOTICE if with_notice else None)

    result = seal_document(path, config)

    assert result.status == "success", result.warnings
    assert result.validations["epubcheck"] == "PASS"
    assert epubcheck_errors(path, cmd) == set()  # el fixture es válido
    assert epubcheck_errors(result.output_path, cmd) == set()


@pytest.mark.parametrize("part", [1, 2])
def test_sealed_real_pdfa_stays_compliant(make_text_pdf, tmp_path, part):
    gs = _ghostscript()
    icc = (gs / "iccprofiles" / "srgb.icc").as_posix()
    pdfa_def = (gs / "lib" / "PDFA_def.ps").read_text(encoding="latin-1")
    def_path = tmp_path / "PDFA_def.ps"
    def_path.write_text(pdfa_def.replace("(srgb.icc)", f"({icc})"), encoding="latin-1")
    src = make_text_pdf("src.pdf", title="Libro PDF/A")
    pdfa = tmp_path / f"libro_pdfa{part}.pdf"
    subprocess.run(
        [
            str(gs / "bin" / "gswin64c.exe"),
            f"-dPDFA={part}",
            f"--permit-file-read={(gs / 'iccprofiles').as_posix()}/",
            "-dBATCH",
            "-dNOPAUSE",
            "-dNOOUTERSAVE",
            "-sColorConversionStrategy=RGB",
            "-sDEVICE=pdfwrite",
            "-dPDFACompatibilityPolicy=1",
            f"-sOutputFile={pdfa}",
            str(def_path),
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    assert run_verapdf(pdfa)["status"] == "PASS"  # el original es PDF/A conforme

    result = seal_document(pdfa, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["verapdf"] == "PASS"
