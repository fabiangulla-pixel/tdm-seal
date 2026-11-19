"""Identificadores ISCC (ISO 24138).

- `compute_iscc`: huella de los bytes (Data-Code + Instance-Code). Rápida;
  la usan `inspect`, `show` y `audit`. Cambia al sellar.
- `compute_content_iscc`: ISCC-CODE completo (Meta + Text + Data + Instance).
  El Text-Code se calcula sobre el texto y no cambia al sellar.
"""

from tdmseal.iscc.content import (
    ContentIscc,
    compute_content_iscc,
    content_extra_available,
)
from tdmseal.iscc.data import IsccResult, compute_iscc

__all__ = [
    "ContentIscc",
    "IsccResult",
    "compute_content_iscc",
    "compute_iscc",
    "content_extra_available",
]
