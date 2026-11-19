from __future__ import annotations

import json
from pathlib import Path

import pytest

from tdmseal.aipref import default_preferences
from tdmseal.models import PublisherInfo
from tdmseal.policy.builder import (
    PolicyOptions,
    build_policy_artifacts,
    domain_from_website,
    write_policy_artifacts,
)
from tdmseal.policy.policy_validator import validate_policy_jsonld


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


def _jsonld(**options) -> dict:
    return json.loads(
        build_policy_artifacts(_publisher(), PolicyOptions(**options))["policy.jsonld"]
    )


def test_jsonld_follows_tdmrep_profile():
    policy = _jsonld()

    assert policy["@context"] == [
        "http://www.w3.org/ns/odrl.jsonld",
        "http://www.w3.org/ns/tdmrep.jsonld",
    ]
    assert policy["@type"] == "Offer"
    assert policy["profile"] == "http://www.w3.org/ns/tdmrep"
    assert policy["assigner"]["vcard:nickname"] == "EUE"
    assert policy["assigner"]["vcard:hasURL"] == "https://editorial.example.edu"
    assert "prohibition" not in policy and "obligation" not in policy
    assert validate_policy_jsonld(policy) == []


def test_different_terms_per_purpose_use_purpose_constraint():
    policy = _jsonld(research="consent", non_research="compensate")

    by_purpose = {
        p["constraint"][0]["rightOperand"]: {d["action"] for d in p["duty"]}
        for p in policy["permission"]
    }
    assert by_purpose == {
        "tdm:research": {"obtainConsent"},
        "tdm:non-research": {"obtainConsent", "compensate"},
    }


def test_not_offered_purpose_is_omitted_not_prohibited():
    policy = _jsonld(research="consent", non_research="none")

    assert len(policy["permission"]) == 1
    assert policy["permission"][0]["constraint"][0]["rightOperand"] == "tdm:research"
    assert "prohibition" not in policy


def test_nothing_offered_is_rejected():
    with pytest.raises(ValueError, match="ningún"):
        _jsonld(research="none", non_research="none")


def test_free_term_has_no_duty():
    policy = _jsonld(research="free", non_research="free")
    assert policy["permission"] == [{"action": "tdm:mine"}]


def test_explicit_policy_url_is_used_everywhere():
    url = "https://otro.example.org/politicas/tdm.jsonld"
    artifacts = build_policy_artifacts(_publisher(), PolicyOptions(policy_url=url))

    assert json.loads(artifacts["policy.jsonld"])["uid"] == url
    assert json.loads(artifacts["tdmrep.json"])[0]["tdm-policy"] == url
    assert url in artifacts["policy.html"]


def test_invalid_policy_url_rejected():
    with pytest.raises(ValueError):
        build_policy_artifacts(_publisher(), PolicyOptions(policy_url="politica.jsonld"))


def test_html_is_an_invitation_to_license_and_shows_terms():
    html = build_policy_artifacts(
        _publisher(),
        PolicyOptions(research="consent", non_research="compensate", aipref=default_preferences()),
    )["policy.html"]

    assert "invitación a pedir licencia" in html
    assert "Requiere autorización previa y una compensación económica" in html
    assert "train-ai=n, ai-use=n, search=y" in html
    assert "Summary in English" in html
    assert '<meta name="tdm-reservation" content="1">' in html


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda p: p.update({"@type": "Policy"}), "Offer"),
        (lambda p: p.update({"prohibition": []}), "prohibition"),
        (lambda p: p.update({"permission": []}), "permission"),
        (lambda p: p["permission"][0].update({"action": "use"}), "tdm:mine"),
        (lambda p: p["permission"][0].update({"duty": [{"action": "attribute"}]}), "deber"),
        (lambda p: p["assigner"].update({"foo": "x"}), "vCard"),
        (lambda p: p.update({"@context": ["http://www.w3.org/ns/odrl.jsonld"]}), "@context"),
    ],
)
def test_validator_catches_profile_violations(mutate, fragment):
    policy = _jsonld()
    mutate(policy)
    assert any(fragment in e for e in validate_policy_jsonld(policy))


def test_write_policy_artifacts_creates_files(tmp_path: Path):
    output_dir = tmp_path / "policy_out"

    paths = write_policy_artifacts(output_dir, _publisher(), PolicyOptions())

    assert set(paths) == {"policy.jsonld", "policy.html", "tdmrep.json"}
    for path in paths.values():
        assert path.exists()
        assert path.parent == output_dir
