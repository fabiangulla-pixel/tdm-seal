"""El ONIX que produce TDM Seal valida contra el XSD oficial de EDItEUR.

El esquema (ONIX 3.0, Issue 75) se descarga una vez a
`%LOCALAPPDATA%\\TDMSeal\\tools\\onix` (o `TDMSEAL_ONIX_XSD`, carpeta con los .xsd);
no se versiona. Sin él, estas pruebas se omiten.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from lxml import etree

from tdmseal.onix import ONIX_REF_NS, add_tdm_to_onix, build_onix
from tdmseal.tools import tools_dir


def _xsd(kind: str) -> Path | None:
    configured = os.environ.get("TDMSEAL_ONIX_XSD")
    base = Path(configured) if configured else tools_dir() / "onix"
    if not base.is_dir():
        return None
    found = sorted(base.rglob(f"ONIX_BookProduct_3.0_{kind}.xsd"))
    return found[-1] if found else None


def _schema(kind: str) -> etree.XMLSchema:
    path = _xsd(kind)
    if path is None:
        pytest.skip("XSD oficial de ONIX 3.0 no descargado")
    return etree.XMLSchema(etree.parse(str(path)))


def _assert_valid(schema: etree.XMLSchema, data: bytes) -> None:
    doc = etree.fromstring(data)
    assert schema.validate(doc), "\n".join(str(e) for e in schema.error_log)


VALID_REFERENCE = f"""<?xml version="1.0" encoding="UTF-8"?>
<ONIXMessage release="3.0" xmlns="{ONIX_REF_NS}">
  <Header><Sender><SenderName>Editorial</SenderName></Sender>
    <SentDateTime>20261121</SentDateTime></Header>
  <Product>
    <RecordReference>ebook-1</RecordReference>
    <NotificationType>03</NotificationType>
    <ProductIdentifier><ProductIDType>15</ProductIDType>
      <IDValue>9789585221727</IDValue></ProductIdentifier>
    <DescriptiveDetail>
      <ProductComposition>00</ProductComposition>
      <ProductForm>ED</ProductForm>
      <ProductFormDetail>E101</ProductFormDetail>
      <EpubTechnicalProtection>00</EpubTechnicalProtection>
      <Collection><CollectionType>10</CollectionType>
        <TitleDetail><TitleType>01</TitleType><TitleElement>
          <TitleElementLevel>02</TitleElementLevel><TitleText>Serie</TitleText>
        </TitleElement></TitleDetail></Collection>
      <TitleDetail><TitleType>01</TitleType><TitleElement>
        <TitleElementLevel>01</TitleElementLevel><TitleText>Libro</TitleText>
      </TitleElement></TitleDetail>
      <Language><LanguageRole>01</LanguageRole><LanguageCode>spa</LanguageCode></Language>
    </DescriptiveDetail>
  </Product>
</ONIXMessage>
""".encode()

VALID_SHORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<ONIXmessage release="3.0" xmlns="http://ns.editeur.org/onix/3.0/short">
  <header><sender><x298>Editorial</x298></sender><x307>20261121</x307></header>
  <product>
    <a001>e-1</a001><a002>03</a002>
    <productidentifier><b221>15</b221><b244>9789585221727</b244></productidentifier>
    <descriptivedetail>
      <x314>00</x314><b012>EB</b012><b333>E107</b333>
      <titledetail><b202>01</b202><titleelement><x409>01</x409><b203>Libro</b203>
      </titleelement></titledetail>
    </descriptivedetail>
  </product>
</ONIXmessage>
"""


def test_fixtures_are_valid_before():
    _assert_valid(_schema("reference"), VALID_REFERENCE)
    _assert_valid(_schema("short"), VALID_SHORT)


def test_added_reservation_still_valid_reference():
    out, change = add_tdm_to_onix(VALID_REFERENCE, 1)
    assert change.added == 1
    _assert_valid(_schema("reference"), out)


def test_added_reservation_still_valid_short():
    out, change = add_tdm_to_onix(VALID_SHORT, 1)
    assert change.added == 1
    _assert_valid(_schema("short"), out)


def test_built_onix_valid():
    rows = [
        {
            "archivo": "a.pdf",
            "formato": "pdf",
            "titulo": "A",
            "isbn": "9789585221727",
            "iscc": "ISCC:KACX",
            "estado": "ok",
        },
        {
            "archivo": "b.epub",
            "formato": "epub",
            "titulo": None,
            "isbn": None,
            "iscc": None,
            "estado": "ok",
        },
    ]
    _assert_valid(_schema("reference"), build_onix(rows, 1, "Güilla Edita"))
