from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import tdmseal.cli as cli_module
from tdmseal.aipref import default_preferences
from tdmseal.appconfig import AppDefaults
from tdmseal.site import build_site_artifacts, validate_tdmrep_json, write_site_artifacts

POLICY = "https://editorial.ejemplo/tdm/policies/1"


@pytest.fixture(autouse=True)
def isolated_defaults(monkeypatch):
    monkeypatch.setattr(cli_module, "load_defaults", lambda *a, **k: AppDefaults())


def test_tdmrep_json_matches_spec_example():
    files = build_site_artifacts("https://editorial.ejemplo", 1, POLICY, default_preferences())

    data = json.loads(files[".well-known/tdmrep.json"])
    assert data == [{"location": "/", "tdm-reservation": 1, "tdm-policy": POLICY}]
    assert validate_tdmrep_json(data) == ([], [])


def test_server_snippets_contain_headers():
    files = build_site_artifacts("https://editorial.ejemplo/", 1, POLICY, default_preferences())

    apache, nginx = files["servidor/apache.conf"], files["servidor/nginx.conf"]
    assert 'Header always set tdm-reservation "1"' in apache
    assert f'Header always set tdm-policy "{POLICY}"' in apache
    assert 'Header always set Content-Usage "train-ai=n, ai-use=n, search=y"' in apache
    assert 'add_header tdm-reservation "1" always;' in nginx
    assert 'add_header Content-Usage "train-ai=n, ai-use=n, search=y" always;' in nginx
    robots = files["servidor/robots-content-usage.txt"]
    assert "User-Agent: *\nContent-Usage: train-ai=n, ai-use=n, search=y\n" in robots
    assert '<meta name="tdm-reservation" content="1">' in files["servidor/html-meta.html"]
    assert "https://editorial.ejemplo/.well-known/tdmrep.json" in files["LEEME.txt"]


def test_without_policy_or_aipref_omits_those_lines():
    files = build_site_artifacts("https://e.ejemplo", 1, None, None)

    assert "tdm-policy" not in files["servidor/apache.conf"]
    assert "add_header Content-Usage" not in files["servidor/nginx.conf"]
    assert "servidor/robots-content-usage.txt" not in files


def test_invalid_base_url_rejected():
    with pytest.raises(ValueError):
        build_site_artifacts("editorial.ejemplo", 1, None, None)


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"location": "/", "tdm-reservation": 1}, "arreglo"),
        ([{"tdm-reservation": 1}], "location"),
        ([{"location": "sin-barra", "tdm-reservation": 1}], "location"),
        ([{"location": "/a$b", "tdm-reservation": 1}], "location"),
        ([{"location": "/", "tdm-reservation": True}], "0 o 1"),
        ([{"location": "/", "tdm-reservation": "1"}], "0 o 1"),
        ([{"location": "/", "tdm-reservation": 1, "tdm-policy": "ftp://x"}], "URL"),
        ([], "ninguna regla"),
    ],
)
def test_validator_errors(data, fragment):
    errors, _ = validate_tdmrep_json(data)
    assert any(fragment in e for e in errors), errors


def test_validator_warnings():
    data = [{"location": "/*.jpg$", "tdm-reservation": 0, "tdm-policy": POLICY, "otra": 1}]
    errors, warnings = validate_tdmrep_json(data)
    assert errors == []
    assert len(warnings) == 2


def test_cli_site_generates_files(tmp_path):
    out = tmp_path / "publicar"
    result = CliRunner().invoke(
        cli_module.main,
        ["site", "--base-url", "https://editorial.ejemplo/", "--out", str(out), "--policy", POLICY],
    )

    assert result.exit_code == 0, result.output
    assert (out / ".well-known" / "tdmrep.json").exists()
    assert (out / "servidor" / "nginx.conf").exists()
    check = CliRunner().invoke(
        cli_module.main, ["site", "--check", str(out / ".well-known" / "tdmrep.json")]
    )
    assert check.exit_code == 0
    assert "[OK]" in check.output


def test_cli_site_check_reports_errors(tmp_path):
    bad = tmp_path / "tdmrep.json"
    bad.write_text('{"location": "/"}', encoding="utf-8")

    result = CliRunner().invoke(cli_module.main, ["site", "--check", str(bad)])

    assert result.exit_code == 1
    assert "[ERROR]" in result.output


def test_cli_site_rejects_unknown_aipref_category(tmp_path):
    result = CliRunner().invoke(
        cli_module.main,
        ["site", "--base-url", "https://e.ejemplo", "--out", str(tmp_path), "--aipref", "tdm=n"],
    )
    assert result.exit_code == 2
    assert "desconocida" in result.output


def test_cli_site_warns_on_contradiction(tmp_path):
    result = CliRunner().invoke(
        cli_module.main,
        ["site", "--base-url", "https://e.ejemplo", "--out", str(tmp_path), "--reservation", "0"],
    )
    assert "Contradicción" in result.output


def test_write_uses_lf_line_endings(tmp_path):
    files = build_site_artifacts("https://e.ejemplo", 1, None, default_preferences())
    paths = write_site_artifacts(tmp_path, files)
    assert b"\r\n" not in paths["servidor/nginx.conf"].read_bytes()
