"""Registro público autoalojado y reconocimiento de copias (sin red)."""

from __future__ import annotations

import json
import re

import pikepdf
import pytest
from click.testing import CliRunner

from tdmseal.cli import main
from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.manifest import build_manifest
from tdmseal.match import match_file
from tdmseal.models import TDMPolicy
from tdmseal.registry import build_registry, declaration_kind
from tdmseal.samples import build_text_pdf

pytest.importorskip("pypdfium2")

PUBLISHER = {"name": "Güilla Edita", "rights_email": "derechos@ejemplo.org"}
POLICY = "https://editorial.example.edu/tdm/policies/1"


def _book(path, seed: str, pages: int = 6):
    lines = [
        f"{seed}: página {i}. " + " ".join(f"palabra{seed}{i}{j}" for j in range(60))
        for i in range(pages)
    ]
    return build_text_pdf(path, lines, title=f"Libro {seed}")


@pytest.fixture
def catalog(tmp_path):
    books = tmp_path / "libros"
    books.mkdir()
    sealed = []
    for seed, policy in (("alfa", POLICY), ("beta", None)):
        src = _book(books / f"{seed}.pdf", seed)
        result = seal_document(src, SealConfig(policy=TDMPolicy(1, policy)))
        assert result.status == "success"
        src.unlink()
        sealed.append(result.output_path)
    manifest = build_manifest(sealed, books, publisher=PUBLISHER)
    path = tmp_path / "manifiesto.json"
    manifest.write(path)
    return {"manifest": path, "sealed": sealed, "tmp": tmp_path}


def test_declaration_kinds():
    assert declaration_kind(None, None) is None
    assert declaration_kind(0, POLICY) == "autoriza"
    assert declaration_kind(1, None) == "reserva"
    assert declaration_kind(1, POLICY) == "licencia"


def test_registry_site(catalog):
    out = catalog["tmp"] / "registro"
    result = build_registry(catalog["manifest"], out, "https://editorial.example.edu/registro")

    assert result.works == 2 and not result.timestamped
    data = json.loads((out / "registro.json").read_text(encoding="utf-8"))
    kinds = sorted(d["declaracion"]["tipo"] for d in data["declarations"])
    assert kinds == ["licencia", "reserva"]
    record = next(d for d in data["declarations"] if d["declaracion"]["tipo"] == "licencia")
    assert record["identificadores"]["iscc_texto"].startswith("ISCC:")
    assert "Güilla Edita se reserva expresamente" in record["declaracion"]["texto"]["es"]
    assert record["declaracion"]["base_juridica"]

    page = (out / "obra" / f"{record['id']}.html").read_text(encoding="utf-8")
    assert '<meta name="tdm-reservation" content="1">' in page
    assert f'<meta name="tdm-policy" content="{POLICY}">' in page
    ld = json.loads(re.search(r'ld\+json">\n(.*?)\n</script>', page, re.S).group(1))
    assert ld["@type"] == "Book" and ld["usageInfo"] == POLICY
    assert ld["@id"] == f"https://editorial.example.edu/registro/obra/{record['id']}.html"
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "crypto.subtle.digest('SHA-256'" in index
    assert record["identificadores"]["sha256"] in index


def test_registry_rejects_csv_and_foreign_json(tmp_path):
    with pytest.raises(ValueError, match=r"\.json"):
        build_registry(tmp_path / "m.csv", tmp_path / "r")
    other = tmp_path / "otro.json"
    other.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="manifiesto"):
        build_registry(other, tmp_path / "r")


def test_registry_with_timestamp_proof(catalog, monkeypatch):
    from tdmseal import timestamp

    manifest = catalog["manifest"]
    tsr = manifest.with_name(manifest.name + ".tsr")
    tsr.write_bytes(b"respuesta")
    (manifest.with_name(manifest.name + ".tsr.json")).write_text(
        json.dumps({"fecha_sellada_utc": "2026-11-21T17:00:00Z", "tsa": "https://tsa"}),
        encoding="utf-8",
    )
    ok = timestamp.Verification(True, "2026-11-21T17:00:00Z", True, "SIN VERIFICAR", "")
    monkeypatch.setattr(timestamp, "verify_timestamp", lambda *a, **k: ok)

    out = catalog["tmp"] / "registro"
    result = build_registry(manifest, out)

    assert result.timestamped
    assert (out / "prueba" / "manifiesto.json.tsr").read_bytes() == b"respuesta"
    assert "Sello de tiempo RFC 3161" in (out / "index.html").read_text(encoding="utf-8")


def test_registry_refuses_stale_timestamp(catalog, monkeypatch):
    from tdmseal import timestamp

    manifest = catalog["manifest"]
    manifest.with_name(manifest.name + ".tsr").write_bytes(b"x")
    manifest.with_name(manifest.name + ".tsr.json").write_text("{}", encoding="utf-8")
    bad = timestamp.Verification(False, None, False, "", "el archivo cambió")
    monkeypatch.setattr(timestamp, "verify_timestamp", lambda *a, **k: bad)
    with pytest.raises(ValueError, match="no corresponde"):
        build_registry(manifest, catalog["tmp"] / "registro")


