"""Sello de tiempo RFC 3161: prueba ante terceros de que un archivo existía en
una fecha (la reserva TDM, el manifiesto del catálogo, el libro sellado).

Es lo único de TDM Seal que usa la red, y solo cuando el usuario lo pide
(`tdmseal timestamp create`). A la autoridad de sellado (TSA) se envía
**solo la huella SHA-256** del archivo, nunca su contenido. La respuesta
(`ARCHIVO.tsr`) queda junto al archivo con un recibo legible (`.tsr.json`).

La verificación es local:
- integridad: la huella sellada coincide con el archivo y la respuesta es la
  de nuestra petición (nonce) — sin dependencias;
- firma de la TSA: con OpenSSL (`openssl ts -verify`), que viene con Git
  para Windows, y el certificado raíz de la TSA (`--ca`).

DER mínimo escrito a mano: no se añaden dependencias.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from tdmseal import __version__
from tdmseal.tools import find_openssl, no_window

# TSA públicas y gratuitas conocidas (el usuario elige; no hay ninguna por defecto
# escondida: la CLI muestra a cuál se envía la huella).
KNOWN_TSAS = {
    "freetsa": "https://freetsa.org/tsr",
    "digicert": "http://timestamp.digicert.com",
    "sectigo": "http://timestamp.sectigo.com",
}
DEFAULT_TSA = "freetsa"

OID_SHA256 = "2.16.840.1.101.3.4.2.1"
OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
OID_TST_INFO = "1.2.840.113549.1.9.16.1.4"


class TimestampError(Exception):
    pass


# ---- DER mínimo -------------------------------------------------------------


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _len(len(value)) + value


def _int(n: int) -> bytes:
    raw = n.to_bytes((n.bit_length() + 8) // 8 or 1, "big", signed=True)
    return _tlv(0x02, raw)


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytes([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        body += bytes(reversed(chunk))
    return _tlv(0x06, body)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _read(data: bytes, pos: int = 0) -> tuple[int, bytes, int]:
    """Lee un TLV en `pos`: (etiqueta, valor, posición siguiente)."""
    if pos + 2 > len(data):
        raise TimestampError("respuesta DER truncada")
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4 or pos + count > len(data):
            raise TimestampError("longitud DER inválida")
        length = int.from_bytes(data[pos : pos + count], "big")
        pos += count
    end = pos + length
    if end > len(data):
        raise TimestampError("respuesta DER truncada")
    return tag, data[pos:end], end


def _children(value: bytes) -> list[tuple[int, bytes]]:
    items, pos = [], 0
    while pos < len(value):
        tag, inner, pos = _read(value, pos)
        items.append((tag, inner))
    return items


def _decode_oid(value: bytes) -> str:
    parts = [value[0] // 40, value[0] % 40]
    n = 0
    for b in value[1:]:
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(n)
            n = 0
    return ".".join(str(p) for p in parts)


# ---- Petición y respuesta ------------------------------------------------------


def build_request(digest: bytes, nonce: int) -> bytes:
    """TimeStampReq (RFC 3161 §2.4.1) para una huella SHA-256, con certReq=TRUE."""
    if len(digest) != 32:
        raise ValueError("se espera una huella SHA-256 (32 bytes)")
    imprint = _seq(_seq(_oid(OID_SHA256), b"\x05\x00"), _tlv(0x04, digest))
    return _seq(_int(1), imprint, _int(nonce), _tlv(0x01, b"\xff"))


@dataclass
class TstInfo:
    status: int
    policy: str
    hash_algorithm: str
    hashed_message: str  # hex
    serial: str  # hex
    gen_time: str  # ISO 8601 UTC
    nonce: int | None


def parse_response(data: bytes) -> TstInfo:
    """Extrae el TSTInfo de un TimeStampResp. Lanza TimestampError si la TSA rechazó."""
    tag, body, _ = _read(data)
    if tag != 0x30:
        raise TimestampError("la respuesta no es un TimeStampResp")
    parts = _children(body)
    status_info = _children(parts[0][1])
    status = int.from_bytes(status_info[0][1], "big")
    if status not in (0, 1) or len(parts) < 2:
        detail = ""
        for t, v in status_info[1:]:
            if t == 0x30:
                detail = " ".join(inner.decode("utf-8", "replace") for _, inner in _children(v))
        raise TimestampError(f"la TSA rechazó la petición (estado {status}) {detail}".strip())
    content_info = _children(parts[1][1])
    if _decode_oid(content_info[0][1]) != OID_SIGNED_DATA:
        raise TimestampError("el sello no es un SignedData CMS")
    signed_data = _children(_children(content_info[1][1])[0][1])
    encap = _children(signed_data[2][1])
    if _decode_oid(encap[0][1]) != OID_TST_INFO:
        raise TimestampError("el contenido firmado no es un TSTInfo")
    octets = _children(encap[1][1])[0][1]
    tst = _children(_children(octets)[0][1])
    imprint = _children(tst[2][1])
    algorithm = _decode_oid(_children(imprint[0][1])[0][1])
    gen_time = tst[4][1].decode("ascii")
    nonce = None
    for t, v in tst[5:]:
        if t == 0x02:
            nonce = int.from_bytes(v, "big", signed=True)
            break
    return TstInfo(
        status=status,
        policy=_decode_oid(tst[1][1]),
        hash_algorithm="sha256" if algorithm == OID_SHA256 else algorithm,
        hashed_message=imprint[1][1].hex(),
        serial=tst[3][1].hex(),
        gen_time=_generalized_to_iso(gen_time),
        nonce=nonce,
    )


def _generalized_to_iso(value: str) -> str:
    # AAAAMMDDhhmmss[.fff]Z
    base, _, frac = value.rstrip("Z").partition(".")
    stamp = datetime.strptime(base, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)  # noqa: UP017
    iso = stamp.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{iso}.{frac}Z" if frac else f"{iso}Z"


# ---- Red (solo bajo petición explícita) ---------------------------------------------


def resolve_tsa(tsa: str) -> str:
    url = KNOWN_TSAS.get(tsa.lower(), tsa)
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"TSA desconocida: {tsa!r}. Use una URL o: {', '.join(KNOWN_TSAS)}")
    return url


def _post(url: str, body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/timestamp-query",
            "Accept": "application/timestamp-reply",
            "User-Agent": f"TDM-Seal/{__version__}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.URLError as exc:
        # Antivirus que interceptan TLS rompen el de Python pero no el de curl
        # (visto en este equipo con Norton): se reintenta con curl.exe.
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc) and "SSL" not in str(exc):
            raise TimestampError(f"no se pudo contactar con la TSA: {exc}") from exc
        return _post_with_curl(url, body, timeout)


def _post_with_curl(url: str, body: bytes, timeout: float) -> bytes:
    import shutil

    curl = shutil.which("curl")
    if curl is None:
        raise TimestampError("fallo TLS al contactar con la TSA y no hay curl para reintentar")
    proc = subprocess.run(
        [
            curl,
            "-sS",
            "--fail",
            "--max-time",
            str(int(timeout)),
            "-H",
            "Content-Type: application/timestamp-query",
            "--data-binary",
            "@-",
            url,
        ],
        input=body,
        capture_output=True,
        timeout=timeout + 5,
        check=False,
        **no_window(),
    )
    if proc.returncode != 0:
        raise TimestampError(
            f"curl no pudo contactar con la TSA: {proc.stderr.decode(errors='replace')}"
        )
    return proc.stdout


@dataclass
class Receipt:
    archivo: str
    sha256: str
    tsa: str
    fecha_sellada_utc: str
    serie: str
    politica: str
    nonce: int | None
    herramienta: str
    respuesta: str  # nombre del .tsr

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"


def sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.digest()


def tsr_path(path: Path) -> Path:
    return Path(str(path) + ".tsr")


def create_timestamp(path: Path, tsa: str = DEFAULT_TSA, *, timeout: float = 30) -> Receipt:
    """Pide el sello a la TSA (envía solo la huella) y deja `.tsr` y `.tsr.json`."""
    path = Path(path)
    url = resolve_tsa(tsa)
    digest = sha256_file(path)
    nonce = secrets.randbits(63)
    reply = _post(url, build_request(digest, nonce), timeout)
    info = parse_response(reply)
    if info.hashed_message != digest.hex():
        raise TimestampError("la TSA selló una huella distinta de la enviada")
    if info.nonce != nonce:
        raise TimestampError("la respuesta no corresponde a esta petición (nonce distinto)")
    out = tsr_path(path)
    out.write_bytes(reply)
    receipt = Receipt(
        archivo=path.name,
        sha256=digest.hex(),
        tsa=url,
        fecha_sellada_utc=info.gen_time,
        serie=info.serial,
        politica=info.policy,
        nonce=nonce,
        herramienta=f"TDM Seal {__version__}",
        respuesta=out.name,
    )
    Path(str(out) + ".json").write_text(receipt.to_json(), encoding="utf-8")
    return receipt


@dataclass
class Verification:
    ok: bool
    gen_time: str | None
    hash_matches: bool
    signature: str  # "OK", "FALLO: …", "SIN VERIFICAR: …"
    message: str


def verify_timestamp(
    path: Path, tsr: Path | None = None, ca_file: Path | None = None
) -> Verification:
    """Comprueba que `path` es exactamente lo que se selló; con OpenSSL y `ca_file`,
    también la firma de la TSA."""
    path = Path(path)
    tsr = Path(tsr) if tsr else tsr_path(path)
    if not tsr.exists():
        return Verification(False, None, False, "SIN VERIFICAR", f"no existe {tsr.name}")
    try:
        info = parse_response(tsr.read_bytes())
    except TimestampError as exc:
        return Verification(False, None, False, "SIN VERIFICAR", str(exc))
    matches = info.hashed_message == sha256_file(path).hex()
    if not matches:
        return Verification(
            False,
            info.gen_time,
            False,
            "SIN VERIFICAR",
            "el archivo cambió después de sellarlo (la huella no coincide)",
        )
    signature = "SIN VERIFICAR: indique --ca con el certificado raíz de la TSA"
    ok = True
    if ca_file is not None:
        openssl = find_openssl()
        if openssl is None:
            signature = "SIN VERIFICAR: no se encontró OpenSSL"
        else:
            proc = subprocess.run(
                [
                    openssl,
                    "ts",
                    "-verify",
                    "-data",
                    str(path),
                    "-in",
                    str(tsr),
                    "-CAfile",
                    str(ca_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                **no_window(),
            )
            if proc.returncode == 0 and "OK" in proc.stdout:
                signature = "OK"
            else:
                ok = False
                signature = f"FALLO: {(proc.stdout + proc.stderr).strip()}"
    message = f"sellado el {info.gen_time} (UTC); el archivo no ha cambiado"
    return Verification(ok, info.gen_time, True, signature, message)
