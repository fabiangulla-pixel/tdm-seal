"""Declaración directa en la red federada de hubs ISCC (ISO 24138), sin intermediarios.

Un hub ISCC registra quién declaró un contenido y cuándo (el ISCC-ID lleva la
marca de tiempo del hub) y devuelve un recibo firmado (credencial verificable).
Con la política por defecto de los hubs, puede declarar cualquiera que tenga:

1. una clave Ed25519 (`tdmseal iscc-hub keygen`, se guarda en el equipo), y
2. su clave pública publicada en `https://SU-DOMINIO/.well-known/did.json`
   (identidad `did:web:SU-DOMINIO`), para que el hub sepa que la editorial
   controla esa clave.

No hay cuentas ni cuotas. Protocolo: nota `IsccNote` (esquema 0.8.0) firmada
con ISCC-SIG v1.0 (JCS + Ed25519 + multibase base58btc), POST /declaration;
recibo en GET /declaration/{iscc_id}/receipt. Ver iscc/iscc-hub en GitHub.

Lo único que sale del equipo al declarar es la nota: ISCC, huella BLAKE3,
unidades ISCC (huellas de similitud, no el texto), nonce, firma y,
opcionalmente, la URL pública de la ficha. Nunca el archivo.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tdmseal import __version__
from tdmseal.iscc import ed25519

NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"
SIG_VERSION = "ISCC-SIG v1.0"
PREFIX_PUBLIC = b"\xed\x01"  # multicodec ed25519-pub
PREFIX_SECRET = b"\x80\x26"  # multicodec ed25519-priv (mismo formato que iscc-crypto)
MAX_NOTE_BYTES = 8192

# Lista oficial (github.com/iscc/iscc-hub/hubs/*.yaml, 22-oct-2026).
HUBS = {
    "mainnet": {1: "https://iscc.id", 2: "https://amlet.id", 3: "https://splia.id"},
    "testnet": {
        1: "https://staging.iscc.id",
        2: "https://staging.amlet.id",
        3: "https://staging.splia.id",
    },
}
HUB_NAMES = {1: "ISCC Foundation", 2: "Amlet", 3: "S-PLIA (Hipertexto-Netizen)"}


class HubError(Exception):
    pass


# ---- base58btc / multibase -----------------------------------------------------

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(data) - len(data.lstrip(b"\0"))
    return "1" * pad + out


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        idx = _B58.find(ch)
        if idx < 0:
            raise ValueError(f"carácter no base58: {ch!r}")
        n = n * 58 + idx
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(text) - len(text.lstrip("1"))
    return b"\0" * pad + raw


def jcs(obj) -> bytes:
    """JSON Canonicalization Scheme (RFC 8785) para los objetos de una nota:
    solo cadenas, enteros, listas y objetos con claves ASCII (sin flotantes)."""

    def check(value):
        if isinstance(value, float):
            raise ValueError("JCS: esta implementación no admite números decimales")
        if isinstance(value, dict):
            for k, v in value.items():
                if not k.isascii():
                    raise ValueError("JCS: claves no ASCII no admitidas")
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)

    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# ---- Claves --------------------------------------------------------------------


@dataclass(frozen=True)
class HubKey:
    seed: bytes
    controller: str  # did:web:dominio

    @property
    def public_key(self) -> str:
        return "z" + b58encode(PREFIX_PUBLIC + ed25519.public_key(self.seed))

    @property
    def secret_key(self) -> str:
        return "z" + b58encode(PREFIX_SECRET + self.seed)

    def did_document(self) -> dict:
        """Documento de identidad (W3C CID) a publicar en /.well-known/did.json,
        con la misma forma que genera iscc-crypto."""
        method = f"{self.controller}#{self.public_key}"
        return {
            "id": self.controller,
            "verificationMethod": [
                {
                    "id": method,
                    "type": "Multikey",
                    "controller": self.controller,
                    "publicKeyMultibase": self.public_key,
                }
            ],
            "authentication": [method],
            "assertionMethod": [method],
            "capabilityDelegation": [method],
            "capabilityInvocation": [method],
        }


def did_web_for(domain: str) -> str:
    """'editorial.org' o 'https://editorial.org/' -> 'did:web:editorial.org'."""
    host = domain.strip()
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    host = host.strip("/")
    if not host or "/" in host or " " in host or "." not in host:
        raise ValueError(
            f"dominio no válido: {domain!r} (solo el dominio, p. ej. editorial.org; "
            "did.json debe ir en la raíz del dominio)"
        )
    return "did:web:" + host.lower().replace(":", "%3A")


def did_url(controller: str) -> str:
    host = controller.removeprefix("did:web:").replace("%3A", ":")
    return f"https://{host}/.well-known/did.json"


def key_path() -> Path:
    base = os.environ.get("TDMSEAL_HUB_KEY")
    if base:
        return Path(base)
    root = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(root) / "TDMSeal" / "clave-iscc.json"


def generate_key(domain: str) -> HubKey:
    return HubKey(secrets.token_bytes(32), did_web_for(domain))


def save_key(key: HubKey, path: Path | None = None, *, overwrite: bool = False) -> Path:
    path = Path(path) if path else key_path()
    if path.exists() and not overwrite:
        raise HubError(f"ya existe una clave en {path}; no se sobrescribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "aviso": "CLAVE SECRETA de la editorial. No la comparta ni la suba a ninguna parte.",
        "controller": key.controller,
        "public_key": key.public_key,
        "secret_key": key.secret_key,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_key(path: Path | None = None) -> HubKey:
    path = Path(path) if path else key_path()
    if not path.exists():
        raise HubError(f"no hay clave en {path}; créela con `tdmseal iscc-hub keygen`")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = b58decode(data["secret_key"][1:])
    if not data["secret_key"].startswith("z") or raw[:2] != PREFIX_SECRET or len(raw) != 34:
        raise HubError("la clave guardada no tiene el formato multikey Ed25519 esperado")
    key = HubKey(raw[2:], data["controller"])
    if data.get("public_key") and data["public_key"] != key.public_key:
        raise HubError("la clave pública guardada no corresponde a la secreta")
    return key


# ---- Nota de declaración ----------------------------------------------------------


def create_nonce(hub_id: int) -> str:
    if not 0 <= hub_id <= 4095:
        raise ValueError("hub_id debe estar entre 0 y 4095")
    value = int.from_bytes(secrets.token_bytes(16), "big") & ~(0xFFF << 116)
    return (value | (hub_id << 116)).to_bytes(16, "big").hex()


def _timestamp_now() -> str:
    now = datetime.now(timezone.utc)  # noqa: UP017
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def sign_note(note: dict, key: HubKey) -> dict:
    """Firma ISCC-SIG v1.0: JCS del objeto con `signature` sin `proof`, Ed25519."""
    if "signature" in note:
        raise ValueError("la nota ya tiene firma")
    signed = dict(note)
    signed["signature"] = {
        "version": SIG_VERSION,
        "controller": key.controller,
        "pubkey": key.public_key,
    }
    proof = ed25519.sign(key.seed, jcs(signed))
    signed["signature"]["proof"] = "z" + b58encode(proof)
    return signed


def verify_note(note: dict) -> bool:
    """Comprueba la firma de una nota con la clave pública que lleva dentro."""
    sig = note.get("signature") or {}
    try:
        pub = b58decode(sig["pubkey"][1:])
        proof = b58decode(sig["proof"][1:])
    except (KeyError, ValueError, TypeError):
        return False
    if pub[:2] != PREFIX_PUBLIC:
        return False
    unsigned = dict(note)
    unsigned["signature"] = {k: v for k, v in sig.items() if k != "proof"}
    return ed25519.verify(pub[2:], jcs(unsigned), proof)


def build_note(path: Path, key: HubKey, hub_id: int, gateway: str | None = None) -> dict:
    """Nota firmada para un PDF/EPUB: ISCC-CODE, datahash y unidades de 256 bits."""
    from tdmseal.iscc.content import compute_content_iscc

    full = compute_content_iscc(path, bits=256)
    units = [full.meta_code]
    if full.text_code:
        units.append(full.text_code)
    units.append(full.data_code)
    note = {
        "$schema": NOTE_SCHEMA,
        "iscc_code": full.iscc,
        "datahash": full.datahash,
        "nonce": create_nonce(hub_id),
        "timestamp": _timestamp_now(),
        "units": units,
    }
    if gateway:
        if not gateway.startswith(("https://", "http://")) or any(c.isspace() for c in gateway):
            raise ValueError("gateway debe ser una URL http(s) sin espacios")
        note["gateway"] = gateway
    signed = sign_note(note, key)
    if len(json.dumps(signed).encode()) > MAX_NOTE_BYTES:
        raise HubError("la nota supera los 8192 bytes que admite un hub")
    return signed


# ---- Red (solo bajo orden explícita) ----------------------------------------------


def hub_url(hub: str | int, network: str = "mainnet") -> tuple[int, str]:
    """Acepta 1/2/3, 'iscc.id' o una URL. Devuelve (hub_id, url)."""
    table = HUBS[network]
    if isinstance(hub, int) or str(hub).isdigit():
        hub_id = int(hub)
        if hub_id not in table:
            raise ValueError(f"hub {hub_id} no está en la lista {network}: {sorted(table)}")
        return hub_id, table[hub_id]
    for hub_id, url in table.items():
        if str(hub).rstrip("/") in (url, url.removeprefix("https://")):
            return hub_id, url
    raise ValueError(f"hub desconocido: {hub!r}")


_ERRORS = {
    400: "petición rechazada (nonce repetido o formato inválido)",
    401: "firma inválida o clave no autorizada por el hub",
    409: "ya existe una declaración con esta misma huella",
    422: "el hub rechazó un campo",
    503: "el hub no pudo resolver su did.json; publíquelo y reintente",
}


def _request(url: str, method: str = "GET", body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": f"TDM-Seal/{__version__}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read() or b"null")
        except ValueError:
            detail = None
        message = _ERRORS.get(exc.code, f"error HTTP {exc.code}")
        if isinstance(detail, dict) and detail.get("error"):
            message += f": {detail['error']}"
        raise HubError(message) from exc
    except urllib.error.URLError as exc:
        raise HubError(f"no se pudo contactar con el hub: {exc.reason}") from exc


def declare(note: dict, base_url: str, *, timeout: float = 30) -> dict:
    """Envía la nota. Devuelve {'iscc_id', 'seq', 'receipt'}."""
    base = base_url.rstrip("/")
    status, ack = _request(f"{base}/declaration", "POST", note, timeout)
    if status != 201 or not isinstance(ack, dict) or "iscc_id" not in ack:
        raise HubError(f"respuesta inesperada del hub ({status}): {ack}")
    try:
        _, receipt = _request(f"{base}/declaration/{ack['iscc_id']}/receipt", timeout=timeout)
    except HubError:
        receipt = None  # se puede pedir después; la declaración ya existe
    return {"iscc_id": ack["iscc_id"], "seq": ack.get("seq"), "receipt": receipt}
