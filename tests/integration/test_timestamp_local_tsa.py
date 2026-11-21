"""Sello de tiempo RFC 3161 contra una TSA LOCAL montada con OpenSSL.

No se usa la red: un servidor HTTP en 127.0.0.1 responde con `openssl ts
-reply`, con una CA y un certificado de sellado creados para la prueba. Así se
comprueba la petición DER, el análisis de la respuesta, la verificación de
integridad y la de la firma con `openssl ts -verify`.
"""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tdmseal.timestamp import (
    TimestampError,
    build_request,
    create_timestamp,
    parse_response,
    sha256_file,
    tsr_path,
    verify_timestamp,
)
from tdmseal.tools import find_openssl

OPENSSL = find_openssl()
pytestmark = pytest.mark.skipif(OPENSSL is None, reason="OpenSSL no disponible")

TSA_CONF = """
[ req ]
distinguished_name = dn
prompt = no
[ dn ]
CN = {cn}
[ ca_ext ]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
[ tsa_ext ]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,timeStamping
[ tsa ]
default_tsa = tsa_config
[ tsa_config ]
dir = {dir}
serial = $dir/serial
signer_cert = $dir/tsa.pem
certs = $dir/ca.pem
signer_key = $dir/tsa.key
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256
accuracy = secs:1
ordering = no
tsa_name = no
ess_cert_id_chain = no
ess_cert_id_alg = sha256
"""


def _ssl(*args: str, cwd: Path, input: bytes | None = None) -> bytes:
    proc = subprocess.run(
        [OPENSSL, *args], cwd=cwd, input=input, capture_output=True, check=False, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace"))
    return proc.stdout


@pytest.fixture(scope="module")
def tsa(tmp_path_factory):
    d = tmp_path_factory.mktemp("tsa")
    conf = d / "tsa.cnf"
    conf.write_text(TSA_CONF.format(cn="TSA prueba", dir=d.as_posix()), encoding="ascii")
    (d / "serial").write_text("01\n", encoding="ascii")
    _ssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
        "-days",
        "2",
        "-config",
        "tsa.cnf",
        "-extensions",
        "ca_ext",
        "-subj",
        "/CN=CA prueba",
        cwd=d,
    )
    _ssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "tsa.key",
        "-out",
        "tsa.csr",
        "-config",
        "tsa.cnf",
        cwd=d,
    )
    _ssl(
        "x509",
        "-req",
        "-in",
        "tsa.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-out",
        "tsa.pem",
        "-days",
        "2",
        "-extfile",
        "tsa.cnf",
        "-extensions",
        "tsa_ext",
        cwd=d,
    )
    state = {"reject": False}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            assert self.headers["Content-Type"] == "application/timestamp-query"
            (d / "q.tsq").write_bytes(body)
            if state["reject"]:
                reply = _rejection()  # estado 2 ("rejection") con texto
            else:
                reply = _ssl(
                    "ts", "-reply", "-config", "tsa.cnf", "-queryfile", "q.tsq", "-out", "-", cwd=d
                )
            self.send_response(200)
            self.send_header("Content-Type", "application/timestamp-reply")
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"http://127.0.0.1:{server.server_port}/tsr", "ca": d / "ca.pem", "state": state}
    server.shutdown()


def _rejection() -> bytes:
    text = b"politica no admitida"
    utf8 = bytes([0x0C, len(text)]) + text
    free = bytes([0x30, len(utf8)]) + utf8
    status = bytes([0x02, 0x01, 0x02]) + free
    info = bytes([0x30, len(status)]) + status
    return bytes([0x30, len(info)]) + info


def test_request_is_valid_der_for_openssl(tmp_path):
    query = tmp_path / "q.tsq"
    query.write_bytes(build_request(b"\x11" * 32, 12345))
    text = _ssl("ts", "-query", "-in", str(query), "-text", cwd=tmp_path).decode()
    assert "sha256" in text
    assert "0000 - 11 11 11 11" in text
    assert "0x3039" in text  # nonce 12345
    assert "Certificate required: yes" in text


def test_create_and_verify_with_local_tsa(tsa, tmp_path):
    doc = tmp_path / "manifiesto.json"
    doc.write_text('{"obras": 1}', encoding="utf-8")

    receipt = create_timestamp(doc, tsa["url"])

    assert receipt.sha256 == sha256_file(doc).hex()
    assert receipt.politica == "1.2.3.4.1"
    assert receipt.fecha_sellada_utc.endswith("Z")
    assert tsr_path(doc).exists()
    stored = json.loads(Path(str(tsr_path(doc)) + ".json").read_text(encoding="utf-8"))
    assert stored["tsa"] == tsa["url"] and stored["respuesta"] == "manifiesto.json.tsr"

    plain = verify_timestamp(doc)
    assert plain.ok and plain.hash_matches and plain.signature.startswith("SIN VERIFICAR")

    full = verify_timestamp(doc, ca_file=tsa["ca"])
    assert full.ok and full.signature == "OK", full.signature


def test_tampered_file_detected(tsa, tmp_path):
    doc = tmp_path / "libro.pdf"
    doc.write_bytes(b"%PDF-1.7 original")
    create_timestamp(doc, tsa["url"])
    doc.write_bytes(b"%PDF-1.7 cambiado")

    result = verify_timestamp(doc, ca_file=tsa["ca"])

    assert not result.ok and not result.hash_matches
    assert "cambió" in result.message


def test_wrong_ca_fails_signature(tsa, tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x", encoding="utf-8")
    create_timestamp(doc, tsa["url"])
    other = tmp_path / "otra"
    other.mkdir()
    (other / "c.cnf").write_text(TSA_CONF.format(cn="otra", dir=other.as_posix()), encoding="ascii")
    _ssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "k",
        "-out",
        "ca.pem",
        "-days",
        "1",
        "-config",
        "c.cnf",
        "-extensions",
        "ca_ext",
        cwd=other,
    )

    result = verify_timestamp(doc, ca_file=other / "ca.pem")

    assert not result.ok and result.signature.startswith("FALLO")


def test_tsa_rejection_reported(tsa, tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x", encoding="utf-8")
    tsa["state"]["reject"] = True
    try:
        with pytest.raises(TimestampError, match="rechazó.*politica no admitida"):
            create_timestamp(doc, tsa["url"])
    finally:
        tsa["state"]["reject"] = False
    assert not tsr_path(doc).exists()


def test_garbage_response_rejected():
    with pytest.raises(TimestampError):
        parse_response(b"\x30\x05\x02\x01")
