"""PDF cifrados, con adjuntos y con formularios: lo que el sello debe conservar.

Hallazgo del 21-nov-2026: con `--allow-encrypted`, la copia sellada salía
descifrada y sin restricciones (pikepdf guarda sin cifrado por defecto).
"""

from __future__ import annotations

import pikepdf
import pytest

from tdmseal.config import SealConfig
from tdmseal.models import TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.pdf.integrity import compare_encryption, compare_non_metadata_invariants
from tdmseal.seal import seal_pdf

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")
RESTRICTED = pikepdf.Permissions(extract=False, modify_other=False, print_highres=False)


@pytest.mark.parametrize(
    "encryption",
    [
        pikepdf.Encryption(owner="propietario", user="", R=6, allow=RESTRICTED),  # AES-256
        pikepdf.Encryption(
            owner="propietario", user="", R=4, aes=True, allow=RESTRICTED
        ),  # AES-128
        pikepdf.Encryption(  # RC4-128 (no admite cifrar el XMP)
            owner="propietario", user="", R=4, aes=False, metadata=False, allow=RESTRICTED
        ),
    ],
    ids=["aes256", "aes128", "rc4"],
)
def test_encrypted_pdf_stays_encrypted_with_same_permissions(make_text_pdf, tmp_path, encryption):
    src = make_text_pdf("plain.pdf", title="Cifrado")
    path = tmp_path / "cifrado.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(path, encryption=encryption)

    result = seal_pdf(path, SealConfig(policy=POLICY, allow_encrypted=True, compute_iscc=True))

    assert result.status == "success", (result.errors, result.warnings)
    assert result.validations["encryption_preserved"] == "PASS"
    with pikepdf.open(result.output_path) as out, pikepdf.open(path) as orig:
        assert out.is_encrypted
        assert out.allow == orig.allow
        assert out.encryption.bits == orig.encryption.bits
    after = inspect_pdf(result.output_path)
    assert after.encrypted
    assert after.tdm.reservation == 1  # un rastreador lo lee (contraseña de usuario vacía)
    with pikepdf.open(result.output_path, password="propietario") as out:
        assert out.owner_password_matched  # la contraseña de propietario sigue sirviendo


def test_compare_encryption_detects_stripped_encryption(make_text_pdf, tmp_path):
    src = make_text_pdf("plain.pdf")
    enc = tmp_path / "enc.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(enc, encryption=pikepdf.Encryption(owner="o", user="", allow=RESTRICTED))
    stripped = tmp_path / "stripped.pdf"
    with pikepdf.open(enc) as pdf:
        pdf.save(stripped)  # el comportamiento por defecto de pikepdf: descifra

    result = compare_encryption(enc, stripped)

    assert result["status"] == "FAIL"
    assert "no lo está" in result["issues"][0]


def _with_attachments(src, out, *, nested: bool):
    with pikepdf.open(src) as pdf:
        a = pikepdf.AttachedFileSpec(pdf, b"<factura>1</factura>", mime_type="text/xml")
        b = pikepdf.AttachedFileSpec(pdf, b"datos;1\n", mime_type="text/csv")
        if nested:
            # Árbol de nombres con /Kids (como lo escriben algunos programas).
            leaf1 = pdf.make_indirect(
                pikepdf.Dictionary(Names=["a.xml", a.obj], Limits=[pikepdf.String("a.xml")] * 2)
            )
            leaf2 = pdf.make_indirect(
                pikepdf.Dictionary(Names=["b.csv", b.obj], Limits=[pikepdf.String("b.csv")] * 2)
            )
            pdf.Root.Names = pikepdf.Dictionary(
                EmbeddedFiles=pikepdf.Dictionary(Kids=[leaf1, leaf2])
            )
        else:
            pdf.attachments["a.xml"] = a
            pdf.attachments["b.csv"] = b
        pdf.save(out)
    return out


@pytest.mark.parametrize("nested", [False, True], ids=["plano", "arbol_kids"])
def test_attachments_are_kept(make_text_pdf, tmp_path, nested):
    path = _with_attachments(make_text_pdf("src.pdf"), tmp_path / "adj.pdf", nested=nested)
    with pikepdf.open(path) as pdf:
        assert set(pdf.attachments) == {"a.xml", "b.csv"}

    result = seal_pdf(path, SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["non_metadata_invariants"] == "PASS"
    with pikepdf.open(result.output_path) as out:
        assert out.attachments["a.xml"].get_file().read_bytes() == b"<factura>1</factura>"


def _with_form(src, out):
    with pikepdf.open(src) as pdf:
        page = pdf.pages[0]
        text = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Annot,
                Subtype=pikepdf.Name.Widget,
                FT=pikepdf.Name.Tx,
                T=pikepdf.String("nombre"),
                V=pikepdf.String("Ana Pérez"),
                Rect=[50, 50, 250, 70],
                P=page.obj,
            )
        )
        check = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.Annot,
                Subtype=pikepdf.Name.Widget,
                FT=pikepdf.Name.Btn,
                T=pikepdf.String("acepta"),
                V=pikepdf.Name.Yes,
                AS=pikepdf.Name.Yes,
                Rect=[50, 80, 64, 94],
                P=page.obj,
            )
        )
        page.obj.Annots = pdf.make_indirect(pikepdf.Array([text, check]))
        pdf.Root.AcroForm = pikepdf.Dictionary(Fields=[text, check], NeedAppearances=True)
        pdf.save(out)
    return out


def test_filled_form_is_kept(make_text_pdf, tmp_path):
    path = _with_form(make_text_pdf("src.pdf"), tmp_path / "formulario.pdf")

    result = seal_pdf(path, SealConfig(policy=POLICY))

    assert result.status == "success", result.warnings
    with pikepdf.open(result.output_path) as out:
        fields = {str(f.T): f.V for f in out.Root.AcroForm.Fields}
        assert str(fields["nombre"]) == "Ana Pérez"
        assert fields["acepta"] == pikepdf.Name.Yes


def test_integrity_detects_changed_form_value(make_text_pdf, tmp_path):
    path = _with_form(make_text_pdf("src.pdf"), tmp_path / "formulario.pdf")
    changed = tmp_path / "cambiado.pdf"
    with pikepdf.open(path) as pdf:
        pdf.Root.AcroForm.Fields[0].V = pikepdf.String("Otra persona")
        pdf.save(changed)

    result = compare_non_metadata_invariants(path, changed)

    assert result["status"] == "FAIL"
    assert any("formulario" in i for i in result["issues"])


def test_integrity_detects_changed_attachment(make_text_pdf, tmp_path):
    path = _with_attachments(make_text_pdf("src.pdf"), tmp_path / "adj.pdf", nested=False)
    changed = tmp_path / "cambiado.pdf"
    with pikepdf.open(path) as pdf:
        pdf.attachments["a.xml"] = pikepdf.AttachedFileSpec(pdf, b"<factura>2</factura>")
        pdf.save(changed)

    result = compare_non_metadata_invariants(path, changed)

    assert result["status"] == "FAIL"
    assert any("adjunto" in i for i in result["issues"])
