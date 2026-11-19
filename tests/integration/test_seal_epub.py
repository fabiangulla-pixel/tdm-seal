"""Sellado de EPUB 2 y 3 con los mismos invariantes que en PDF."""

from __future__ import annotations

import json
import zipfile

import pytest
from click.testing import CliRunner

from tdmseal.cli import main as cli_main
from tdmseal.config import SealConfig
from tdmseal.discovery import iter_documents
from tdmseal.documents import inspect_document, seal_document
from tdmseal.epub.writer import rewrite_epub
from tdmseal.errors import TDM005_EPUB_INVALID, TDM022_EPUB_DRM, TDM050_OUTPUT_EXISTS
from tdmseal.iscc import content as content_mod
from tdmseal.iscc.content import NO_EPUB_EXTRA_WARNING, compute_content_iscc
from tdmseal.models import EPUBInfo, TDMPolicy
from tdmseal.reporting.json_report import build_report
from tdmseal.validation import epubcheck_validator

POLICY = TDMPolicy(reservation=1, policy_url="https://editorial.example.edu/tdm/policy.jsonld")

ENCRYPTION_XML = (
    b'<?xml version="1.0"?>\n'
    b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
    b'xmlns:enc="http://www.w3.org/2001/04/xmlenc#">\n'
    b'<enc:EncryptedData><enc:EncryptionMethod Algorithm="%s"/>'
    b'<enc:CipherData><enc:CipherReference URI="OEBPS/c0.xhtml"/></enc:CipherData>'
    b"</enc:EncryptedData>\n</encryption>\n"
)


@pytest.fixture(autouse=True)
def no_epubcheck(monkeypatch):
    """Por defecto EPUBCheck no está (como en este equipo); hay pruebas aparte."""
    monkeypatch.setattr(epubcheck_validator, "_command", lambda: None)