def test_match_identical_and_stripped_copy(catalog):
    alfa = catalog["sealed"][0]
    assert match_file(alfa, catalog["manifest"])[0].level == "idéntico"

    # Copia "pirata": otro nombre, sin XMP ni /Info, re-guardada linealizada.
    copy = catalog["tmp"] / "descarga (1).pdf"
    with pikepdf.open(alfa) as pdf:
        del pdf.Root["/Metadata"]
        del pdf.trailer["/Info"]
        pdf.save(copy, linearize=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)

    matches = match_file(copy, catalog["manifest"])
    assert matches[0].level == "mismo texto"
    assert matches[0].title == "Libro alfa"
    assert matches[0].reservation == 1 and matches[0].policy == POLICY
    assert all(m.title != "Libro beta" for m in matches)


def test_match_against_registry_json(catalog):
    out = catalog["tmp"] / "registro"
    build_registry(catalog["manifest"], out)
    matches = match_file(catalog["sealed"][1], out / "registro.json")
    assert [m.level for m in matches][:1] == ["idéntico"]


def test_unrelated_book_not_matched(catalog):
    other = _book(catalog["tmp"] / "otro.pdf", "gamma")
    assert match_file(other, catalog["manifest"]) == []
    result = CliRunner().invoke(main, ["match", str(other), "--catalog", str(catalog["manifest"])])
    assert result.exit_code == 1 and "SIN COINCIDENCIAS" in result.output


@pytest.fixture
def big_catalog(tmp_path):
    """Dos libros largos con huellas por fragmentos, como deja `tdmseal manifest`."""
    from tdmseal.fingerprint import write_fingerprints

    books = tmp_path / "largos"
    books.mkdir()
    texts = {}
    for seed in ("delta", "omega"):
        # 6 palabras por renglón: más anchas se saldrían de la página y no se extraerían.
        pages = [
            "\n".join(" ".join(f"{seed}{p}x{line}y{w}" for w in range(6)) for line in range(40))
            for p in range(10)
        ]
        texts[seed] = pages
        build_text_pdf(books / f"{seed}.pdf", pages, title=f"Libro {seed}")
    docs = sorted(books.glob("*.pdf"))
    manifest = build_manifest(docs, books, publisher=PUBLISHER)
    path = tmp_path / "catalogo.json"
    manifest.write(path)
    write_fingerprints(
        path, {row["archivo"]: d for row, d in zip(manifest.rows, docs, strict=True)}
    )
    return {"manifest": path, "texts": texts, "tmp": tmp_path}


def test_extract_recognized(big_catalog):
    extract = build_text_pdf(
        big_catalog["tmp"] / "capitulo.pdf", big_catalog["texts"]["delta"][3:6]
    )
    matches = match_file(extract, big_catalog["manifest"])
    assert [m.level for m in matches] == ["extracto de la obra"]
    assert matches[0].title == "Libro delta"
    assert matches[0].suspect_share > 0.9 and 0.2 < matches[0].work_share < 0.4


def test_book_inside_text_dump(big_catalog):
    dump = big_catalog["tmp"] / "dataset.jsonl"
    rows = [json.dumps({"text": f"texto ajeno número {i} " * 40}) for i in range(200)]
    rows.append(json.dumps({"text": " ".join(big_catalog["texts"]["omega"])}))
    dump.write_text("\n".join(rows), encoding="utf-8")

    matches = match_file(dump, big_catalog["manifest"])

    assert matches and matches[0].title == "Libro omega"
    assert matches[0].level == "contiene la obra" and matches[0].work_share > 0.95
    assert all(m.title != "Libro delta" for m in matches)


def test_unrelated_text_dump_not_matched(big_catalog):
    dump = big_catalog["tmp"] / "otro.txt"
    dump.write_text("Un texto cualquiera sobre otra cosa. " * 500, encoding="utf-8")
    assert match_file(dump, big_catalog["manifest"]) == []


def test_no_fingerprints_no_fragment_matching(big_catalog):
    big_catalog["manifest"].with_name("catalogo.json.huellas.json").unlink()
    extract = build_text_pdf(
        big_catalog["tmp"] / "capitulo.pdf", big_catalog["texts"]["delta"][3:6]
    )
    assert match_file(extract, big_catalog["manifest"]) == []


def test_fingerprints_hold_no_text(big_catalog):
    raw = big_catalog["manifest"].with_name("catalogo.json.huellas.json").read_text("utf-8")
    assert "delta0x" not in raw and "omega" not in raw.replace("omega.pdf", "")


def test_cli_registry(catalog):
    out = catalog["tmp"] / "web"
    result = CliRunner().invoke(main, ["registry", str(catalog["manifest"]), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "2 obra(s)" in result.output and "Sin sello de tiempo" in result.output
