"""Aviso visible opcional: página final (PDF) o documento final (EPUB)."""

from __future__ import annotations

import zipfile

import pikepdf
import pytest
from click.testing import CliRunner
from lxml import etree

import tdmseal.cli as cli_module
from tdmseal.appconfig import AppDefaults
from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.errors import TDM023_NOTICE_NOT_ALLOWED
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.notice import (
    NOTICE_TITLE_EN,
    NOTICE_TITLE_ES,
    NoticeOptions,
    notice_from_publisher,
)
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.validation import epubcheck_validator

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")
NOTICE = NoticeOptions(
    editorial="Editorial Universidad Ejemplo",
    contact="derechos@editorial.example.edu",
    policy_url=POLICY.policy_url,
)


@pytest.fixture(autouse=True)
def no_epubcheck(monkeypatch):
    monkeypatch.setattr(epubcheck_validator, "_command", lambda: None)


def _config(**kw) -> SealConfig:
    return SealConfig(policy=POLICY, notice=NOTICE, **kw)


def _page_text(path, index: int) -> str:
    pdfium = pytest.importorskip("pypdfium2")
    doc = pdfium.PdfDocument(str(path))
    try:
        # Los títulos largos ocupan varias líneas: se normalizan los saltos.
        return " ".join(doc[index].get_textpage().get_text_bounded().split())
    finally:
        doc.close()


# ---- PDF ------------------------------------------------------------------------


def test_pdf_gets_one_final_page_and_existing_pages_untouched(make_text_pdf):
    path = make_text_pdf("libro.pdf")
    with pikepdf.open(path) as pdf:
        original_streams = [bytes(p.Contents.read_bytes()) for p in pdf.pages]

    result = seal_document(path, _config())

    assert result.status == "success", result.warnings
    assert result.validations["non_metadata_invariants"] == "PASS"
    with pikepdf.open(result.output_path) as pdf:
        assert len(pdf.pages) == len(original_streams) + 1
        for page, original in zip(pdf.pages, original_streams, strict=False):
            assert bytes(page.Contents.read_bytes()) == original
    last = _page_text(result.output_path, len(original_streams))
    assert NOTICE_TITLE_ES in last
    assert NOTICE_TITLE_EN in last  # versión en inglés también presente
    assert "Editorial Universidad Ejemplo" in last


def test_pdf_notice_is_idempotent(make_text_pdf):
    first = seal_document(make_text_pdf("libro.pdf"), _config())
    second = seal_document(first.output_path, _config())

    with pikepdf.open(first.output_path) as a, pikepdf.open(second.output_path) as b:
        assert len(b.pages) == len(a.pages)
    assert any("ya tenía la página de aviso" in w for w in second.warnings)


def test_default_seal_never_adds_pages(make_text_pdf):
    path = make_text_pdf("libro.pdf")
    result = seal_document(path, SealConfig(policy=POLICY))

    assert inspect_pdf(result.output_path).page_count == inspect_pdf(path).page_count


@pytest.mark.parametrize("part", [1, 2, 3, 4])
def test_pdfa_is_rejected(make_pdfa, part):
    path = make_pdfa(f"a{part}.pdf", part=part, conformance="B" if part < 4 else None)

    result = seal_document(path, _config())

    assert result.status == "skipped"
    assert result.reason_code == TDM023_NOTICE_NOT_ALLOWED
    assert not path.with_name(f"a{part}_TDM.pdf").exists()


def test_pdfua_is_rejected(make_pdf_with_xmp):
    xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/" '
        b'pdfuaid:part="1"/></rdf:RDF></x:xmpmeta>'
    )
    result = seal_document(make_pdf_with_xmp("ua.pdf", xmp), _config())

    assert result.reason_code == TDM023_NOTICE_NOT_ALLOWED


def test_signed_pdf_rejected_even_with_force_signed(make_signed_pdf):
    result = seal_document(make_signed_pdf(), _config(force_signed=True))

    assert result.reason_code == TDM023_NOTICE_NOT_ALLOWED


