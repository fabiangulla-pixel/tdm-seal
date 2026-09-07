from __future__ import annotations

from tdmseal.xmp.parser import RDF_NS, find_rdf_root, parse_xmp
from tdmseal.xmp.pdfa_extension import (
    PDFA_EXTENSION_NS,
    PDFA_SCHEMA_NS,
    merge_tdmrep_extension_schema,
)
from tdmseal.xmp.tdmrep import TDM_NS

_SCHEMAS_TAG = f"{{{PDFA_EXTENSION_NS}}}schemas"
_BAG_TAG = f"{{{RDF_NS}}}Bag"
_LI_TAG = f"{{{RDF_NS}}}li"
_NS_URI_TAG = f"{{{PDFA_SCHEMA_NS}}}namespaceURI"


def _find_schemas_bag(rdf_root):
    for desc in rdf_root.findall(f"{{{RDF_NS}}}Description"):
        el = desc.find(_SCHEMAS_TAG)
        if el is not None:
            return el.find(_BAG_TAG)
    return None


def test_merge_creates_schemas_when_absent():
    root = find_rdf_root(parse_xmp(None))

    operation = merge_tdmrep_extension_schema(root)

    assert operation == "create"
    bag = _find_schemas_bag(root)
    assert bag is not None
    entries = bag.findall(_LI_TAG)
    assert len(entries) == 1
    assert entries[0].find(_NS_URI_TAG).text == TDM_NS


def test_merge_is_idempotent():
    root = find_rdf_root(parse_xmp(None))
    merge_tdmrep_extension_schema(root)

    operation = merge_tdmrep_extension_schema(root)

    assert operation == "unchanged"
    bag = _find_schemas_bag(root)
    assert len(bag.findall(_LI_TAG)) == 1


def test_merge_preserves_other_schema_entries():
    existing_xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" '
        b'xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" '
        b'xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#">'
        b"<pdfaExtension:schemas><rdf:Bag>"
        b'<rdf:li rdf:parseType="Resource">'
        b"<pdfaSchema:schema>Otro esquema de InDesign</pdfaSchema:schema>"
        b"<pdfaSchema:namespaceURI>http://example.org/other/</pdfaSchema:namespaceURI>"
        b"</rdf:li>"
        b"</rdf:Bag></pdfaExtension:schemas>"
        b"</rdf:Description>"
        b"</rdf:RDF></x:xmpmeta>"
    )
    root = find_rdf_root(parse_xmp(existing_xmp))

    operation = merge_tdmrep_extension_schema(root)

    assert operation == "update"
    bag = _find_schemas_bag(root)
    entries = bag.findall(_LI_TAG)
    assert len(entries) == 2
    namespaces = {e.find(_NS_URI_TAG).text for e in entries}
    assert namespaces == {"http://example.org/other/", TDM_NS}
