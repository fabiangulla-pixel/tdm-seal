from __future__ import annotations

import pikepdf
import pytest

from tdmseal.config import SealConfig
from tdmseal.models import TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.seal import seal_pdf


def _config(**kwargs) -> SealConfig:
    policy = kwargs.pop("policy", TDMPolicy(reservation=1))
    return SealConfig(policy=policy, **kwargs)


def test_caso_a_pdf_sin_xmp(make_pdf):
    pdf_path = make_pdf("plain_no_xmp.pdf", page_count=3)

    result = seal_pdf(pdf_path, _config())

    assert result.status == "success"
    assert result.operation == "create"
    assert result.output_path.exists()
    assert result.output_path.name == "plain_no_xmp_TDM.pdf"
    assert result.validations["xmp_re_read"] == "PASS"
    assert result.validations["non_metadata_invariants"] == "PASS"

    after = inspect_pdf(result.output_path)
    assert after.tdm.reservation == 1
    assert after.page_count == 3


def test_caso_b_pdf_con_xmp_preserva_metadatos_ajenos(make_pdf_with_xmp):
    foreign_xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b"<dc:title>Manual de Autoayuda</dc:title>"
        b"</rdf:Description>"
        b"</rdf:RDF>"
        b"</x:xmpmeta>"
    )
    pdf_path = make_pdf_with_xmp("plain_with_xmp.pdf", foreign_xmp)

    result = seal_pdf(
        pdf_path,
        _config(
            policy=TDMPolicy(
                reservation=1, policy_url="https://editorial.example.edu/tdm/policy.jsonld"
            )
        ),
    )

    assert result.status == "success"
    with pikepdf.open(result.output_path) as pdf:
        xmp = bytes(pdf.Root.Metadata.read_bytes())
    assert b"Manual de Autoayuda" in xmp
    assert b"tdm:reservation" in xmp


def test_caso_c_pdf_con_tdm_previo_actualiza_no_duplica(make_pdf_with_xmp):
    previous_xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:tdm="http://www.w3.org/ns/tdmrep/">'
        b"<tdm:reservation>0</tdm:reservation>"
        b"</rdf:Description>"
        b"</rdf:RDF>"
        b"</x:xmpmeta>"
    )
    pdf_path = make_pdf_with_xmp("plain_with_tdm.pdf", previous_xmp)

    result = seal_pdf(pdf_path, _config(policy=TDMPolicy(reservation=1)))

    assert result.status == "success"
    assert result.operation == "update"
    after = inspect_pdf(result.output_path)
    assert after.tdm.reservation == 1


def test_idempotencia_sellar_dos_veces_no_duplica(make_pdf):
    pdf_path = make_pdf("idempotent.pdf")

    first = seal_pdf(pdf_path, _config())
    assert first.status == "success"

    second_config = _config()
    second_config.output_suffix = "_TDM2"
    second = seal_pdf(first.output_path, second_config)

    assert second.status == "success"
    assert second.operation == "update"
    with pikepdf.open(second.output_path) as pdf:
        xmp = bytes(pdf.Root.Metadata.read_bytes())
    assert xmp.count(b"<tdm:reservation>") == 1


def test_caso_h_pdf_firmado_se_omite(tmp_path, make_pdf, monkeypatch):
    pdf_path = make_pdf("signed.pdf")

    import tdmseal.pdf.inspector as inspector_module

    monkeypatch.setattr(inspector_module, "has_digital_signature", lambda pdf: True)

    result = seal_pdf(pdf_path, _config())

    assert result.status == "skipped"
    assert result.reason_code == "TDM021"
    assert result.output_path is None
    assert not (pdf_path.with_name("signed_TDM.pdf")).exists()


def test_reservation_invalida_rechazada():
    with pytest.raises(ValueError):
        TDMPolicy(reservation=5)


def test_no_sobrescribe_salida_existente(make_pdf):
    pdf_path = make_pdf("existing.pdf")
    output_path = pdf_path.with_name("existing_TDM.pdf")
    output_path.write_bytes(b"%PDF-1.4\n%%EOF")

    result = seal_pdf(pdf_path, _config())

    assert result.status == "failed"
    assert result.reason_code == "TDM050"
