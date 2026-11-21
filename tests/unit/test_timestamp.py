"""Sello de tiempo RFC 3161: partes que no necesitan OpenSSL ni red."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tdmseal import timestamp as ts
from tdmseal.cli import main


def test_request_der_shape():
    req = ts.build_request(bytes(range(32)), 2**62 + 5)
    tag, body, end = ts._read(req)
    assert tag == 0x30 and end == len(req)
    items = ts._children(body)
    assert [t for t, _ in items] == [0x02, 0x30, 0x02, 0x01]
    assert int.from_bytes(items[2][1], "big") == 2**62 + 5
    algo, digest = ts._children(items[1][1])
    assert ts._decode_oid(ts._children(algo[1])[0][1]) == ts.OID_SHA256
    assert digest[1] == bytes(range(32))


def test_request_rejects_wrong_digest():
    with pytest.raises(ValueError):
        ts.build_request(b"corto", 1)


@pytest.mark.parametrize("oid", [ts.OID_SHA256, ts.OID_TST_INFO, "1.2.3.4.1", "2.5.29.37"])
def test_oid_roundtrip(oid):
    assert ts._decode_oid(ts._oid(oid)[2:]) == oid


def test_long_length_roundtrip():
    value = b"x" * 300
    tag, inner, _ = ts._read(ts._tlv(0x04, value))
    assert tag == 0x04 and inner == value


def test_truncated_der_rejected():
    with pytest.raises(ts.TimestampError):
        ts._read(b"\x30\x82\x01")


def test_generalized_time():
    assert ts._generalized_to_iso("20261121163300Z") == "2026-11-21T16:33:00Z"
    assert ts._generalized_to_iso("20261121163300.25Z") == "2026-11-21T16:33:00.25Z"


def test_resolve_tsa():
    assert ts.resolve_tsa("FreeTSA") == "https://freetsa.org/tsr"
    assert ts.resolve_tsa("http://tsa.local/x") == "http://tsa.local/x"
    with pytest.raises(ValueError):
        ts.resolve_tsa("inventada")


def test_create_never_sends_the_file(tmp_path, monkeypatch):
    """Solo viaja la petición DER (huella + nonce), nunca bytes del archivo."""
    doc = tmp_path / "libro.pdf"
    doc.write_bytes(b"CONTENIDO-SECRETO" * 100)
    sent = {}

    def fake_post(url, body, timeout):
        sent["body"] = body
        raise ts.TimestampError("sin red en la prueba")

    monkeypatch.setattr(ts, "_post", fake_post)
    with pytest.raises(ts.TimestampError):
        ts.create_timestamp(doc, "freetsa")
    assert b"CONTENIDO-SECRETO" not in sent["body"]
    assert ts.sha256_file(doc) in sent["body"]
    assert len(sent["body"]) < 100


def test_verify_without_tsr(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x", encoding="utf-8")
    result = ts.verify_timestamp(doc)
    assert not result.ok and "no existe" in result.message


def test_cli_announces_what_is_sent(tmp_path, monkeypatch):
    doc = tmp_path / "m.json"
    doc.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        ts, "create_timestamp", lambda p, u: (_ for _ in ()).throw(ts.TimestampError("sin red"))
    )
    result = CliRunner().invoke(main, ["timestamp", "create", str(doc), "--tsa", "digicert"])
    assert "solo la huella SHA-256" in result.output
    assert "http://timestamp.digicert.com" in result.output
    assert result.exit_code == 1