def _opf(path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("OEBPS/content.opf").decode()


@pytest.mark.parametrize("version", [2, 3])
def test_seal_epub_creates_new_file_with_tdm(make_epub, version):
    path = make_epub(f"v{version}.epub", version=version)

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.status == "success", result.warnings
    assert result.output_path.name == f"v{version}_TDM.epub"
    assert path.exists()  # el original no se toca
    info = inspect_document(result.output_path)
    assert isinstance(info, EPUBInfo)
    assert info.tdm.reservation == 1
    assert info.tdm.policy_url == POLICY.policy_url
    assert result.validations["opf_re_read"] == "PASS"
    assert result.validations["container_unchanged"] == "PASS"
    assert result.validations["epubcheck"] == "SKIPPED"


def test_container_untouched_except_opf(make_epub):
    path = make_epub()

    result = seal_document(path, SealConfig(policy=POLICY))

    with zipfile.ZipFile(path) as a, zipfile.ZipFile(result.output_path) as b:
        assert [i.filename for i in a.infolist()] == [i.filename for i in b.infolist()]
        first = b.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert b.read("mimetype") == b"application/epub+zip"
        for info in a.infolist():
            if info.filename != "OEBPS/content.opf":
                assert b.getinfo(info.filename).CRC == info.CRC
                assert b.getinfo(info.filename).date_time == info.date_time


def test_seal_twice_is_idempotent(make_epub):
    first = seal_document(make_epub(), SealConfig(policy=POLICY))
    second = seal_document(first.output_path, SealConfig(policy=POLICY))

    assert second.status == "success"
    assert second.operation == "update"
    assert _opf(second.output_path).count("tdm:reservation") == 1


def test_epub_with_drm_is_skipped(make_epub):
    path = make_epub(
        extra_files={
            "META-INF/encryption.xml": ENCRYPTION_XML
            % b"http://www.w3.org/2001/04/xmlenc#aes128-cbc"
        }
    )

    result = seal_document(path, SealConfig(policy=POLICY, allow_encrypted=True))

    assert result.status == "skipped"
    assert result.reason_code == TDM022_EPUB_DRM
    assert not path.with_name("libro_TDM.epub").exists()


@pytest.mark.parametrize("marker", ["META-INF/rights.xml", "META-INF/license.lcpl"])
def test_adobe_and_lcp_drm_markers_are_skipped(make_epub, marker):
    path = make_epub(extra_files={marker: b"<rights/>"})

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.reason_code == TDM022_EPUB_DRM


def test_font_obfuscation_is_not_drm(make_epub):
    path = make_epub(
        extra_files={
            "META-INF/encryption.xml": ENCRYPTION_XML % b"http://www.idpf.org/2008/embedding"
        }
    )

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.status == "success"
    assert any("ofuscada" in w for w in result.warnings)


def test_mimetype_not_first_is_repaired_with_warning(make_epub):
    path = make_epub(mimetype_first=False)
    assert inspect_document(path).mimetype_ok is False

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.status == "success", result.warnings
    assert any("mimetype" in w for w in result.warnings)
    assert inspect_document(result.output_path).mimetype_ok is True


def test_existing_output_is_not_overwritten(make_epub):
    path = make_epub()
    path.with_name("libro_TDM.epub").write_bytes(b"previo")

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.reason_code == TDM050_OUTPUT_EXISTS
    assert path.with_name("libro_TDM.epub").read_bytes() == b"previo"


def test_not_an_epub_fails_cleanly(tmp_path):
    bad = tmp_path / "roto.epub"
    bad.write_bytes(b"no es un zip")

    result = seal_document(bad, SealConfig(policy=POLICY))

    assert result.status == "failed"
    assert result.reason_code == TDM005_EPUB_INVALID


def test_report_for_epub(make_epub):
    result = seal_document(make_epub(), SealConfig(policy=POLICY))

    report = build_report(result)
    assert report["input"]["format"] == "epub"
    assert report["output"]["tdm_reservation"] == 1
    json.dumps(report)


def test_rewrite_only_changes_requested_entry(make_epub, tmp_path):
    path = make_epub()
    out = tmp_path / "out.epub"

    rewrite_epub(path, out, {"OEBPS/c0.xhtml": b"<cambiado/>"})

    with zipfile.ZipFile(out) as zf:
        assert zf.read("OEBPS/c0.xhtml") == b"<cambiado/>"
        assert zf.testzip() is None


# ---- ISCC -------------------------------------------------------------------


def test_epub_iscc_without_extra_warns(monkeypatch, make_epub):
    monkeypatch.setattr(content_mod, "epub_extra_available", lambda: False)

    result = seal_document(make_epub(), SealConfig(policy=POLICY, compute_iscc=True))

    assert result.status == "success"
    assert NO_EPUB_EXTRA_WARNING in result.warnings
    declared = inspect_document(result.output_path).declared_iscc
    assert declared.source_iscc and declared.content_code is None


def test_epub_meta_code_matches_sdk_reference(monkeypatch, make_epub):
    """Meta-Code de 'Derechos y minería' calculado con iscc-sdk 0.9.7 (mismo que en PDF)."""
    monkeypatch.setattr(content_mod, "epub_extra_available", lambda: False)
    assert compute_content_iscc(make_epub()).meta_code == "ISCC:AAA2B62QYNYJXSH7"


@pytest.mark.parametrize("version", [2, 3])
def test_epub_text_code_unchanged_by_sealing(make_epub, version):
    pytest.importorskip("iscc_tika")
    path = make_epub(f"v{version}.epub", version=version)
    before = compute_content_iscc(path)

    result = seal_document(path, SealConfig(policy=POLICY, compute_iscc=True))
    after = compute_content_iscc(result.output_path)

    assert result.status == "success", result.warnings
    assert before.text_code is not None
    assert after.text_code == before.text_code
    assert after.meta_code == before.meta_code
    assert result.validations["iscc_content_stable"] == "PASS"
    assert inspect_document(result.output_path).declared_iscc.content_code == before.text_code


# ---- descubrimiento y CLI -------------------------------------------------------


def test_iter_documents_finds_pdf_and_epub(make_epub, make_pdf, tmp_path):
    make_epub("a.epub")
    make_pdf("b.pdf")
    (tmp_path / "c.txt").write_text("x")
    upper = make_pdf("D.PDF")

    found = iter_documents(tmp_path)

    assert sorted(p.name.lower() for p in found) == ["a.epub", "b.pdf", "d.pdf"]
    assert upper in found


def test_cli_seal_folder_with_pdf_and_epub(make_epub, make_pdf, tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    make_epub("a.epub")
    make_pdf("b.pdf")

    out = CliRunner().invoke(cli_main, ["seal", str(tmp_path), "--reservation", "1"])

    assert out.exit_code == 0, out.output
    assert (tmp_path / "a_TDM.epub").exists()
    assert (tmp_path / "b_TDM.pdf").exists()
    assert "2 correctos" in out.output


def test_cli_inspect_and_show_epub(make_epub):
    sealed = seal_document(make_epub(), SealConfig(policy=POLICY)).output_path

    inspect_out = CliRunner().invoke(cli_main, ["inspect", str(sealed)])
    show_out = CliRunner().invoke(cli_main, ["show", str(sealed)])

    assert "EPUB version: 3.0" in inspect_out.output
    payload = json.loads(show_out.output)
    assert payload["tdm_reservation"] == 1
    assert payload["source"] == "opf-package-metadata"
