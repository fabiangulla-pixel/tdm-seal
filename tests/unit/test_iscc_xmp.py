from __future__ import annotations

from tdmseal.iscc.xmp import ISCC_XMP_NS, read_declared_iscc, write_declared_iscc
from tdmseal.xmp.parser import find_rdf_root, parse_xmp
from tdmseal.xmp.serializer import serialize_xmp

ORIG = {
    "content_code": "ISCC:EAATKCI547UG6QIL",
    "source_iscc": "ISCC:KAC2B62QYNYJXSH7GUER3Z7IN5AQWAHRQIJA744FDPTHPCM3CQVZ6WA",
    "source_datahash": "1e20aaaa",
}

FOREIGN_XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:format>application/pdf</dc:format></rdf:Description>"
    b"</rdf:RDF></x:xmpmeta>"
)


def _root(xmp: bytes | None = None):
    tree = parse_xmp(xmp)
    return tree, find_rdf_root(tree)


def test_write_then_read_roundtrip_and_preserves_foreign_xmp():
    tree, rdf = _root(FOREIGN_XMP)

    assert write_declared_iscc(rdf, **ORIG) == "create"

    reread = read_declared_iscc(find_rdf_root(parse_xmp(serialize_xmp(tree))))
    assert reread.to_dict() == ORIG
    assert b"application/pdf" in serialize_xmp(tree)
    assert ISCC_XMP_NS.encode() in serialize_xmp(tree)


def test_rewrite_same_values_is_unchanged_and_not_duplicated():
    tree, rdf = _root()
    write_declared_iscc(rdf, **ORIG)

    assert write_declared_iscc(rdf, **ORIG) == "unchanged"
    assert serialize_xmp(tree).count(b"isccContentCode>") == 2  # apertura + cierre


def test_resealing_same_content_keeps_original_provenance():
    _, rdf = _root()
    write_declared_iscc(rdf, **ORIG)

    # Segundo sellado: el "original" ahora es el archivo ya sellado.
    op = write_declared_iscc(
        rdf,
        content_code=ORIG["content_code"],
        source_iscc="ISCC:KACOTRODISTINTO",
        source_datahash="1e20bbbb",
    )

    declared = read_declared_iscc(rdf)
    assert op == "unchanged"
    assert declared.source_iscc == ORIG["source_iscc"]
    assert declared.source_datahash == ORIG["source_datahash"]


def test_different_content_replaces_provenance():
    _, rdf = _root()
    write_declared_iscc(rdf, **ORIG)

    op = write_declared_iscc(
        rdf, content_code="ISCC:EAAOTRO", source_iscc="ISCC:KACNUEVO", source_datahash="1e20cc"
    )

    declared = read_declared_iscc(rdf)
    assert op == "update"
    assert declared.content_code == "ISCC:EAAOTRO"
    assert declared.source_iscc == "ISCC:KACNUEVO"


def test_missing_content_code_does_not_erase_existing_one():
    _, rdf = _root()
    write_declared_iscc(rdf, **ORIG)

    write_declared_iscc(rdf, content_code=None, source_iscc="ISCC:KACX", source_datahash="1e20d")

    assert read_declared_iscc(rdf).content_code == ORIG["content_code"]


def test_read_returns_none_without_properties():
    _, rdf = _root(FOREIGN_XMP)
    assert read_declared_iscc(rdf) is None
