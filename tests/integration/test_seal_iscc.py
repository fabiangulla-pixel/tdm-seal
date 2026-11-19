"""Sellado con ISCC (--iscc) y conservación del diccionario Info."""

from __future__ import annotations

import json

import pikepdf
import pytest
from click.testing import CliRunner

from tdmseal.cli import main as cli_main
from tdmseal.config import SealConfig
from tdmseal.iscc import content as content_mod
from tdmseal.iscc.content import NO_EXTRA_WARNING, compute_content_iscc
from tdmseal.iscc.xmp import ISCC_XMP_NS
from tdmseal.models import TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.reporting.json_report import build_report
from tdmseal.seal import seal_pdf

pytest.importorskip("pypdfium2")

POLICY = TDMPolicy(reservation=1, policy_url="https://editorial.example.edu/tdm/policy.jsonld")


def _xmp(path) -> bytes:
    with pikepdf.open(path) as pdf:
        return bytes(pdf.Root.Metadata.read_bytes())


def test_sealing_keeps_content_and_meta_codes_only_byte_codes_change(make_text_pdf):
    """Requisito central de la fase 1: el ISCC de contenido sobrevive al sellado."""
    pdf_path = make_text_pdf("libro.pdf", title="Derechos y minería")
    before = compute_content_iscc(pdf_path)

    result = seal_pdf(pdf_path, SealConfig(policy=POLICY, compute_iscc=True))
    after = compute_content_iscc(result.output_path)

    assert result.status == "success", result.warnings
    assert after.text_code == before.text_code
    assert after.meta_code == before.meta_code
    assert after.data_code != before.data_code
    assert after.instance_code != before.instance_code
    assert after.iscc != before.iscc
    assert result.validations["iscc_content_stable"] == "PASS"
    assert result.validations["iscc_xmp_re_read"] == "PASS"


def test_iscc_written_to_xmp_and_report(make_text_pdf):
    pdf_path = make_text_pdf("libro.pdf", title="Derechos y minería")
    original = compute_content_iscc(pdf_path)

    result = seal_pdf(pdf_path, SealConfig(policy=POLICY, compute_iscc=True))

    declared = inspect_pdf(result.output_path).declared_iscc
    assert declared.content_code == original.text_code
    assert declared.source_iscc == original.iscc
    assert declared.source_datahash == original.datahash

    report = build_report(result)
    assert report["iscc"]["input"]["iscc"] == original.iscc
    assert report["iscc"]["content_code_unchanged_by_sealing"] is True
    assert report["output"]["declared_iscc"]["content_code"] == original.text_code
    json.dumps(report)  # serializable


def test_without_iscc_flag_nothing_iscc_is_written(make_text_pdf):
    result = seal_pdf(make_text_pdf(), SealConfig(policy=POLICY))

    assert result.status == "success"
    assert ISCC_XMP_NS.encode() not in _xmp(result.output_path)
    assert build_report(result)["iscc"] is None


def test_resealing_sealed_file_keeps_original_source_iscc(make_text_pdf):
    pdf_path = make_text_pdf("libro.pdf", title="Derechos y minería")
    original = compute_content_iscc(pdf_path)
    first = seal_pdf(pdf_path, SealConfig(policy=POLICY, compute_iscc=True))

    second = seal_pdf(first.output_path, SealConfig(policy=POLICY, compute_iscc=True))

    assert second.status == "success", second.warnings
    declared = inspect_pdf(second.output_path).declared_iscc
    assert declared.source_iscc == original.iscc
    assert _xmp(second.output_path).count(b"isccSource>") == 2  # sin duplicados


def _declared_extension_namespaces(path) -> list[str]:
    from tdmseal.xmp.parser import parse_xmp

    tree = parse_xmp(_xmp(path))
    return [
        el.text.strip()
        for el in tree.iter("{http://www.aiim.org/pdfa/ns/schema#}namespaceURI")
        if el.text
    ]


