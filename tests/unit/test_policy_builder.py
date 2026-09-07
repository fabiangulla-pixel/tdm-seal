from __future__ import annotations

import json
from pathlib import Path

import pytest

from tdmseal.models import PublisherInfo
from tdmseal.policy.builder import (
    PolicyOptions,
    build_policy_artifacts,
    domain_from_website,
    write_policy_artifacts,
)


def _publisher(**overrides) -> PublisherInfo:
    data = {
        "name": "Editorial Universidad Ejemplo",
        "acronym": "EUE",
        "website": "https://editorial.example.edu",
        "rights_email": "derechos@editorial.example.edu",
    }
    data.update(overrides)
    return PublisherInfo(**data)


def test_domain_from_website_strips_scheme():
    assert domain_from_website("https://editorial.example.edu/tdm") == "editorial.example.edu"
    assert domain_from_website("editorial.example.edu") == "editorial.example.edu"


def test_domain_from_website_rejects_unparseable():
    with pytest.raises(ValueError):
        domain_from_website("")


def test_build_policy_artifacts_requires_name_website_email():
    with pytest.raises(ValueError):
        build_policy_artifacts(PublisherInfo(), PolicyOptions())


def test_build_policy_artifacts_produces_three_files():
    artifacts = build_policy_artifacts(_publisher(), PolicyOptions())

    assert set(artifacts) == {"policy.jsonld", "policy.html", "tdmrep.json"}

    jsonld = json.loads(artifacts["policy.jsonld"])
    assert jsonld["assigner"]["vcard:fn"] == "Editorial Universidad Ejemplo"
    assert jsonld["assigner"]["vcard:hasEmail"] == "mailto:derechos@editorial.example.edu"
    assert jsonld["uid"] == "https://editorial.example.edu/tdm/policies/1"

    tdmrep = json.loads(artifacts["tdmrep.json"])
    assert tdmrep == [
        {
            "location": "/",
            "tdm-reservation": 1,
            "tdm-policy": "https://editorial.example.edu/tdm/policies/1",
        }
    ]

    assert "Editorial Universidad Ejemplo" in artifacts["policy.html"]
    assert "derechos@editorial.example.edu" in artifacts["policy.html"]


def test_require_compensation_adds_duty_and_mentions_it():
    artifacts = build_policy_artifacts(_publisher(), PolicyOptions(require_compensation=True))

    jsonld = json.loads(artifacts["policy.jsonld"])
    duties = {d["action"] for d in jsonld["permission"][0]["duty"]}
    assert duties == {"obtainConsent", "compensate"}
    assert "compensación económica" in artifacts["policy.html"]


def test_html_escapes_publisher_name():
    artifacts = build_policy_artifacts(
        _publisher(name="Editorial <Ejemplo> & Cía"), PolicyOptions()
    )

    assert "<Ejemplo>" not in artifacts["policy.html"]
    assert "&lt;Ejemplo&gt;" in artifacts["policy.html"]


def test_write_policy_artifacts_creates_files(tmp_path: Path):
    output_dir = tmp_path / "policy_out"

    paths = write_policy_artifacts(output_dir, _publisher(), PolicyOptions())

    assert set(paths) == {"policy.jsonld", "policy.html", "tdmrep.json"}
    for path in paths.values():
        assert path.exists()
        assert path.parent == output_dir
