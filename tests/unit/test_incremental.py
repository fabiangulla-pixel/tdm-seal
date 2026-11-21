"""Actualización incremental del XMP (para sellar PDF firmados sin invalidar la firma)."""

from __future__ import annotations

import pikepdf
import pytest

from tdmseal.pdf.incremental import IncrementalUpdateError, append_xmp_update

XMP = (
    b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
    b'xmlns:tdm="http://www.w3.org/ns/tdmrep#"><tdm:reservation>1</tdm:reservation>'
    b'</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
)


def _check(src, out):
    assert out.read_bytes().startswith(src.read_bytes())
    with pikepdf.open(out) as pdf:
        assert pdf.Root.Metadata.read_bytes() == XMP
        assert "/Filter" not in pdf.Root.Metadata  # PDF/A-1: XMP sin comprimir
        assert list(pdf.check_pdf_syntax()) == []
        return dict(pdf.docinfo), len(pdf.pages)


@pytest.mark.parametrize("xref_streams", [False, True])
def test_appends_revision_and_keeps_original_bytes(tmp_path, make_text_pdf, xref_streams):
    src = make_text_pdf("src.pdf", title="Título")
    if xref_streams:
        with pikepdf.open(src, allow_overwriting_input=True) as pdf:
            pdf.save(src, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        assert b"/XRef" in src.read_bytes()
    out = tmp_path / "out.pdf"

    append_xmp_update(src, out, XMP)

    info, pages = _check(src, out)
    assert info["/Title"] == "Título"
    assert pages == 2
    tail = out.read_bytes()[len(src.read_bytes()) :]
    assert (b"/Type /XRef" in tail) == xref_streams  # mismo tipo de xref que el original


def test_replaces_existing_metadata_object_in_place(tmp_path, make_pdf_with_xmp):
    src = make_pdf_with_xmp("x.pdf", b"<x:xmpmeta xmlns:x='adobe:ns:meta/'/>")
    with pikepdf.open(src) as pdf:
        meta_num = pdf.Root.Metadata.objgen
        root_num = pdf.Root.objgen
    out = tmp_path / "out.pdf"

    append_xmp_update(src, out, XMP)

    _check(src, out)
    tail = out.read_bytes()[len(src.read_bytes()) :]
    assert f"{meta_num[0]} {meta_num[1]} obj".encode() in tail
    assert f"\n{root_num[0]} {root_num[1]} obj".encode() not in tail  # catálogo sin tocar


def test_keeps_inherited_info(tmp_path):
    from tests.conftest import build_incremental_without_info

    src = build_incremental_without_info(tmp_path / "mupdf.pdf", title="Heredado", subject="S")
    out = tmp_path / "out.pdf"

    append_xmp_update(src, out, XMP)

    info, _ = _check(src, out)
    assert info.get("/Title") == "Heredado"


def test_twice_chains_revisions(tmp_path, make_text_pdf):
    src = make_text_pdf("src.pdf")
    mid, out = tmp_path / "mid.pdf", tmp_path / "out.pdf"
    append_xmp_update(src, mid, b"<x/>")
    append_xmp_update(mid, out, XMP)
    _check(mid, out)


def test_rejects_file_without_startxref(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\n%%EOF\n")
    with pytest.raises(IncrementalUpdateError):
        append_xmp_update(bad, tmp_path / "out.pdf", XMP)
