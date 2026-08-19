"""Detección de cifrado en un PDF."""

from __future__ import annotations

import pikepdf


def is_encrypted(pdf: pikepdf.Pdf) -> bool:
    return bool(pdf.is_encrypted)
