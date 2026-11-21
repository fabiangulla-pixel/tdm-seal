"""Declaración en hubs ISCC: firma, nota y protocolo (sin red: hub local)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import iscc_core as ic
import pytest

from tdmseal.iscc import ed25519
from tdmseal.iscc import hub as h

# RFC 8032 §7.1, TEST 1 y TEST 2.
RFC_VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
]


@pytest.mark.parametrize("seed, pub, msg, sig", RFC_VECTORS)
def test_ed25519_rfc8032(seed, pub, msg, sig):
    seed_b, msg_b = bytes.fromhex(seed), bytes.fromhex(msg)
    assert ed25519.public_key(seed_b).hex() == pub
    assert ed25519.sign(seed_b, msg_b).hex() == sig
    assert ed25519.verify(bytes.fromhex(pub), msg_b, bytes.fromhex(sig))
    assert not ed25519.verify(bytes.fromhex(pub), msg_b + b"x", bytes.fromhex(sig))
    bad = bytearray(bytes.fromhex(sig))
    bad[5] ^= 1
    assert not ed25519.verify(bytes.fromhex(pub), msg_b, bytes(bad))


def test_base58_roundtrip():
    for data in (b"", b"\0\0abc", bytes(range(256)), h.PREFIX_PUBLIC + b"\x01" * 32):
        assert h.b58decode(h.b58encode(data)) == data
    assert h.b58encode(b"\0\0\x01") == "112"


def test_public_key_multikey_format():
    key = h.HubKey(b"\x07" * 32, "did:web:editorial.org")
    assert key.public_key.startswith("z6Mk")
    assert key.secret_key.startswith("z3u2")
    doc = key.did_document()
    assert doc["id"] == "did:web:editorial.org"
    assert doc["verificationMethod"][0]["publicKeyMultibase"] == key.public_key
    assert doc["assertionMethod"] == [f"did:web:editorial.org#{key.public_key}"]


@pytest.mark.parametrize(
    "domain, expected",
    [
        ("editorial.org", "did:web:editorial.org"),
        ("https://Editorial.ORG/", "did:web:editorial.org"),
        ("localhost:8443", "did:web:localhost%3A8443"),
    ],
)
def test_did_web(domain, expected):
    if "." not in domain:
        with pytest.raises(ValueError):
            h.did_web_for(domain)
        return
    assert h.did_web_for(domain) == expected
    assert h.did_url(expected) == f"https://{expected[8:]}/.well-known/did.json"


@pytest.mark.parametrize("bad", ["", "editorial.org/registro", "sin punto", "https://"])
def test_did_web_rejects(bad):
    with pytest.raises(ValueError):
        h.did_web_for(bad)


def test_nonce_embeds_hub_id():
    for hub_id in (0, 1, 3, 4095):
        nonce = h.create_nonce(hub_id)
        assert len(nonce) == 32 and nonce == nonce.lower()
        raw = bytes.fromhex(nonce)
        assert (raw[0] << 4) | (raw[1] >> 4) == hub_id
    with pytest.raises(ValueError):
        h.create_nonce(4096)


def test_jcs_rules():
    assert h.jcs({"b": 1, "a": [{"z": "ñ", "y": 2}]}) == '{"a":[{"y":2,"z":"ñ"}],"b":1}'.encode()
    with pytest.raises(ValueError):
        h.jcs({"a": 1.5})


def test_sign_and_verify_note():
    key = h.HubKey(b"\x01" * 32, "did:web:editorial.org")
    note = h.sign_note({"$schema": h.NOTE_SCHEMA, "iscc_code": "ISCC:X", "nonce": "0" * 32}, key)
    assert h.verify_note(note)
    tampered = json.loads(json.dumps(note))
    tampered["iscc_code"] = "ISCC:Y"
    assert not h.verify_note(tampered)
    with pytest.raises(ValueError):
        h.sign_note(note, key)


def test_key_storage(tmp_path, monkeypatch):
    path = tmp_path / "clave.json"
    monkeypatch.setenv("TDMSEAL_HUB_KEY", str(path))
    key = h.generate_key("editorial.org")
    assert h.save_key(key) == path
    assert h.load_key() == key
    with pytest.raises(h.HubError, match="no se sobrescribe"):
        h.save_key(h.generate_key("editorial.org"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["public_key"] = h.generate_key("x.org").public_key
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(h.HubError, match="no corresponde"):
        h.load_key()


@pytest.fixture
def sample_pdf(tmp_path):
    pytest.importorskip("pypdfium2")
    from tdmseal.samples import SAMPLE_TEXT, build_text_pdf

    return build_text_pdf(tmp_path / "obra.pdf", SAMPLE_TEXT, title="Obra de prueba")


def test_build_note_meets_hub_rules(sample_pdf):
    """Reglas de iscc_hub/validators.py (iscc-hub 0.1.2) reproducidas aquí."""
    key = h.HubKey(b"\x02" * 32, "did:web:editorial.org")
    note = h.build_note(sample_pdf, key, 1, "https://editorial.org/registro/obra/x.html")

    allowed = {
        "$schema",
        "iscc_code",
        "datahash",
        "nonce",
        "timestamp",
        "signature",
        "units",
        "metahash",
        "gateway",
    }
    assert set(note) <= allowed
    assert note["$schema"] == h.NOTE_SCHEMA
    assert ic.iscc_validate(note["iscc_code"], strict=True)
    assert ic.iscc_decode(note["iscc_code"])[0] == ic.MT.ISCC
    assert note["datahash"].startswith("1e20") and len(note["datahash"]) == 68
    assert len(note["units"]) <= 4
    for unit in note["units"]:
        assert ic.iscc_validate(unit, strict=True)
        assert len(ic.iscc_decode(unit)[4]) * 8 == 256
    instance = "ISCC:" + ic.encode_component(
        ic.MT.INSTANCE, ic.ST.NONE, ic.VS.V0, 256, bytes.fromhex(note["datahash"][4:])
    )
    assert ic.gen_iscc_code(note["units"] + [instance])["iscc"] == note["iscc_code"]
    import re

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", note["timestamp"])
    assert set(note["signature"]) == {"version", "controller", "pubkey", "proof"}
    assert h.verify_note(note)
    assert len(json.dumps(note).encode()) < h.MAX_NOTE_BYTES


def test_hub_url_resolution():
    assert h.hub_url(1) == (1, "https://iscc.id")
    assert h.hub_url("3") == (3, "https://splia.id")
    assert h.hub_url("amlet.id") == (2, "https://amlet.id")
    assert h.hub_url(1, "testnet") == (1, "https://staging.iscc.id")
    with pytest.raises(ValueError):
        h.hub_url(9)


@pytest.fixture
def local_hub():
    store: dict = {"notes": [], "status": 201}

    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            assert self.headers["Accept"] == "application/json"
            note = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not h.verify_note(note):
                return self._json(401, {"error": "Invalid signature"})
            if store["status"] != 201:
                return self._json(store["status"], {"error": "duplicate datahash"})
            store["notes"].append(note)
            self._json(201, {"iscc_id": "ISCC:MAIGPRUEBA", "seq": len(store["notes"]) - 1})

        def do_GET(self):  # noqa: N802
            if self.path == "/declaration/ISCC:MAIGPRUEBA/receipt":
                return self._json(200, {"type": ["VerifiableCredential", "IsccReceipt"]})
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", store
    server.shutdown()


def test_declare_against_local_hub(sample_pdf, local_hub):
    url, store = local_hub
    key = h.HubKey(b"\x03" * 32, "did:web:editorial.org")
    result = h.declare(h.build_note(sample_pdf, key, 1), url)

    assert result["iscc_id"] == "ISCC:MAIGPRUEBA" and result["seq"] == 0
    assert result["receipt"]["type"][1] == "IsccReceipt"
    assert store["notes"][0]["signature"]["controller"] == "did:web:editorial.org"


def test_declare_errors_explained(sample_pdf, local_hub):
    url, store = local_hub
    key = h.HubKey(b"\x04" * 32, "did:web:editorial.org")
    store["status"] = 409
    with pytest.raises(h.HubError, match="misma huella.*duplicate"):
        h.declare(h.build_note(sample_pdf, key, 1), url)
    note = h.build_note(sample_pdf, key, 1)
    note["nonce"] = "001" + "0" * 29  # alterada después de firmar
    with pytest.raises(h.HubError, match="firma inválida"):
        h.declare(note, url)


def test_declare_unreachable():
    note = {"x": 1}
    with pytest.raises(h.HubError, match="no se pudo contactar"):
        h.declare(note, "http://127.0.0.1:9", timeout=2)
