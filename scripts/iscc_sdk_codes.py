"""Imprime en JSON los códigos ISCC que calcula iscc-sdk para cada PDF dado.

Herramienta de desarrollo para comprobar que `tdmseal.iscc.content` produce
los mismos códigos que la implementación de referencia. Se corre con el
Python de un entorno donde esté instalado iscc-sdk (no es dependencia del
proyecto), p. ej.:

    %USERPROFILE%\\.venvs\\iscc-sdk-ref\\Scripts\\python.exe scripts\\iscc_sdk_codes.py a.pdf b.pdf
"""

from __future__ import annotations

import json
import sys

import iscc_sdk as idk


def main(paths: list[str]) -> None:
    out = {}
    for p in paths:
        meta = idk.code_iscc(p, create_thumb=False, add_units=True)
        out[p] = {"iscc": meta.iscc, "units": meta.units, "name": meta.name}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
