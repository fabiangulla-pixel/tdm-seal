"""Política TDM legible por máquinas: ODRL 2.2 en JSON-LD con el perfil TDMRep.

Fuente: TDMRep, Final CG Report 10-may-2024, sección 7 (consultada el
19-nov-2026). Requisitos del perfil:

- `@context` = exactamente [odrl.jsonld, tdmrep.jsonld];
- `uid` = URI de la política; `@type` = "Offer";
- `profile` = "http://www.w3.org/ns/tdmrep";
- `assigner` con propiedades vCard (fn, nickname, hasEmail, hasAddress,
  hasTelephone, hasURL);
- `permission` (arreglo) con acción `tdm:mine`; deberes `obtainConsent`
  y `compensate`; restricción opcional (experimental) de `purpose` igual a
  `tdm:research` o `tdm:non-research`;
- `obligation` y `prohibition` NO deberían aparecer.

Por eso un uso que la editorial no quiere ofrecer simplemente no aparece
como permiso: la reserva se mantiene y la política solo describe lo que sí
se puede licenciar. Es una oferta, no una prohibición.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tdmseal.models import PublisherInfo
    from tdmseal.policy.builder import PolicyOptions

ODRL_CONTEXT = ["http://www.w3.org/ns/odrl.jsonld", "http://www.w3.org/ns/tdmrep.jsonld"]
TDMREP_PROFILE = "http://www.w3.org/ns/tdmrep"
PURPOSES = {"research": "tdm:research", "non-research": "tdm:non-research"}

# Condiciones por finalidad → deberes ODRL. "none" = no se ofrece.
TERMS = {
    "free": [],
    "consent": ["obtainConsent"],
    "compensate": ["obtainConsent", "compensate"],
    "none": None,
}


def _permission(duties: list[str], purpose: str | None) -> dict:
    perm: dict = {"action": "tdm:mine"}
    if purpose is not None:
        perm["constraint"] = [{"leftOperand": "purpose", "operator": "eq", "rightOperand": purpose}]
    if duties:
        perm["duty"] = [{"action": d} for d in duties]
    return perm


def build_permissions(research: str, non_research: str) -> list[dict]:
    """Permisos según las condiciones para investigación y para otros fines."""
    for term in (research, non_research):
        if term not in TERMS:
            raise ValueError(f"condición desconocida: {term!r} (use {', '.join(TERMS)})")
    if research == non_research:
        duties = TERMS[research]
        return [] if duties is None else [_permission(duties, None)]
    permissions = []
    for term, purpose in (
        (research, PURPOSES["research"]),
        (non_research, PURPOSES["non-research"]),
    ):
        if TERMS[term] is not None:
            permissions.append(_permission(TERMS[term], purpose))
    return permissions


def build_assigner(publisher: PublisherInfo, contact_url: str | None, domain: str) -> dict:
    assigner: dict = {"uid": f"https://{domain}", "vcard:fn": publisher.name}
    if publisher.acronym:
        assigner["vcard:nickname"] = publisher.acronym
    assigner["vcard:hasEmail"] = f"mailto:{publisher.rights_email}"
    url = contact_url or publisher.website
    if url:
        assigner["vcard:hasURL"] = url
    return assigner


def build_policy_jsonld(
    publisher: PublisherInfo, domain: str, options: PolicyOptions, policy_url: str
) -> dict:
    research, non_research = options.resolved_terms()
    return {
        "@context": list(ODRL_CONTEXT),
        "uid": policy_url,
        "@type": "Offer",
        "profile": TDMREP_PROFILE,
        "assigner": build_assigner(publisher, options.license_contact_url, domain),
        "permission": build_permissions(research, non_research),
    }


def build_tdmrep_json(reservation: int, policy_url: str | None, location: str = "/") -> list[dict]:
    entry: dict = {"location": location, "tdm-reservation": reservation}
    if policy_url:
        entry["tdm-policy"] = policy_url
    return [entry]
