"""Descubrimiento de documentos (PDF y EPUB) a partir de un archivo o una carpeta.

Compartido entre la CLI y la GUI para no duplicar la lógica de recorrido.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = (".pdf", ".epub")


def document_kind(path: Path) -> str | None:
    """'pdf', 'epub' o None según la extensión (sin distinguir mayúsculas)."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    return None


def iter_documents(
    target: Path, recursive: bool = False, suffixes: tuple[str, ...] = SUPPORTED_SUFFIXES
) -> list[Path]:
    """Archivos PDF/EPUB de `target` (o `target` mismo si es un archivo)."""
    target = Path(target)
    if target.is_file():
        return [target]
    candidates = target.rglob("*") if recursive else target.glob("*")
    return sorted(p for p in candidates if p.is_file() and p.suffix.lower() in suffixes)


def iter_pdfs(target: Path, recursive: bool = False) -> list[Path]:
    """Solo PDF (compatibilidad con versiones anteriores)."""
    return iter_documents(target, recursive, suffixes=(".pdf",))
