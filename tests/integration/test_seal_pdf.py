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


def test_caso_h_pdf_firmado_se_omite(make_signed_pdf):
    pdf_path = make_signed_pdf("signed.pdf")

    result = seal_pdf(pdf_path, _config())

    assert result.status == "skipped"
    assert result.reason_code == "TDM021"
    assert result.output_path is None
    assert not (pdf_path.with_name("signed_TDM.pdf")).exists()


def test_caso_h_force_signed_permite_sellar(make_signed_pdf):
    pdf_path = make_signed_pdf("signed_forced.pdf")

    result = seal_pdf(pdf_path, _config(force_signed=True))

    assert result.status == "success"
    assert result.output_path.exists()


def test_caso_i_pdf_cifrado_legible_se_omite(make_encrypted_pdf):
    pdf_path = make_encrypted_pdf("encrypted_readable.pdf", user_password="")

    result = seal_pdf(pdf_path, _config())

    assert result.status == "skipped"
    assert result.reason_code == "TDM020"
    assert result.output_path is None


def test_caso_i_pdf_cifrado_con_password_falla_legible(make_encrypted_pdf):
    pdf_path = make_encrypted_pdf("encrypted_locked.pdf", user_password="secreto123")

    result = seal_pdf(pdf_path, _config())

    assert result.status == "failed"
    assert result.reason_code == "TDM020"


def test_pdf_cifrado_allow_encrypted_igual_se_omite_si_ilegible(make_encrypted_pdf):
    # allow_encrypted solo evita el bloqueo por defecto para PDF cifrados
    # LEGIBLES; un PDF que exige contrasena sigue sin poder abrirse.
    pdf_path = make_encrypted_pdf("encrypted_locked2.pdf", user_password="secreto123")

    result = seal_pdf(pdf_path, _config(allow_encrypted=True))

    assert result.status == "failed"
    assert result.reason_code == "TDM020"


@pytest.mark.parametrize("part", [1, 2, 3])
def test_caso_d_e_f_pdfa_1_2_3_anade_extension_schema(make_pdfa, part):
    pdf_path = make_pdfa(f"pdfa{part}.pdf", part=part, conformance="B")

    result = seal_pdf(pdf_path, _config())

    assert result.status == "success"
    with pikepdf.open(result.output_path) as pdf:
        xmp = bytes(pdf.Root.Metadata.read_bytes())
    assert b"pdfaExtension:schemas" in xmp
    assert b"http://www.w3.org/ns/tdmrep/" in xmp
    assert b"tdm:reservation" in xmp


def test_caso_g_pdfa_4_no_anade_extension_schema(make_pdfa):
    pdf_path = make_pdfa("pdfa4.pdf", part=4, conformance=None)

    result = seal_pdf(pdf_path, _config())

    assert result.status == "success"
    with pikepdf.open(result.output_path) as pdf:
        xmp = bytes(pdf.Root.Metadata.read_bytes())
    assert b"pdfaExtension:schemas" not in xmp
    assert b"tdm:reservation" in xmp


def test_pdfa_extension_schema_idempotente(make_pdfa):
    pdf_path = make_pdfa("pdfa2_repeat.pdf", part=2)

    first = seal_pdf(pdf_path, _config())
    second_config = _config()
    second_config.output_suffix = "_TDM2"
    second = seal_pdf(first.output_path, second_config)

    assert second.status == "success"
    with pikepdf.open(second.output_path) as pdf:
        xmp = bytes(pdf.Root.Metadata.read_bytes())
    # xmlns:tdm="..." (declaracion) + <pdfaSchema:namespaceURI>...</...>
    # (entrada del Extension Schema): 2 apariciones, sin duplicar en el
    # segundo sellado.
    assert xmp.count(b"http://www.w3.org/ns/tdmrep/") == 2


def test_reservation_invalida_rechazada():
    with pytest.raises(ValueError):
        TDMPolicy(reservation=5)


def test_no_sobrescribe_salida_existente(make_pdf):
    pdf_path = make_pdf("existing.pdf")
    output_path = pdf_path.with_name("existing_TDM.pdf")
    output_path.write_bytes(b"%PDF-1.4\n%%EOF")

    result = seal_pdf(pdf_path, _config())

    # Ya sellado: se omite (no es un error) y no se sobrescribe.
    assert result.status == "skipped"
    assert result.reason_code == "TDM050"
    assert output_path.read_bytes() == b"%PDF-1.4\n%%EOF"
