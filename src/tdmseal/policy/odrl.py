"""Política TDM machine-readable en JSON-LD/ODRL y señal `tdmrep.json` (secciones 23 y 26)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tdmseal.models import PublisherInfo
    from tdmseal.policy.builder import PolicyOptions


def build_policy_jsonld(publisher: PublisherInfo, domain: str, options: PolicyOptions) -> dict:
    duties: list[dict] = []
    if options.require_consent:
        duties.append({"action": "obtainConsent"})
    if options.require_compensation:
        duties.append({"action": "compensate"})

    return {
        "@context": [
            "http://www.w3.org/ns/odrl.jsonld",
            "http://www.w3.org/ns/tdmrep.jsonld",
        ],
        "uid": f"https://{domain}/tdm/policies/{options.policy_id}",
        "@type": "Offer",
        "profile": "http://www.w3.org/ns/tdmrep",
        "assigner": {
            "uid": f"https://{domain}",
            "vcard:fn": publisher.name,
            "vcard:hasEmail": f"mailto:{publisher.rights_email}",
        },
        "permission": [{"action": "tdm:mine", "duty": duties}],
    }


def build_tdmrep_json(reservation: int, policy_url: str | None, location: str = "/") -> list[dict]:
    entry: dict = {"location": location, "tdm-reservation": reservation}
    if policy_url:
        entry["tdm-policy"] = policy_url
    return [entry]
