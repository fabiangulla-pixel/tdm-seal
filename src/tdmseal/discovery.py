"""Descubrimiento de archivos PDF a partir de un archivo o una carpeta.

Compartido entre la CLI y la GUI para no duplicar la lógica de recorrido.
"""

from __future__ import annotations

from pathlib import Path


def iter_pdfs(target: Path, recursive: bool = False) -> list[Path]:
    target = Path(target)
    if target.is_file():
        return [target]
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in target.glob(pattern) if p.is_file())
