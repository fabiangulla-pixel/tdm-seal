"""PDF con firmas criptográficas reales (pyHanko en un entorno aparte).

pyHanko no es dependencia de TDM Seal. Si existe
`%USERPROFILE%\\.venvs\\pyhanko-ref` (o `TDMSEAL_PYHANKO_PY`), estas pruebas
firman PDF de verdad con un certificado autofirmado y verifican la firma con
pyHanko; si no, se omiten. Crear el entorno:

    py -3.12 -m venv %USERPROFILE%\\.venvs\\pyhanko-ref
    %USERPROFILE%\\.venvs\\pyhanko-ref\\Scripts\\python -m pip install pyhanko==0.29.1
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

import tdmseal.cli as cli_module
from tdmseal.appconfig import AppDefaults
from tdmseal.config import SealConfig
from tdmseal.documents import seal_document
from tdmseal.models import TDMPolicy

pytestmark = pytest.mark.real_tools

HELPER = Path(__file__).with_name("pyhanko_helper.py")
POLICY = TDMPolicy(1, "https://editorial.example.edu/tdm/policies/1")


def _pyhanko_python() -> Path:
    configured = os.environ.get("TDMSEAL_PYHANKO_PY")
    candidate = (
        Path(configured)
        if configured
        else Path.home() / ".venvs" / "pyhanko-ref" / "Scripts" / "python.exe"
    )
    if not candidate.exists():
        pytest.skip("pyHanko de referencia no instalado")
    return candidate


def _helper(*args: object) -> str:
    proc = subprocess.run(
        [str(_pyhanko_python()), "-I", str(HELPER), *map(str, args)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return proc.stdout.strip()


@pytest.fixture
def signed(tmp_path, make_text_pdf):
    def _make(mode: str) -> Path:
        out = tmp_path / f"{mode}.pdf"
        _helper(mode, make_text_pdf("src.pdf", title="Firmado"), out, tmp_path / "claves")
        return out

    return _make


@pytest.mark.parametrize("mode", ["sign", "certify"])
def test_really_signed_pdf_is_refused_and_untouched(signed, mode, tmp_path):
    path = signed(mode)
    before = path.read_bytes()
    assert _helper("verify", path, tmp_path / "claves") == "intact"

    result = seal_document(path, SealConfig(policy=POLICY))

    assert result.status == "skipped"
    assert result.reason_code == "TDM021"
    assert result.output_path is None
    assert path.read_bytes() == before
    assert _helper("verify", path, tmp_path / "claves") == "intact"


def test_empty_signature_field_is_sealed(signed):
    """Un campo de firma vacío (para firmar después) no impide sellar."""
    result = seal_document(signed("field"), SealConfig(policy=POLICY))

    assert result.status == "success", result.warnings


def test_forced_seal_warns_that_signature_is_broken(signed, tmp_path, monkeypatch):
    """--force-signed invalida la firma (comprobado con pyHanko) y debe decirlo claro."""
    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())
    path = signed("sign")

    out = CliRunner().invoke(cli_module.main, ["seal", str(path), "--force-signed"])

    assert out.exit_code == 0, out.output
    assert "firma digital del original NO es válida" in out.output
    sealed = tmp_path / "sign_TDM.pdf"
    assert _helper("verify", sealed, tmp_path / "claves") == "broken"
    assert _helper("verify", path, tmp_path / "claves") == "intact"  # el original, intacto
