from __future__ import annotations

import csv
import json
import subprocess

import pytest
from click.testing import CliRunner

import tdmseal.cli as cli_module
from tdmseal.appconfig import AppDefaults
from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.manifest import (
    COLUMNS,
    build_manifest,
    normalize_isbn,
    sign_file,
    ssh_keygen,
)
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.validation import epubcheck_validator

POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")

XMP_ISBN = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" '
    b'xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/" '
    b'prism:isbn="978-958-0000-00-6"><dc:title><rdf:Alt>'
    b'<rdf:li xml:lang="x-default">Libro con ISBN</rdf:li></rdf:Alt></dc:title>'
    b"</rdf:Description></rdf:RDF></x:xmpmeta>"
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(epubcheck_validator, "_command", lambda: None)
    monkeypatch.setattr(
        cli_module,
        "load_defaults",
        lambda *a, **k: AppDefaults(publisher=PublisherInfo(name="Editorial Ejemplo")),
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("urn:isbn:9789580000006", "9789580000006"),
        ("ISBN 978-958-0000-00-6", "9789580000006"),
        ("0-306-40615-2", "0306406152"),
        ("9789580000000", None),  # dígito de control incorrecto
        ("urn:isbn:0000000000000", None),  # relleno visto en EPUB reales
        ("0000000000", None),
        ("1234567890128", None),  # control válido pero sin prefijo 978/979
        ("teléfono 3001234567", None),
        (None, None),
    ],
)
def test_normalize_isbn(text, expected):
    assert normalize_isbn(text) == expected


def test_manifest_rows_for_pdf_and_epub(make_text_pdf, make_epub, tmp_path):
    pdf = make_text_pdf("libro.pdf", xmp_bytes=XMP_ISBN)
    epub = make_epub("libro.epub")
    sealed = seal_document(epub, SealConfig(policy=POLICY)).output_path

    manifest = build_manifest([pdf, epub, sealed], base_dir=tmp_path, aipref="train-ai=n")

    by_file = {row["archivo"]: row for row in manifest.rows}
    assert by_file["libro.pdf"]["isbn"] == "9789580000006"
    assert by_file["libro.pdf"]["titulo"] == "Libro con ISBN"
    assert by_file["libro.pdf"]["estado"] == "sin TDM"
    assert by_file["libro.epub"]["isbn"] == "9789580000006"  # dc:identifier urn:isbn
    assert by_file["libro.epub"]["titulo"] == "Derechos y minería"
    assert by_file["libro_TDM.epub"]["tdm_reserva"] == 1
    assert by_file["libro_TDM.epub"]["tdm_politica"] == POLICY.policy_url
    assert by_file["libro_TDM.epub"]["estado"] == "ok"
    for row in manifest.rows:
        assert row["sha256"] and row["iscc"].startswith("ISCC:")
        assert row["aipref"] == "train-ai=n"


def test_manifest_includes_iscc_units(make_text_pdf, tmp_path):
    pytest.importorskip("pypdfium2")
    manifest = build_manifest([make_text_pdf("a.pdf")], base_dir=tmp_path)

    row = manifest.rows[0]
    assert row["iscc_texto"].startswith("ISCC:E")
    assert row["iscc_meta"].startswith("ISCC:A")


def test_unreadable_file_is_reported_not_fatal(tmp_path, make_text_pdf):
    bad = tmp_path / "roto.pdf"
    bad.write_bytes(b"no es un pdf")
    good = make_text_pdf("bueno.pdf")

    manifest = build_manifest([bad, good], base_dir=tmp_path, with_iscc=False)

    assert manifest.rows[0]["estado"].startswith("error")
    assert manifest.rows[1]["estado"] == "sin TDM"


def test_write_csv_with_bom_and_json(make_text_pdf, tmp_path):
    manifest = build_manifest([make_text_pdf("a.pdf")], base_dir=tmp_path, with_iscc=False)

    csv_path = manifest.write(tmp_path / "out" / "catalogo.csv")
    json_path = manifest.write(tmp_path / "out" / "catalogo.json")

    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == COLUMNS
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["works"][0]["archivo"] == "a.pdf"
    with pytest.raises(ValueError):
        manifest.write(tmp_path / "catalogo.txt")


def test_cli_manifest(make_text_pdf, make_epub, tmp_path):
    make_text_pdf("a.pdf")
    make_epub("b.epub")
    out = tmp_path / "catalogo_tdm.json"

    result = CliRunner().invoke(
        cli_module.main, ["manifest", str(tmp_path), "--out", str(out), "--no-iscc"]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {w["archivo"] for w in data["works"]} == {"a.pdf", "b.epub"}
    assert data["publisher"]["name"] == "Editorial Ejemplo"


@pytest.mark.skipif(ssh_keygen() is None, reason="ssh-keygen no disponible")
def test_sign_and_verify_manifest(make_text_pdf, tmp_path):
    key = tmp_path / "clave"
    subprocess.run(
        [ssh_keygen(), "-q", "-t", "ed25519", "-N", "", "-C", "editorial", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    manifest = build_manifest([make_text_pdf("a.pdf")], base_dir=tmp_path, with_iscc=False)
    path = manifest.write(tmp_path / "catalogo.json")

    sig = sign_file(path, key)

    assert sig.read_text().startswith("-----BEGIN SSH SIGNATURE-----")
    pub = (tmp_path / "clave.pub").read_text().strip()
    allowed = tmp_path / "allowed_signers"
    allowed.write_text(f"editorial {pub}\n")
    with open(path, "rb") as fh:
        ok = subprocess.run(
            [
                ssh_keygen(),
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                "editorial",
                "-n",
                "tdm-seal-manifest",
                "-s",
                str(sig),
            ],
            stdin=fh,
            capture_output=True,
        )
    assert ok.returncode == 0, ok.stderr
    # Un cambio en el manifiesto invalida la firma.
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with open(path, "rb") as fh:
        bad = subprocess.run(
            [
                ssh_keygen(),
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                "editorial",
                "-n",
                "tdm-seal-manifest",
                "-s",
                str(sig),
            ],
            stdin=fh,
            capture_output=True,
        )
    assert bad.returncode != 0
