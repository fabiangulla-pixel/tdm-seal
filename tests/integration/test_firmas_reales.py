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
    def _make(mode: str, src: Path | None = None) -> Path:
        out = tmp_path / f"{mode}.pdf"
        src = src or make_text_pdf("src.pdf", title="Firmado")
        _helper(mode, src, out, tmp_path / "claves")
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


@pytest.mark.parametrize("mode", ["sign", "certify"])
@pytest.mark.parametrize("xref_streams", [False, True])
def test_forced_seal_keeps_signature_valid(
    signed, tmp_path, monkeypatch, make_text_pdf, mode, xref_streams
):
    """--force-signed sella con una actualización incremental y la firma sigue válida.

    pyHanko clasifica el cambio como LTA_UPDATES (el nivel más benigno, el de
    un sello de tiempo) y lo admite incluso en una firma de certificación.
    """
    import pikepdf

    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())
    src = make_text_pdf("src.pdf", title="Firmado")
    if xref_streams:
        with pikepdf.open(src, allow_overwriting_input=True) as pdf:
            pdf.save(src, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    path = signed(mode, src)

    out = CliRunner().invoke(cli_module.main, ["seal", str(path), "--force-signed", "--iscc"])

    assert out.exit_code == 0, out.output
    assert "1 correctos" in out.output
    assert "la firma sigue siendo válida" in out.output
    sealed = tmp_path / f"{mode}_TDM.pdf"
    detail = _helper("detail", sealed, tmp_path / "claves")
    assert "intacta=True valida=True" in detail
    assert "docmdp_ok=True veredicto=True" in detail
    assert "nivel=LTA_UPDATES" in detail


def test_forced_seal_of_signed_pdfa_keeps_signature_and_pdfa(signed, tmp_path):
    """PDF/A-2b firmado: el XMP existente se reemplaza en su sitio y veraPDF sigue en PASS."""
    from tdmseal import tools

    gs = tools.tools_dir() / "gs"
    if not (gs / "bin" / "gswin64c.exe").exists() or tools.find_verapdf() is None:
        pytest.skip("Ghostscript o veraPDF no instalados")
    from tests.integration.test_real_tools import _pdfa_from

    path = signed("sign", _pdfa_from(gs, tmp_path, 2))

    result = seal_document(path, SealConfig(policy=POLICY, force_signed=True, compute_iscc=True))

    assert result.status == "success", result.warnings
    assert result.validations["signature_preserved"] == "PASS"
    assert result.validations["verapdf"] == "PASS"
    assert "intacta=True valida=True" in _helper("detail", result.output_path, tmp_path / "claves")
