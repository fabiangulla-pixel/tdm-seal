from __future__ import annotations

import json
from pathlib import Path

import pytest

from tdmseal import tools
from tdmseal.validation import verapdf_validator


def test_run_verapdf_skipped_when_not_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(tools, "find_verapdf", lambda: None)

    result = verapdf_validator.run_verapdf(tmp_path / "file.pdf")

    assert result["status"] == "SKIPPED"
    # El mensaje debe ser útil para quien usa el .exe, sin remitir al código fuente.
    message = result["issues"][0]
    assert "SKIPPED" in message
    assert "veraPDF" in message
    assert "https://software.verapdf.org/" in message
    assert ".py" not in message


def _report(compliant: bool, rules: list[str]) -> str:
    summaries = [
        {
            "specification": "ISO 19005-2:2011",
            "clause": c,
            "testNumber": 1,
            "status": "failed",
            "description": f"regla {c}",
        }
        for c in rules
    ]
    result = {"compliant": compliant, "details": {"ruleSummaries": summaries}}
    # Algunas versiones de veraPDF devuelven una lista de resultados.
    return "log previo\n" + json.dumps({"report": {"jobs": [{"validationResult": [result]}]}})


def _fake(monkeypatch, outputs: dict[str, str]):
    monkeypatch.setattr(tools, "find_verapdf", lambda: ["verapdf"])

    class Proc:
        def __init__(self, stdout):
            self.stdout, self.stderr = stdout, ""

    monkeypatch.setattr(
        verapdf_validator.subprocess, "run", lambda args, **kw: Proc(outputs[Path(args[-1]).name])
    )


def test_pass_when_compliant(monkeypatch, tmp_path):
    _fake(monkeypatch, {"out.pdf": _report(True, [])})
    assert verapdf_validator.run_verapdf(tmp_path / "out.pdf")["status"] == "PASS"


def test_fail_when_sealing_adds_violation(monkeypatch, tmp_path):
    _fake(monkeypatch, {"in.pdf": _report(True, []), "out.pdf": _report(False, ["6.6.2.3"])})

    result = verapdf_validator.run_verapdf(tmp_path / "out.pdf", tmp_path / "in.pdf")

    assert result["status"] == "FAIL"
    assert any("6.6.2.3" in i for i in result["issues"])


def test_preexisting_violations_do_not_fail(monkeypatch, tmp_path):
    _fake(
        monkeypatch,
        {"in.pdf": _report(False, ["6.2.11.4"]), "out.pdf": _report(False, ["6.2.11.4"])},
    )

    result = verapdf_validator.run_verapdf(tmp_path / "out.pdf", tmp_path / "in.pdf")

    assert result["status"] == "PASS"
    assert "ya incumplía 1" in result["issues"][0]


def test_fail_on_unparseable_output(monkeypatch, tmp_path):
    _fake(monkeypatch, {"out.pdf": "no es json"})
    assert verapdf_validator.run_verapdf(tmp_path / "out.pdf")["status"] == "FAIL"


@pytest.mark.real_tools
def test_real_verapdf_runs(tmp_path, make_pdf):
    if tools.find_verapdf() is None:
        pytest.skip("veraPDF no instalado")
    # Un PDF normal no es PDF/A: veraPDF debe responder (no conforme), no fallar al ejecutarse.
    result = verapdf_validator.run_verapdf(make_pdf("x.pdf"))
    assert result["status"] == "FAIL"
    assert "no conforme" in result["issues"][0]
