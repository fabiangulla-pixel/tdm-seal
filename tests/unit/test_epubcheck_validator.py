from __future__ import annotations

import json
from pathlib import Path

from tdmseal.validation import epubcheck_validator as ev


def test_skipped_when_not_installed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ev, "_command", lambda: None)

    result = ev.run_epubcheck(tmp_path / "a.epub", tmp_path / "b.epub")

    assert result["status"] == "SKIPPED"
    assert "EPUBCheck" in result["issues"][0]
    assert "TDMSEAL_EPUBCHECK_JAR" in result["issues"][0]


def _fake_runner(errors_by_file: dict[str, list[dict]]):
    def fake_run(args, **kwargs):
        target = Path(args[-3]).name
        report = Path(args[-1])
        report.write_text(json.dumps({"messages": errors_by_file[target]}), encoding="utf-8")

    return fake_run


def test_preexisting_errors_do_not_fail(monkeypatch, tmp_path: Path):
    shared = [{"ID": "RSC-005", "severity": "ERROR", "message": "ya estaba"}]
    monkeypatch.setattr(ev, "_command", lambda: ["epubcheck"])
    monkeypatch.setattr(ev.subprocess, "run", _fake_runner({"in.epub": shared, "out.epub": shared}))

    result = ev.run_epubcheck(tmp_path / "in.epub", tmp_path / "out.epub")

    assert result["status"] == "PASS"
    assert "ya tenía 1 error" in result["issues"][0]


def test_new_error_fails(monkeypatch, tmp_path: Path):
    new = [{"ID": "OPF-027", "severity": "ERROR", "message": "propiedad no declarada"}]
    monkeypatch.setattr(ev, "_command", lambda: ["epubcheck"])
    monkeypatch.setattr(ev.subprocess, "run", _fake_runner({"in.epub": [], "out.epub": new}))

    result = ev.run_epubcheck(tmp_path / "in.epub", tmp_path / "out.epub")

    assert result["status"] == "FAIL"
    assert "OPF-027" in result["issues"][0]


def test_warnings_are_ignored(monkeypatch, tmp_path: Path):
    warn = [{"ID": "ACC-001", "severity": "WARNING", "message": "aviso"}]
    monkeypatch.setattr(ev, "_command", lambda: ["epubcheck"])
    monkeypatch.setattr(ev.subprocess, "run", _fake_runner({"in.epub": [], "out.epub": warn}))

    assert ev.run_epubcheck(tmp_path / "in.epub", tmp_path / "out.epub")["status"] == "PASS"
