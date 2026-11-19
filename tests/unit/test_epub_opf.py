from __future__ import annotations

from tdmseal.epub.opf import (
    TDM_EPUB_URI,
    ensure_prefix,
    parse_opf,
    read_iscc,
    read_tdm,
    serialize_opf,
    write_iscc,
    write_tdm,
)
from tdmseal.iscc.xmp import ISCC_XMP_NS
from tdmseal.models import TDMPolicy

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policy.jsonld")


def _opf(version: str, meta: str = "", prefix: str | None = None) -> bytes:
    prefix_attr = f' prefix="{prefix}"' if prefix else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}"{prefix_attr}>\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "    <dc:title>Libro</dc:title>\n"
        f"{meta}"
        "  </metadata>\n</package>\n"
    ).encode()


def test_epub3_writes_property_form_and_declares_prefix():
    raw = _opf("3.0", prefix="rendition: http://www.idpf.org/vocab/rendition/#")
    root = parse_opf(raw)

    assert write_tdm(root, POLICY) == "create"

    out = serialize_opf(root, raw).decode()
    assert '<meta property="tdm:reservation">1</meta>' in out
    assert f'<meta property="tdm:policy">{POLICY.policy_url}</meta>' in out
    # Conserva el prefijo que ya había y añade tdm con la URI de la especificación.
    assert root.get("prefix") == (
        f"rendition: http://www.idpf.org/vocab/rendition/# tdm: {TDM_EPUB_URI}"
    )
    assert out.startswith("<?xml")


def test_epub2_writes_name_content_form_without_prefix():
    raw = _opf("2.0")
    root = parse_opf(raw)

    write_tdm(root, POLICY)

    out = serialize_opf(root, raw).decode()
    assert '<meta name="tdm:reservation" content="1"/>' in out
    assert root.get("prefix") is None


def test_rewrite_is_idempotent_and_updates_value():
    root = parse_opf(_opf("3.0"))
    write_tdm(root, POLICY)
    write_tdm(root, POLICY)
    assert write_tdm(root, TDMPolicy(0)) == "update"

    decl = read_tdm(root)
    assert decl.reservation == 0
    assert decl.policy_url is None  # se retira si la nueva política no la trae
    out = serialize_opf(root, b"").decode()
    assert out.count("tdm:reservation") == 1
    assert root.get("prefix").count("tdm:") == 1


def test_epub3_with_legacy_epub2_meta_updates_both_forms():
    raw = _opf("3.0", meta='    <meta name="tdm:reservation" content="0"/>\n')
    root = parse_opf(raw)

    assert write_tdm(root, POLICY) == "update"

    out = serialize_opf(root, raw).decode()
    assert '<meta name="tdm:reservation" content="1"/>' in out
    assert '<meta property="tdm:reservation">1</meta>' in out


def test_reads_existing_declaration_in_both_forms():
    epub2 = parse_opf(_opf("2.0", '    <meta name="tdm:reservation" content="1"/>\n'))
    epub3 = parse_opf(_opf("3.0", '    <meta property="tdm:reservation">0</meta>\n'))

    assert read_tdm(epub2).reservation == 1
    assert read_tdm(epub3).reservation == 0
    assert read_tdm(parse_opf(_opf("3.0"))).present is False


def test_refines_metas_are_ignored():
    raw = _opf("3.0", '    <meta refines="#x" property="tdm:reservation">0</meta>\n')
    assert read_tdm(parse_opf(raw)).present is False


def test_ensure_prefix_replaces_conflicting_binding():
    root = parse_opf(_opf("3.0", prefix="tdm: http://otra.example/#"))
    ensure_prefix(root, "tdm", TDM_EPUB_URI)
    assert root.get("prefix") == f"tdm: {TDM_EPUB_URI}"


def test_iscc_roundtrip_in_opf_and_provenance_kept():
    root = parse_opf(_opf("3.0"))
    write_iscc(root, content_code="ISCC:EAA1", source_iscc="ISCC:KAC1", source_datahash="1e20a")
    write_iscc(root, content_code="ISCC:EAA1", source_iscc="ISCC:KAC2", source_datahash="1e20b")

    declared = read_iscc(root)
    assert declared.content_code == "ISCC:EAA1"
    assert declared.source_iscc == "ISCC:KAC1"  # procedencia original conservada
    assert f"tdmseal: {ISCC_XMP_NS}" in root.get("prefix")


def test_iscc_epub2_uses_name_content():
    raw = _opf("2.0")
    root = parse_opf(raw)
    write_iscc(root, content_code=None, source_iscc="ISCC:KAC1", source_datahash="1e20a")

    out = serialize_opf(root, raw).decode()
    assert '<meta name="tdmseal:isccSource" content="ISCC:KAC1"/>' in out
    assert "isccContentCode" not in out
