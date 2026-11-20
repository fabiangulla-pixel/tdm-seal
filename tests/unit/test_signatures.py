"""Detector de firmas: casos estructurales que una firma real puede presentar."""

from __future__ import annotations

import pikepdf

from tdmseal.pdf.signatures import has_digital_signature


def _pdf_with_fields(*fields: pikepdf.Dictionary) -> pikepdf.Pdf:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.Root.AcroForm = pikepdf.Dictionary(
        Fields=pikepdf.Array([pdf.make_indirect(f) for f in fields])
    )
    return pdf


def _sig_value(pdf: pikepdf.Pdf) -> pikepdf.Object:
    return pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Sig))


def test_unsigned_pdf():
    pdf = pikepdf.Pdf.new()
    assert not has_digital_signature(pdf)


def test_empty_signature_field_is_not_a_signature():
    pdf = _pdf_with_fields(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T=pikepdf.String("Vacia")))
    assert not has_digital_signature(pdf)


def test_signature_type_inherited_from_parent_field():
    """ISO 32000-1 §12.7.3.1: /FT es heredable; el valor puede estar en el hijo."""
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    kid = pdf.make_indirect(pikepdf.Dictionary(T=pikepdf.String("hijo"), V=_sig_value(pdf)))
    parent = pdf.make_indirect(
        pikepdf.Dictionary(FT=pikepdf.Name.Sig, T=pikepdf.String("p"), Kids=[kid])
    )
    kid.Parent = parent
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([parent]))

    assert has_digital_signature(pdf)


def test_text_field_with_value_is_not_a_signature():
    pdf = _pdf_with_fields(pikepdf.Dictionary(FT=pikepdf.Name.Tx, V=pikepdf.String("hola")))
    assert not has_digital_signature(pdf)


def test_docmdp_or_ur3_permissions_count_as_signed():
    for key in ("/DocMDP", "/UR3"):
        pdf = pikepdf.Pdf.new()
        pdf.Root.Perms = pikepdf.Dictionary({key: _sig_value(pdf)})
        assert has_digital_signature(pdf), key


def test_cyclic_kids_do_not_hang():
    pdf = pikepdf.Pdf.new()
    a = pdf.make_indirect(pikepdf.Dictionary(T=pikepdf.String("a")))
    b = pdf.make_indirect(pikepdf.Dictionary(T=pikepdf.String("b"), Kids=[a]))
    a.Kids = pikepdf.Array([b])
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([a]))

    assert not has_digital_signature(pdf)
