"""Interoperabilidad con la implementación de referencia (iscc-crypto).

`iscc_crypto.verify_json` es la función con la que el hub ISCC verifica las
firmas (iscc_hub/validators.py). Se ejecuta en un entorno aparte
(`%USERPROFILE%\\.venvs\\iscc-crypto-ref`); si no existe, se omite.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tdmseal.iscc import hub as h

REF = Path.home() / ".venvs" / "iscc-crypto-ref" / "Scripts" / "python.exe"
pytestmark = pytest.mark.skipif(not REF.exists(), reason="iscc-crypto de referencia no instalado")

CHECK = r"""
import json, sys
import iscc_crypto as icr
data = json.load(open(sys.argv[1], encoding="utf-8"))
kp = icr.key_from_secret(data["secret"], controller=data["controller"])
res = icr.verify_json(data["note"], identity_doc=None, raise_on_error=False)
print(json.dumps({
    "public_key": kp.public_key,
    "did": kp.controller_document,
    "signature_valid": res.signature_valid,
    "their_note": icr.sign_json({"iscc_code": "ISCC:X", "n": 1}, kp),
}))
"""


def _run(tmp_path, payload: dict) -> dict:
    data = tmp_path / "entrada.json"
    data.write_text(json.dumps(payload), encoding="utf-8")
    script = tmp_path / "check.py"
    script.write_text(CHECK, encoding="utf-8")
    out = subprocess.run(
        [str(REF), "-I", str(script), str(data)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout
    return json.loads(out)


def test_reference_accepts_our_keys_signatures_and_did(tmp_path):
    pytest.importorskip("pypdfium2")
    from tdmseal.samples import SAMPLE_TEXT, build_text_pdf

    key = h.generate_key("editorial.org")
    pdf = build_text_pdf(tmp_path / "obra.pdf", SAMPLE_TEXT, title="Obra")
    note = h.build_note(pdf, key, 1, "https://editorial.org/registro/obra/1.html")

    ref = _run(tmp_path, {"secret": key.secret_key, "controller": key.controller, "note": note})

    assert ref["public_key"] == key.public_key
    assert ref["did"] == key.did_document()
    assert ref["signature_valid"] is True
    # Y al revés: nuestra verificación acepta una firma hecha por iscc-crypto.
    assert h.verify_note(ref["their_note"])
