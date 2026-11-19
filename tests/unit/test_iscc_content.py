from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tdmseal.iscc import content as content_mod
from tdmseal.iscc.content import (
    NO_EXTRA_WARNING,
    NO_TEXT_WARNING,
    compute_content_iscc,
    name_from_filename,
)

pytest.importorskip("pypdfium2")

# Valores calculados con iscc-sdk 0.9.7 sobre los mismos fixtures (19-nov-2026).
# El Text-Code y el Meta-Code solo dependen del texto y del título, no de los
# bytes que escriba pikepdf, así que son estables entre versiones.
SDK_TEXT_CODE = "ISCC:EAATKCI547UG6QIL"
SDK_META_CODE_TITLE = "ISCC:AAA2B62QYNYJXSH7"  # título "Derechos y minería"
SDK_META_CODE_FILENAME = "ISCC:AAA36PALX5LH45JX"  # nombre de archivo "sin-titulo_libro.pdf"


def test_text_and_meta_codes_match_iscc_sdk_reference(make_text_pdf):
    result = compute_content_iscc(make_text_pdf("con_titulo.pdf", title="Derechos y minería"))

    assert result.text_code == SDK_TEXT_CODE
    assert result.meta_code == SDK_META_CODE_TITLE
    assert result.name == "Derechos y minería"
    assert result.content_computed
    assert result.warnings == []


def test_meta_code_falls_back_to_filename_like_sdk(make_text_pdf):
    result = compute_content_iscc(make_text_pdf("sin-titulo_libro.pdf"))

    assert result.name == "sin titulo libro"
    assert result.meta_code == SDK_META_CODE_FILENAME
    assert result.text_code == SDK_TEXT_CODE


def test_title_is_read_from_xmp_when_info_has_none(make_text_pdf):
    xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">Solo en XMP</rdf:li></rdf:Alt>'
        b"</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>"
    )
    result = compute_content_iscc(make_text_pdf("x.pdf", xmp_bytes=xmp))

    assert result.name == "Solo en XMP"


def test_composite_iscc_has_four_units(make_text_pdf):
    result = compute_content_iscc(make_text_pdf(title="Derechos y minería"))

    assert result.iscc.startswith("ISCC:KAC")
    assert [result.meta_code[5], result.text_code[5], result.data_code[5]] == ["A", "E", "G"]
    assert result.instance_code.startswith("ISCC:I")


def test_text_code_ignores_filename_and_title(make_text_pdf):
    a = compute_content_iscc(make_text_pdf("a.pdf", title="Uno"))
    b = compute_content_iscc(make_text_pdf("otro_nombre.pdf", title="Otro título"))

    assert a.text_code == b.text_code
    assert a.meta_code != b.meta_code


def test_text_code_changes_when_text_changes(make_text_pdf):
    a = compute_content_iscc(make_text_pdf("a.pdf"))
    b = compute_content_iscc(make_text_pdf("b.pdf", ["Un texto completamente distinto."]))

    assert a.text_code != b.text_code


def test_pdf_without_text_layer_skips_text_code(make_pdf):
    result = compute_content_iscc(make_pdf("escaneo.pdf"))

    assert result.text_code is None
    assert NO_TEXT_WARNING in result.warnings
    # Se sigue calculando un ISCC útil con Meta, Data e Instance.
    assert result.iscc.startswith("ISCC:")


def test_without_extra_warns_and_still_computes(monkeypatch, make_text_pdf):
    monkeypatch.setattr(content_mod, "content_extra_available", lambda: False)

    result = compute_content_iscc(make_text_pdf())

    assert result.text_code is None
    assert NO_EXTRA_WARNING in result.warnings
    assert result.data_code and result.instance_code and result.meta_code


def test_name_from_filename():
    assert name_from_filename(Path("mi-libro_final.pdf")) == "mi libro final"


def _sdk_python() -> Path | None:
    configured = os.environ.get("TDMSEAL_ISCC_SDK_PY")
    candidate = (
        Path(configured)
        if configured
        else Path.home() / ".venvs" / "iscc-sdk-ref" / "Scripts" / "python.exe"
    )
    return candidate if candidate.exists() else None


@pytest.mark.skipif(_sdk_python() is None, reason="iscc-sdk de referencia no instalado")
def test_full_iscc_code_matches_live_iscc_sdk(make_text_pdf, make_pdf):
    """Compara el ISCC-CODE completo con iscc-sdk real (entorno aparte, opcional)."""
    paths = [
        make_text_pdf("con_titulo.pdf", title="Derechos y minería"),
        make_text_pdf("sin-titulo.pdf"),
        make_text_pdf("largo.pdf", [f"Línea de prueba número {i}" for i in range(300)]),
    ]
    script = Path(__file__).resolve().parents[2] / "scripts" / "iscc_sdk_codes.py"
    proc = subprocess.run(
        [str(_sdk_python()), str(script), *map(str, paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        check=True,
    )
    sdk = json.loads(proc.stdout)

    for path in paths:
        assert compute_content_iscc(path).iscc == sdk[str(path)]["iscc"], path.name