def test_tagged_pdf_notice_is_artifact(make_text_pdf, tmp_path):
    path = make_text_pdf("tagged.pdf")
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.Root.StructTreeRoot = pdf.make_indirect(
            pikepdf.Dictionary(Type=pikepdf.Name("/StructTreeRoot"))
        )
        pdf.save(path)

    result = seal_document(path, _config())

    assert result.status == "success"
    assert any("Artifact" in w for w in result.warnings)
    with pikepdf.open(result.output_path) as pdf:
        assert bytes(pdf.pages[-1].Contents.read_bytes()).startswith(b"/Artifact BMC")


def test_notice_with_iscc_declares_original_text_code(make_text_pdf):
    pytest.importorskip("pypdfium2")
    from tdmseal.iscc.content import compute_content_iscc

    path = make_text_pdf("libro.pdf", title="Derechos y minería")
    original = compute_content_iscc(path)

    result = seal_document(path, _config(compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["iscc_content_stable"] == "SKIPPED"
    assert inspect_pdf(result.output_path).declared_iscc.content_code == original.text_code


def test_notice_requires_publisher_data():
    with pytest.raises(ValueError):
        notice_from_publisher(PublisherInfo(), None)
    with pytest.raises(ValueError):
        notice_from_publisher(PublisherInfo(name="Ed."), None)
    assert notice_from_publisher(PublisherInfo(name="Ed.", website="https://e.x"), None)


# ---- EPUB -----------------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 3])
def test_epub_gets_final_document_in_spine(make_epub, version):
    path = make_epub(f"v{version}.epub", version=version)

    result = seal_document(path, _config())

    assert result.status == "success", result.warnings
    assert result.validations["container_unchanged"] == "PASS"
    with zipfile.ZipFile(result.output_path) as zf, zipfile.ZipFile(path) as orig:
        names = zf.namelist()
        assert names[-1] == "OEBPS/tdmseal-aviso.xhtml"
        notice = etree.fromstring(zf.read("OEBPS/tdmseal-aviso.xhtml"))
        assert NOTICE_TITLE_ES in etree.tostring(notice, encoding="unicode")
        opf = etree.fromstring(zf.read("OEBPS/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        assert opf.findall("opf:spine/opf:itemref", ns)[-1].get("idref") == "tdmseal-aviso"
        for info in orig.infolist():
            if info.filename != "OEBPS/content.opf":
                assert zf.getinfo(info.filename).CRC == info.CRC


def test_epub_notice_is_idempotent(make_epub):
    first = seal_document(make_epub(), _config())
    second = seal_document(first.output_path, _config())

    with zipfile.ZipFile(second.output_path) as zf:
        assert zf.namelist().count("OEBPS/tdmseal-aviso.xhtml") == 1
    assert any("ya tenía el documento de aviso" in w for w in second.warnings)


def test_fixed_layout_epub_is_rejected(make_epub):
    path = make_epub(
        "fxl.epub",
        package_prefix="rendition: http://www.idpf.org/vocab/rendition/#",
        extra_meta='    <meta property="rendition:layout">pre-paginated</meta>\n',
    )

    result = seal_document(path, _config())

    assert result.reason_code == TDM023_NOTICE_NOT_ALLOWED
    assert not path.with_name("fxl_TDM.epub").exists()


# ---- CLI ------------------------------------------------------------------------


def test_cli_visible_notice_requires_publisher(make_text_pdf, monkeypatch):
    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())

    out = CliRunner().invoke(cli_module.main, ["seal", str(make_text_pdf()), "--visible-notice"])

    assert out.exit_code == 2
    assert "nombre de la editorial" in out.output


def test_cli_visible_notice_adds_page(make_text_pdf, monkeypatch):
    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())
    path = make_text_pdf("libro.pdf")

    out = CliRunner().invoke(
        cli_module.main,
        [
            "seal",
            str(path),
            "--visible-notice",
            "--publisher-name",
            "Editorial Ejemplo",
            "--publisher-email",
            "derechos@ejemplo.org",
        ],
    )

    assert out.exit_code == 0, out.output
    assert inspect_pdf(path.with_name("libro_TDM.pdf")).page_count == 3
