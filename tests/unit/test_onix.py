"""Reserva TDM en ONIX 3.0 (EpubUsageConstraint, listas 145/146)."""

from __future__ import annotations

import pytest
from lxml import etree

from tdmseal.onix import (
    ONIX_REF_NS,
    add_tdm_to_onix,
    build_onix,
    is_digital_form,
    tdm_status_in_onix,
)

REFERENCE = f"""<?xml version="1.0" encoding="UTF-8"?>
<ONIXMessage release="3.0" xmlns="{ONIX_REF_NS}">
  <Header><Sender><SenderName>Güilla Edita</SenderName></Sender>
    <SentDateTime>20261121</SentDateTime></Header>
  <Product>
    <RecordReference>ebook-1</RecordReference>
    <NotificationType>03</NotificationType>
    <DescriptiveDetail>
      <ProductComposition>00</ProductComposition>
      <ProductForm>ED</ProductForm>
      <ProductFormDetail>E101</ProductFormDetail>
      <EpubTechnicalProtection>00</EpubTechnicalProtection>
      <Collection><CollectionType>10</CollectionType></Collection>
      <TitleDetail><TitleType>01</TitleType><TitleElement><TitleElementLevel>01</TitleElementLevel>
        <TitleText>Los días biches</TitleText></TitleElement></TitleDetail>
    </DescriptiveDetail>
  </Product>
  <Product>
    <RecordReference>print-1</RecordReference>
    <NotificationType>03</NotificationType>
    <DescriptiveDetail>
      <ProductComposition>00</ProductComposition>
      <ProductForm>BC</ProductForm>
      <TitleDetail><TitleType>01</TitleType></TitleDetail>
    </DescriptiveDetail>
  </Product>
  <Product>
    <RecordReference>ebook-2</RecordReference>
    <NotificationType>03</NotificationType>
    <DescriptiveDetail>
      <ProductComposition>00</ProductComposition>
      <ProductForm>EA</ProductForm>
      <EpubUsageConstraint><EpubUsageType>02</EpubUsageType>
        <EpubUsageStatus>01</EpubUsageStatus></EpubUsageConstraint>
      <EpubUsageConstraint><EpubUsageType>11</EpubUsageType>
        <EpubUsageStatus>02</EpubUsageStatus>
        <EpubUsageLimit><Quantity>5</Quantity><EpubUsageUnit>07</EpubUsageUnit></EpubUsageLimit>
      </EpubUsageConstraint>
      <TitleDetail><TitleType>01</TitleType></TitleDetail>
    </DescriptiveDetail>
  </Product>
</ONIXMessage>
""".encode()

SHORT = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<ONIXmessage release="3.0" xmlns="http://ns.editeur.org/onix/3.0/short">
  <header><sender><x298>Editorial</x298></sender><x307>20261121</x307></header>
  <product>
    <a001>e-1</a001><a002>03</a002>
    <descriptivedetail>
      <x314>00</x314><b012>EB</b012>
      <titledetail><b202>01</b202></titledetail>
    </descriptivedetail>
  </product>
</ONIXmessage>
"""


def _children(xml: bytes, ref: str) -> list[str]:
    root = etree.fromstring(xml)
    for product in root:
        if etree.QName(product).localname not in ("Product", "product"):
            continue
        first = product[0]
        if first.text == ref:
            detail = next(
                c
                for c in product
                if etree.QName(c).localname in ("DescriptiveDetail", "descriptivedetail")
            )
            return [etree.QName(c).localname for c in detail if isinstance(c.tag, str)]
    raise AssertionError(ref)


def test_digital_forms():
    assert is_digital_form("ED") and is_digital_form("ea") and is_digital_form("AJ")
    assert not is_digital_form("BC") and not is_digital_form(None)


def test_adds_reservation_in_schema_order_and_touches_nothing_else():
    out, change = add_tdm_to_onix(REFERENCE, 1)

    assert (change.products, change.added, change.updated) == (3, 1, 1)
    assert change.skipped_print == ["print-1"]
    order = _children(out, "ebook-1")
    # Después de EpubTechnicalProtection y antes de Collection (orden del XSD).
    assert order.index("EpubTechnicalProtection") < order.index("EpubUsageConstraint")
    assert order.index("EpubUsageConstraint") < order.index("Collection")
    status = tdm_status_in_onix(out)
    assert status == {"ebook-1": "03", "print-1": None, "ebook-2": "03"}
    # Se conserva el resto: la otra restricción, el título con acentos.
    assert "Los días biches".encode() in out
    assert out.count(b"<EpubUsageType>02</EpubUsageType>") == 1
    # El límite deja de tener sentido con "prohibido".
    assert b"EpubUsageLimit" not in out


def test_idempotent():
    once, _ = add_tdm_to_onix(REFERENCE, 1)
    twice, change = add_tdm_to_onix(once, 1)
    assert twice == once
    assert change.added == change.updated == 0 and change.unchanged == 2


def test_reservation_zero_means_permitted():
    out, _ = add_tdm_to_onix(REFERENCE, 0)
    assert tdm_status_in_onix(out)["ebook-1"] == "01"


def test_all_products_includes_print():
    out, change = add_tdm_to_onix(REFERENCE, 1, all_products=True)
    assert change.skipped_print == []
    assert tdm_status_in_onix(out)["print-1"] == "03"


def test_short_tags_and_encoding_preserved():
    out, change = add_tdm_to_onix(SHORT, 1)
    assert change.added == 1
    assert out.startswith(b"<?xml version='1.0' encoding='ISO-8859-1'?>")
    assert b"<x318>11</x318>" in out and b"<x319>03</x319>" in out
    assert _children(out, "e-1") == ["x314", "b012", "epubusageconstraint", "titledetail"]
    assert tdm_status_in_onix(out) == {"e-1": "03"}


@pytest.mark.parametrize(
    "data, message",
    [
        (b"<no", "XML"),
        (b"<root/>", "ONIX"),
        (b'<ONIXMessage release="2.1"/>', "3.0"),
    ],
)
def test_rejects_non_onix3(data, message):
    with pytest.raises(ValueError, match=message):
        add_tdm_to_onix(data, 1)


def test_no_external_entities():
    evil = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///c:/windows/win.ini">]>'
        b'<ONIXMessage release="3.0"><Product><RecordReference>&e;</RecordReference>'
        b"</Product></ONIXMessage>"
    )
    out, _ = add_tdm_to_onix(evil, 1)
    assert b"[fonts]" not in out.lower()


def test_build_onix_from_manifest_rows():
    rows = [
        {
            "archivo": "a.pdf",
            "formato": "pdf",
            "titulo": "A & B",
            "isbn": "9789585221727",
            "iscc": "ISCC:KACX",
            "estado": "ok",
        },
        {"archivo": "roto.pdf", "estado": "error: ilegible"},
    ]
    out = build_onix(rows, 1, "Güilla Edita")
    root = etree.fromstring(out)
    ns = {"o": ONIX_REF_NS}
    assert len(root.findall("o:Product", ns)) == 1
    assert root.findtext(".//o:TitleText", namespaces=ns) == "A & B"
    assert root.findtext(".//o:ProductFormDetail", namespaces=ns) == "E107"
    ids = [e.text for e in root.iterfind(".//o:IDValue", ns)]
    assert ids == ["9789585221727", "ISCC:KACX"]
    assert tdm_status_in_onix(out) == {"tdmseal.9789585221727": "03"}
