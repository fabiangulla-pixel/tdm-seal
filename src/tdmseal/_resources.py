"""Rutas a los recursos empaquetados (`tdmseal/resources/`).

Viven dentro del paquete para que funcionen igual instalado con
`pip install` (no editable), en modo editable y congelado con PyInstaller
(`build_exe.bat` los copia a `tdmseal/resources` dentro del .exe).
"""

from __future__ import annotations

from pathlib import Path

_RESOURCES = Path(__file__).resolve().parent / "resources"


def resource_path(*parts: str) -> Path:
    return _RESOURCES.joinpath(*parts)
