"""Lectura del contenedor EPUB (ZIP): OPF, versión y detección de DRM/cifrado.

Referencias: EPUB 3.3 (W3C), sección "Open Container Format"; OPF 2.0.1 (IDPF).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

CONTAINER_PATH = "META-INF/container.xml"
ENCRYPTION_PATH = "META-INF/encryption.xml"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
XMLENC_NS = "http://www.w3.org/2001/04/xmlenc#"
OPF_NS = "http://www.idpf.org/2007/opf"
MIMETYPE = b"application/epub+zip"

# Ofuscación de fuentes: no es DRM ni impide leer el libro (EPUB 3.3, sec. 4.3;
# algoritmo de Adobe usado por libros EPUB 2). Se tolera.
FONT_OBFUSCATION_ALGORITHMS = {
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
}
# Archivos que delatan DRM aunque no haya encryption.xml legible.
DRM_MARKERS = {
    "META-INF/rights.xml": "Adobe ADEPT (META-INF/rights.xml)",
    "META-INF/license.lcpl": "Readium LCP (META-INF/license.lcpl)",
}


class EpubError(ValueError):
    """El archivo no es un EPUB legible."""


@dataclass(frozen=True)
class EpubContainer:
    opf_path: str
    version: str  # "2.0", "3.0", "3.3"…
    drm: str | None  # descripción del DRM/cifrado detectado, o None
    obfuscated_fonts: int
    mimetype_ok: bool  # 'mimetype' primero, sin comprimir y con el valor correcto


def _parse_xml(data: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        return etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise EpubError(f"XML malformado: {exc}") from exc


def find_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        root = _parse_xml(zf.read(CONTAINER_PATH))
    except KeyError as exc:
        raise EpubError("falta META-INF/container.xml") from exc
    rootfile = root.find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise EpubError("container.xml no declara el paquete OPF (rootfile)")
    return rootfile.get("full-path")


def _detect_drm(zf: zipfile.ZipFile) -> tuple[str | None, int]:
    names = set(zf.namelist())
    for marker, label in DRM_MARKERS.items():
        if marker in names:
            return label, 0
    if ENCRYPTION_PATH not in names:
        return None, 0
    root = _parse_xml(zf.read(ENCRYPTION_PATH))
    obfuscated = 0
    encrypted: list[str] = []
    for enc_data in root.iter(f"{{{XMLENC_NS}}}EncryptedData"):
        method = enc_data.find(f"{{{XMLENC_NS}}}EncryptionMethod")
        algorithm = method.get("Algorithm") if method is not None else None
        ref = enc_data.find(f".//{{{XMLENC_NS}}}CipherReference")
        uri = ref.get("URI") if ref is not None else "?"
        if algorithm in FONT_OBFUSCATION_ALGORITHMS:
            obfuscated += 1
        else:
            encrypted.append(uri)
    if encrypted:
        shown = ", ".join(encrypted[:3]) + ("…" if len(encrypted) > 3 else "")
        return f"recursos cifrados en META-INF/encryption.xml ({shown})", obfuscated
    return None, obfuscated


def read_container(path: Path) -> EpubContainer:
    """Inspecciona el contenedor sin modificarlo. Lanza EpubError si no es un EPUB."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise EpubError(f"no es un ZIP/EPUB legible: {exc}") from exc
    with zf:
        infos = zf.infolist()
        mimetype_ok = bool(
            infos
            and infos[0].filename == "mimetype"
            and infos[0].compress_type == zipfile.ZIP_STORED
            and zf.read("mimetype").strip() == MIMETYPE
        )
        opf_path = find_opf_path(zf)
        try:
            opf_root = _parse_xml(zf.read(opf_path))
        except KeyError as exc:
            raise EpubError(f"el paquete OPF declarado no existe: {opf_path}") from exc
        version = opf_root.get("version") or "?"
        drm, obfuscated = _detect_drm(zf)
    return EpubContainer(
        opf_path=opf_path,
        version=version,
        drm=drm,
        obfuscated_fonts=obfuscated,
        mimetype_ok=mimetype_ok,
    )
