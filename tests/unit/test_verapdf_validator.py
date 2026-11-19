from __future__ import annotations

import json
from pathlib import Path

from tdmseal.validation import verapdf_validator


def test_run_verapdf_skipped_when_not_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(verapdf_validator.shutil, "which", lambda name: None)

    result = verapdf_validator.run_verapdf(tmp_path / "file.pdf")

    assert result["status"] == "SKIPPED"
    # El mensaje debe ser útil para quien usa el .exe, sin remitir al código fuente.
    message = result["issues"][0]
    assert "SKIPPED" in message
    assert "veraPDF" in message
    assert "https://software.verapdf.org/" in message
    assert ".py" not in message


def test_run_verapdf_pass_when_compliant(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        verapdf_validator.shutil, "which", lambda name: "verapdf" if name == "verapdf" else None
    )

    class FakeProc:
        stdout = json.dumps({"report": {"jobs": [{"validationResult": {"compliant": True}}]}})

    monkeypatch.setattr(verapdf_validator.subprocess, "run", lambda *a, **kw: FakeProc())

    result = verapdf_validator.run_verapdf(tmp_path / "file.pdf")

    assert result["status"] == "PASS"


def test_run_verapdf_fail_when_not_compliant(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        verapdf_validator.shutil, "which", lambda name: "verapdf" if name == "verapdf" else None
    )

    class FakeProc:
        stdout = json.dumps({"report": {"jobs": [{"validationResult": {"compliant": False}}]}})

    monkeypatch.setattr(verapdf_validator.subprocess, "run", lambda *a, **kw: FakeProc())

    result = verapdf_validator.run_verapdf(tmp_path / "file.pdf")

    assert result["status"] == "FAIL"


def test_run_verapdf_fail_on_unparseable_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        verapdf_validator.shutil, "which", lambda name: "verapdf" if name == "verapdf" else None
    )

    class FakeProc:
        stdout = "not json"

    monkeypatch.setattr(verapdf_validator.subprocess, "run", lambda *a, **kw: FakeProc())

    result = verapdf_validator.run_verapdf(tmp_path / "file.pdf")

    assert result["status"] == "FAIL"