def test_pdfa2_declares_iscc_namespace_in_extension_schema(make_pdfa):
    pdf_path = make_pdfa("pdfa2.pdf", part=2)
    config = SealConfig(policy=POLICY, compute_iscc=True, run_verapdf=False)

    first = seal_pdf(pdf_path, config)
    second = seal_pdf(first.output_path, config)  # idempotencia del esquema

    for result in (first, second):
        assert result.status == "success", result.warnings
        namespaces = _declared_extension_namespaces(result.output_path)
        assert namespaces.count(ISCC_XMP_NS) == 1
        assert namespaces.count("http://www.w3.org/ns/tdmrep/") == 1


def test_blank_pdf_seals_with_warning_and_skipped_stability(make_pdf):
    result = seal_pdf(make_pdf(), SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success"
    assert result.validations["iscc_content_stable"] == "SKIPPED"
    assert any("capa de texto" in w for w in result.warnings)
    assert inspect_pdf(result.output_path).declared_iscc.source_iscc


def test_without_extra_still_seals_and_warns(monkeypatch, make_text_pdf):
    monkeypatch.setattr(content_mod, "content_extra_available", lambda: False)

    result = seal_pdf(make_text_pdf(), SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success"
    assert NO_EXTRA_WARNING in result.warnings
    assert result.validations["iscc_content_stable"] == "SKIPPED"
    declared = inspect_pdf(result.output_path).declared_iscc
    assert declared.content_code is None
    assert declared.source_iscc


def test_iscc_failure_does_not_block_sealing(monkeypatch, make_text_pdf):
    import tdmseal.seal as seal_mod

    def boom(path):
        raise RuntimeError("pdfium no pudo abrirlo")

    monkeypatch.setattr(seal_mod, "compute_content_iscc", boom)

    result = seal_pdf(make_text_pdf(), SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success"
    assert any("No se pudo calcular el ISCC" in w for w in result.warnings)


# ---- Info heredado (bug real: el sellado borraba título y asunto) -------------


def test_sealing_preserves_inherited_info_dictionary(make_incremental_pdf):
    pdf_path = make_incremental_pdf(
        "mupdf.pdf", title="Los días biches", subject="Prueba para el autor"
    )

    result = seal_pdf(pdf_path, SealConfig(policy=POLICY))

    assert result.status == "success", result.warnings
    assert result.validations["docinfo_preserved"] == "PASS"
    assert any("Info heredado" in w for w in result.warnings)
    with pikepdf.open(result.output_path) as pdf:
        assert str(pdf.trailer.Info["/Title"]) == "Los días biches"
        assert str(pdf.trailer.Info["/Subject"]) == "Prueba para el autor"


def test_docinfo_loss_is_reported_as_failure(monkeypatch, make_incremental_pdf):
    import tdmseal.seal as seal_mod

    monkeypatch.setattr(seal_mod, "restore_inherited_info", lambda pdf, path: False)
    pdf_path = make_incremental_pdf("m.pdf")

    result = seal_pdf(pdf_path, SealConfig(policy=POLICY))

    assert result.status == "failed"
    assert result.validations["docinfo_preserved"] == "FAIL"


# ---- CLI --------------------------------------------------------------------


def test_cli_iscc_json(make_text_pdf):
    pdf_path = make_text_pdf("libro.pdf", title="Derechos y minería")

    out = CliRunner().invoke(cli_main, ["iscc", str(pdf_path), "--json"])

    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert data[str(pdf_path)]["iscc"] == compute_content_iscc(pdf_path).iscc


def test_cli_iscc_text_output(make_text_pdf):
    out = CliRunner().invoke(cli_main, ["iscc", str(make_text_pdf())])

    assert out.exit_code == 0, out.output
    assert "ISCC-CODE:" in out.output
    assert "Text-Code:" in out.output


def test_cli_seal_with_iscc_flag(make_text_pdf, monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    pdf_path = make_text_pdf("libro.pdf")

    out = CliRunner().invoke(cli_main, ["seal", str(pdf_path), "--reservation", "1", "--iscc"])

    assert out.exit_code == 0, out.output
    assert "ISCC original:" in out.output
    report = json.loads(pdf_path.with_name("libro_TDM.pdf.report.json").read_text(encoding="utf-8"))
    assert report["iscc"]["content_code_unchanged_by_sealing"] is True
