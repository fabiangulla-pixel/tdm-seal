"""Firma PDF de prueba con pyHanko (se ejecuta en un entorno aparte, no en el del proyecto).

pyHanko no es dependencia de TDM Seal: las pruebas lo invocan con el Python de
`%USERPROFILE%\\.venvs\\pyhanko-ref` (o `TDMSEAL_PYHANKO_PY`) si existe.

Uso:
    python pyhanko_helper.py sign|certify|field ENTRADA SALIDA CARPETA_CLAVES
    python pyhanko_helper.py verify ENTRADA CARPETA_CLAVES   -> imprime "intact" o "broken"
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path


def _make_keys(folder: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key_path, cert_path = folder / "clave.pem", folder / "cert.pem"
    if key_path.exists() and cert_path.exists():
        return key_path, cert_path
    folder.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Editorial Ejemplo (prueba)")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, True, False, False, False, True, False, False, False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def sign(mode: str, src: Path, out: Path, keys: Path) -> None:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    key_path, cert_path = _make_keys(keys)
    with src.open("rb") as inf:
        # strict=False: PDF reales (p. ej. guardados por MuPDF) pueden traer
        # generaciones huérfanas que el modo estricto rechaza; Acrobat las acepta.
        writer = IncrementalPdfFileWriter(inf, strict=False)
        if mode == "field":
            fields.append_signature_field(
                writer, fields.SigFieldSpec("FirmaVacia", box=(20, 20, 220, 70))
            )
            with out.open("wb") as outf:
                writer.write(outf)
            return
        signer = signers.SimpleSigner.load(str(key_path), str(cert_path))
        meta = signers.PdfSignatureMetadata(field_name="Firma1", certify=mode == "certify")
        with out.open("wb") as outf:
            signers.sign_pdf(writer, meta, signer=signer, output=outf)


def detail(path: Path, keys: Path) -> str:
    """'intacta=… nivel=… docmdp_ok=… veredicto=…' para la primera firma."""
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    _, cert_path = _make_keys(keys)
    context = ValidationContext(trust_roots=[load_cert_from_pemder(str(cert_path))])
    with path.open("rb") as f:
        status = validate_pdf_signature(
            PdfFileReader(f, strict=False).embedded_signatures[0], context
        )
        level = status.modification_level.name if status.modification_level else None
        return (
            f"intacta={status.intact} valida={status.valid} nivel={level} "
            f"docmdp_ok={status.docmdp_ok} veredicto={status.bottom_line}"
        )


def verify(path: Path, keys: Path) -> str:
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    _, cert_path = _make_keys(keys)
    context = ValidationContext(trust_roots=[load_cert_from_pemder(str(cert_path))])
    with path.open("rb") as f:
        reader = PdfFileReader(f, strict=False)
        if not reader.embedded_signatures:
            return "unsigned"
        status = validate_pdf_signature(reader.embedded_signatures[0], context)
        return "intact" if status.intact and status.valid else "broken"


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "verify":
        print(verify(Path(sys.argv[2]), Path(sys.argv[3])))
    elif command == "detail":
        print(detail(Path(sys.argv[2]), Path(sys.argv[3])))
    else:
        sign(command, Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
