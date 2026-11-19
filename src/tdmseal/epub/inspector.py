"""Inspección de un EPUB sin modificarlo: versión, DRM, mimetype, TDMRep e ISCC."""

from __future__ import annotations

import zipfile
from pathlib import Path

from tdmseal.epub.container import EpubError, read_container
from tdmseal.epub.opf import parse_opf, read_iscc, read_tdm
from tdmseal.errors import TDM005_EPUB_INVALID, TDMSealError
from tdmseal.iscc.data import compute_iscc
from tdmseal.models import EPUBInfo
from tdmseal.pdf.inspector import sha256_file


def read_opf_bytes(path: Path, opf_path: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(opf_path)


def inspect_epub(path: Path) -> EPUBInfo:
    """Inspecciona un EPUB. Lanza TDMSealError (TDM005) si no es un EPUB legible."""
    path = Path(path)
    try:
        container = read_container(path)
        opf_root = parse_opf(read_opf_bytes(path, container.opf_path))
        tdm = read_tdm(opf_root)
        declared = read_iscc(opf_root)
    except (EpubError, ValueError, KeyError) as exc:
        raise TDMSealError(TDM005_EPUB_INVALID, f"No se pudo leer el EPUB: {path} ({exc})") from exc

    return EPUBInfo(
        path=path,
        epub_version=container.version,
        opf_path=container.opf_path,
        drm=container.drm,
        obfuscated_fonts=container.obfuscated_fonts,
        mimetype_ok=container.mimetype_ok,
        tdm=tdm,
        sha256=sha256_file(path),
        iscc=compute_iscc(path).iscc,
        declared_iscc=declared,
    )
