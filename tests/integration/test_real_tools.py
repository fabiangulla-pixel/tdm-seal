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
from tdmseal.samples import SAMPLE_TEXT, build_text_pdf
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


def _pdfa_from(gs: Path, tmp_path: Path, part: int) -> Path:
    """PDF/A-`part`b real generado con Ghostscript a partir de un PDF de texto."""
    icc = (gs / "iccprofiles" / "srgb.icc").as_posix()
    pdfa_def = (gs / "lib" / "PDFA_def.ps").read_text(encoding="latin-1")
    def_path = tmp_path / "PDFA_def.ps"
    def_path.write_text(pdfa_def.replace("(srgb.icc)", f"({icc})"), encoding="latin-1")
    src = build_text_pdf(tmp_path / "pdfa_src.pdf", SAMPLE_TEXT, title="Libro PDF/A")
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
    return pdfa


@pytest.mark.parametrize("part", [1, 2, 3])
def test_sealed_real_pdfa_stays_compliant(tmp_path, part):
    pdfa = _pdfa_from(_ghostscript(), tmp_path, part)
    assert run_verapdf(pdfa)["status"] == "PASS"  # el original es PDF/A conforme

    result = seal_document(pdfa, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["verapdf"] == "PASS"


def test_sealed_pdfa3_with_attachment_stays_compliant(tmp_path):
    """PDF/A-3b con un XML adjunto (caso factura electrónica / datos asociados)."""
    import pikepdf

    gs = _ghostscript()
    base = _pdfa_from(gs, tmp_path, 3)
    path = tmp_path / "pdfa3_adjunto.pdf"
    with pikepdf.open(base) as pdf:
        spec = pikepdf.AttachedFileSpec(
            pdf,
            b"<?xml version='1.0'?><datos><isbn>9789580000006</isbn></datos>",
            description="Datos asociados",
            mime_type="text/xml",
            relationship=pikepdf.Name.Data,
            mod_date="D:20261121000000Z",
        )
        pdf.attachments["datos.xml"] = spec
        pdf.Root.AF = pikepdf.Array([spec.obj])
        pdf.save(path)
    assert run_verapdf(path)["status"] == "PASS"  # el original es PDF/A-3 conforme

    result = seal_document(path, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["verapdf"] == "PASS"
    assert result.validations["non_metadata_invariants"] == "PASS"


UA_XMP = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">Libro accesible</rdf:li></rdf:Alt></dc:title>
   <pdfuaid:part>1</pdfuaid:part>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>""".encode()


def _build_pdfua(gs: Path, src: Path, out: Path) -> Path:
    """PDF/UA-1 real: Ghostscript incrusta las fuentes y pikepdf etiqueta el contenido.

    Cada página queda envuelta en un único párrafo (`/P` con MCID 0) colgado de
    un `Document` en el árbol de estructura; más Lang, MarkInfo, título
    mostrado y `pdfuaid:part=1`. veraPDF lo da por conforme con `--flavour ua1`.
    """
    import pikepdf

    base = out.with_name("base_" + out.name)
    subprocess.run(
        [
            str(gs / "bin" / "gswin64c.exe"),
            "-dBATCH",
            "-dNOPAUSE",
            "-dQUIET",
            "-sDEVICE=pdfwrite",
            f"-sOutputFile={base}",
            "-c",
            "<</NeverEmbed [ ]>> setdistillerparams",  # incrustar también Helvetica
            "-f",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    with pikepdf.open(base) as pdf:
        struct_root = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot))
        doc = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name.StructElem, S=pikepdf.Name.Document, P=struct_root)
        )
        kids, nums = pikepdf.Array(), pikepdf.Array()
        for i, page in enumerate(pdf.pages):
            contents = page.obj.Contents
            streams = contents if isinstance(contents, pikepdf.Array) else [contents]
            data = b"".join(s.read_bytes() for s in streams)
            page.obj.Contents = pdf.make_stream(b"/P <</MCID 0>> BDC\n" + data + b"\nEMC\n")
            page.obj.StructParents = i
            para = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.StructElem, S=pikepdf.Name.P, P=doc, Pg=page.obj, K=0
                )
            )
            kids.append(para)
            nums.extend([i, pikepdf.Array([para])])
        doc.K = kids
        struct_root.K = doc
        struct_root.ParentTree = pdf.make_indirect(pikepdf.Dictionary(Nums=nums))
        struct_root.ParentTreeNextKey = len(pdf.pages)
        pdf.Root.StructTreeRoot = struct_root
        pdf.Root.MarkInfo = pikepdf.Dictionary(Marked=True)
        pdf.Root.Lang = pikepdf.String("es-CO")
        pdf.Root.ViewerPreferences = pikepdf.Dictionary(DisplayDocTitle=True)
        pdf.docinfo["/Title"] = "Libro accesible"
        meta = pikepdf.Stream(pdf, UA_XMP)
        meta.Type, meta.Subtype = pikepdf.Name.Metadata, pikepdf.Name.XML
        pdf.Root.Metadata = meta
        pdf.save(out)
    return out


def test_sealed_real_pdfua_stays_compliant(make_text_pdf, tmp_path):
    gs = _ghostscript()
    pdfua = _build_pdfua(gs, make_text_pdf("src.pdf"), tmp_path / "libro_ua.pdf")
    assert run_verapdf(pdfua, flavour="ua1")["status"] == "PASS"  # el original es PDF/UA-1

    result = seal_document(pdfua, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["verapdf_ua"] == "PASS"
    assert "verapdf" not in result.validations  # no es PDF/A


def test_visible_notice_refused_on_real_pdfua(make_text_pdf, tmp_path):
    """El aviso visible rompería PDF/UA: el archivo se omite (TDM023) y no se escribe nada."""
    gs = _ghostscript()
    pdfua = _build_pdfua(gs, make_text_pdf("src.pdf"), tmp_path / "libro_ua.pdf")

    result = seal_document(pdfua, SealConfig(policy=POLICY, notice=NOTICE))

    assert result.status == "skipped"
    assert result.reason_code == "TDM023"
    assert any("PDF/UA" in e for e in result.errors)
    assert result.output_path is None
    assert not (tmp_path / "libro_ua_TDM.pdf").exists()
