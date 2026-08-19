from __future__ import annotations

import pytest

from tdmseal.errors import TDMSealError
from tdmseal.models import TDMPolicy
from tdmseal.xmp.parser import find_rdf_root, parse_xmp
from tdmseal.xmp.serializer import serialize_xmp
from tdmseal.xmp.tdmrep import read_tdmrep, validate_policy_url, write_tdmrep


def test_write_tdmrep_on_empty_xmp_creates_declaration():
    root = find_rdf_root(parse_xmp(None))

    operation = write_tdmrep(root, TDMPolicy(reservation=1))

    assert operation == "create"
    declaration = read_tdmrep(root)
    assert declaration.reservation == 1
    assert declaration.policy_url is None
    assert declaration.present


def test_write_tdmrep_with_policy_url():
    root = find_rdf_root(parse_xmp(None))

    write_tdmrep(root, TDMPolicy(reservation=1, policy_url="https://example.org/tdm/policy.jsonld"))

    declaration = read_tdmrep(root)
    assert declaration.policy_url == "https://example.org/tdm/policy.jsonld"


def test_write_tdmrep_is_idempotent_does_not_duplicate():
    root = find_rdf_root(parse_xmp(None))
    write_tdmrep(root, TDMPolicy(reservation=1))
    write_tdmrep(root, TDMPolicy(reservation=1))

    descriptions = root.findall("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description")
    assert len(descriptions) == 1
    declaration = read_tdmrep(root)
    assert declaration.reservation == 1


def test_write_tdmrep_updates_value_from_1_to_0():
    root = find_rdf_root(parse_xmp(None))
    write_tdmrep(root, TDMPolicy(reservation=1))

    operation = write_tdmrep(root, TDMPolicy(reservation=0))

    assert operation == "update"
    assert read_tdmrep(root).reservation == 0


def test_write_tdmrep_updates_policy_url():
    root = find_rdf_root(parse_xmp(None))
    write_tdmrep(root, TDMPolicy(reservation=1, policy_url="https://old.example/policy.json"))

    write_tdmrep(root, TDMPolicy(reservation=1, policy_url="https://new.example/policy.jsonld"))

    assert read_tdmrep(root).policy_url == "https://new.example/policy.jsonld"


def test_write_tdmrep_removes_policy_when_none_given():
    root = find_rdf_root(parse_xmp(None))
    write_tdmrep(root, TDMPolicy(reservation=1, policy_url="https://old.example/policy.json"))

    write_tdmrep(root, TDMPolicy(reservation=1, policy_url=None))

    assert read_tdmrep(root).policy_url is None


def test_write_tdmrep_preserves_foreign_metadata():
    foreign_xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b"<dc:title>Un libro editorial</dc:title>"
        b"</rdf:Description>"
        b"</rdf:RDF>"
        b"</x:xmpmeta>"
    )
    root = find_rdf_root(parse_xmp(foreign_xmp))

    write_tdmrep(root, TDMPolicy(reservation=1))

    serialized = serialize_xmp(root)
    assert b"Un libro editorial" in serialized
    assert read_tdmrep(root).reservation == 1


@pytest.mark.parametrize("value", [0, 1])
def test_tdm_policy_accepts_valid_reservation(value):
    TDMPolicy(reservation=value)


def test_tdm_policy_rejects_invalid_reservation():
    with pytest.raises(ValueError):
        TDMPolicy(reservation=2)


def test_validate_policy_url_accepts_https():
    validate_policy_url("https://editorial.example.edu/tdm/policy.jsonld")


@pytest.mark.parametrize("bad_url", ["not-a-url", "ftp://example.org/x", ""])
def test_validate_policy_url_rejects_invalid(bad_url):
    with pytest.raises(TDMSealError):
        validate_policy_url(bad_url)
