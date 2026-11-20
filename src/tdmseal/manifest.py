"""Manifiesto de catálogo: una fila por obra, para registros ISCC abiertos o de
terceros y para negociar licencias en bloque.

No se sube nada a ningún sitio. La firma es opcional y local
(`ssh-keygen -Y sign`, incluido en Windows 10/11 y en cualquier OpenSSH):
prueba **quién** firmó el manifiesto. La fecha que contiene es la declarada
por quien lo genera; para una prueba de fecha ante terceros haría falta un
sello de tiempo RFC 3161, que requiere conexión y no se hace aquí.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pikepdf

from tdmseal import __version__
from tdmseal.discovery import document_kind
from tdmseal.documents import inspect_document
from tdmseal.tools import no_window
from tdmseal.xmp.parser import RDF_NS, find_rdf_root, parse_xmp

SIGNATURE_NAMESPACE = "tdm-seal-manifest"
DC_NS = "http://purl.org/dc/elements/1.1/"
PRISM_NAMESPACES = (
    "http://prismstandard.org/namespaces/basic/2.0/",
    "http://prismstandard.org/namespaces/basic/3.0/",
    "http://prismstandard.org/namespaces/basic/2.1/",
)
OPF_NS = "http://www.idpf.org/2007/opf"

COLUMNS = [
    "archivo",
    "formato",
    "titulo",
    "isbn",
    "sha256",
    "tamano_bytes",
    "iscc",
    "iscc_meta",
    "iscc_texto",
    "iscc_datos",
    "iscc_instancia",
    "iscc_texto_declarado",
    "iscc_original_declarado",
    "tdm_reserva",
    "tdm_politica",
    "aipref",
    "fecha_utc",
    "estado",
]

_ISBN_CANDIDATE = re.compile(r"(?:97[89][\d\- ]{10,14}|\d[\d\- ]{8,11}[\dXx])")


# ---- ISBN -----------------------------------------------------------------------


def _isbn_ok(digits: str) -> bool:
    # Identificadores de relleno ("0000000000000", visto en EPUB reales) pasan
    # el dígito de control: se exigen el prefijo GS1 y más de un dígito distinto.
    if len(set(digits.upper())) == 1:
        return False
    if len(digits) == 13 and digits.isdigit() and digits[:3] in ("978", "979"):
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
        return total % 10 == 0
    if len(digits) == 10 and digits[:9].isdigit() and (digits[9].isdigit() or digits[9] in "Xx"):
        total = sum((10 - i) * (10 if d in "Xx" else int(d)) for i, d in enumerate(digits))
        return total % 11 == 0
    return False


def normalize_isbn(text: str | None) -> str | None:
    """Devuelve el ISBN (solo dígitos) si `text` contiene uno con dígito de control válido."""
    if not text:
        return None
    for match in _ISBN_CANDIDATE.finditer(text):
        digits = re.sub(r"[\s-]", "", match.group(0)).upper()
        if _isbn_ok(digits):
            return digits
    return None


def _pdf_isbn_and_title(path: Path) -> tuple[str | None, str | None]:
    from tdmseal.pdf.docinfo import effective_docinfo

    info = effective_docinfo(path)
    title = info.get("/Title")
    isbn = normalize_isbn(info.get("/ISBN"))
    with pikepdf.open(path) as pdf:
        metadata = pdf.Root.get("/Metadata")
        raw = bytes(metadata.read_bytes()) if metadata is not None else None
    if raw:
        try:
            rdf = find_rdf_root(parse_xmp(raw))
        except ValueError:
            rdf = None
        if rdf is not None:
            candidates = []
            for ns in PRISM_NAMESPACES:
                for local in ("isbn", "eIsbn"):
                    for desc in rdf.iter(f"{{{RDF_NS}}}Description"):
                        value = desc.get(f"{{{ns}}}{local}")
                        if value:
                            candidates.append(value)
                    candidates += [el.text for el in rdf.iter(f"{{{ns}}}{local}") if el.text]
            for el in rdf.iter(f"{{{DC_NS}}}identifier"):
                candidates += [li.text for li in el.iter(f"{{{RDF_NS}}}li") if li.text]
                if el.text and el.text.strip():
                    candidates.append(el.text)
            for candidate in candidates:
                isbn = isbn or normalize_isbn(candidate)
            if not title:
                for el in rdf.iter(f"{{{DC_NS}}}title"):
                    texts = [li.text for li in el.iter(f"{{{RDF_NS}}}li") if li.text]
                    if texts:
                        title = texts[0]
                        break
    return isbn, title


def _epub_isbn_and_title(path: Path) -> tuple[str | None, str | None]:
    from tdmseal.epub.container import find_opf_path
    from tdmseal.epub.opf import parse_opf, read_dc

    with zipfile.ZipFile(path) as zf:
        root = parse_opf(zf.read(find_opf_path(zf)))
    isbn = None
    for el in root.iter(f"{{{DC_NS}}}identifier"):
        isbn = isbn or normalize_isbn(el.text)
    return isbn, read_dc(root, "title")


# ---- Manifiesto -----------------------------------------------------------------


@dataclass
class Manifest:
    generated_at: str
    publisher: dict | None
    rows: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "tool": "TDM Seal",
                "tool_version": __version__,
                "generated_at_utc": self.generated_at,
                "publisher": self.publisher,
                "works": self.rows,
            },
            indent=2,
            ensure_ascii=False,
        )

    def write(self, out: Path) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".json":
            out.write_text(self.to_json() + "\n", encoding="utf-8")
        elif out.suffix.lower() == ".csv":
            # utf-8-sig: Excel en Windows reconoce así los acentos.
            with open(out, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS)
                writer.writeheader()
                for row in self.rows:
                    writer.writerow({k: "" if row.get(k) is None else row.get(k) for k in COLUMNS})
        else:
            raise ValueError("el manifiesto debe terminar en .csv o .json")
        return out


def build_manifest(
    paths: list[Path],
    base_dir: Path | None = None,
    *,
    with_iscc: bool = True,
    aipref: str | None = None,
    publisher: dict | None = None,
) -> Manifest:
    from tdmseal.iscc.content import compute_content_iscc

    # timezone.utc y no datetime.UTC: el proyecto admite Python 3.10.
    stamp = datetime.now(timezone.utc).replace(microsecond=0)  # noqa: UP017
    now = stamp.isoformat().replace("+00:00", "Z")
    manifest = Manifest(generated_at=now, publisher=publisher)
    for path in paths:
        rel = (
            str(path.relative_to(base_dir))
            if base_dir and path.is_relative_to(base_dir)
            else path.name
        )
        row: dict = {
            "archivo": rel.replace("\\", "/"),
            "formato": document_kind(path),
            "fecha_utc": now,
        }
        try:
            info = inspect_document(path)
            if document_kind(path) == "epub":
                isbn, title = _epub_isbn_and_title(path)
            else:
                isbn, title = _pdf_isbn_and_title(path)
            row.update(
                titulo=title,
                isbn=isbn,
                sha256=info.sha256,
                tamano_bytes=path.stat().st_size,
                iscc=info.iscc,
                tdm_reserva=info.tdm.reservation,
                tdm_politica=info.tdm.policy_url,
                aipref=aipref,
                estado="ok" if info.tdm.reservation is not None else "sin TDM",
            )
            if info.declared_iscc is not None:
                row["iscc_texto_declarado"] = info.declared_iscc.content_code
                row["iscc_original_declarado"] = info.declared_iscc.source_iscc
            if with_iscc and not info.encrypted:
                full = compute_content_iscc(path)
                row.update(
                    iscc=full.iscc,
                    iscc_meta=full.meta_code,
                    iscc_texto=full.text_code,
                    iscc_datos=full.data_code,
                    iscc_instancia=full.instance_code,
                )
        except Exception as exc:  # noqa: BLE001 — una obra ilegible no tumba el catálogo
            row["estado"] = f"error: {exc}"
        manifest.rows.append(row)
    return manifest


# ---- Firma (opcional, local) ---------------------------------------------------


def ssh_keygen() -> str | None:
    return shutil.which("ssh-keygen")


def sign_file(path: Path, key: Path) -> Path:
    """Firma `path` con una clave SSH (`ssh-keygen -Y sign`). Devuelve el `.sig`."""
    binary = ssh_keygen()
    if binary is None:
        raise RuntimeError("no se encontró ssh-keygen (OpenSSH) para firmar")
    sig = Path(str(path) + ".sig")
    if sig.exists():
        sig.unlink()
    proc = subprocess.run(
        [binary, "-Y", "sign", "-f", str(key), "-n", SIGNATURE_NAMESPACE, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        **no_window(),
    )
    if proc.returncode != 0 or not sig.exists():
        raise RuntimeError(f"ssh-keygen no pudo firmar: {proc.stderr.strip()}")
    return sig


def verify_command(path: Path, signer: str = "editorial") -> str:
    """Comando para que un tercero verifique la firma (con un allowed_signers)."""
    return (
        f"ssh-keygen -Y verify -f allowed_signers -I {signer} -n {SIGNATURE_NAMESPACE} "
        f'-s "{path}.sig" < "{path}"'
    )
