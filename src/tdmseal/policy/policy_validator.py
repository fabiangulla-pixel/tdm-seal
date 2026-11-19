"""Validación de los datos del Policy Builder y de la política ODRL resultante."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from tdmseal.models import PublisherInfo
from tdmseal.policy.odrl import ODRL_CONTEXT, PURPOSES, TDMREP_PROFILE

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VCARD_KEYS = {
    "uid",
    "vcard:fn",
    "vcard:nickname",
    "vcard:hasEmail",
    "vcard:hasAddress",
    "vcard:hasTelephone",
    "vcard:hasURL",
}
_DUTIES = {"obtainConsent", "compensate"}


def validate_publisher_for_policy(publisher: PublisherInfo) -> None:
    """Lanza ValueError si faltan datos imprescindibles para generar la política."""
    if not publisher.name:
        raise ValueError("Falta el nombre de la editorial.")
    if not publisher.website:
        raise ValueError("Falta el sitio web de la editorial (se usa para derivar el dominio).")
    if not publisher.rights_email:
        raise ValueError("Falta el correo de derechos.")
    if not _EMAIL_RE.match(publisher.rights_email):
        raise ValueError(f"Correo de derechos inválido: {publisher.rights_email!r}")


def _is_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_policy_jsonld(policy: object) -> list[str]:
    """Comprueba una política contra el perfil ODRL de TDMRep (sec. 7). Devuelve errores."""
    if not isinstance(policy, dict):
        return ["la política debe ser un objeto JSON"]
    errors: list[str] = []
    if policy.get("@context") != ODRL_CONTEXT:
        errors.append(f"@context debe ser exactamente {ODRL_CONTEXT}")
    if not _is_url(policy.get("uid")):
        errors.append("uid debe ser la URL (URI) de la política")
    if policy.get("@type") != "Offer":
        errors.append('@type debe ser "Offer"')
    if policy.get("profile") != TDMREP_PROFILE:
        errors.append(f"profile debe ser {TDMREP_PROFILE}")
    for forbidden in ("obligation", "prohibition"):
        if forbidden in policy:
            errors.append(f"el perfil TDMRep desaconseja '{forbidden}'")

    assigner = policy.get("assigner")
    if not isinstance(assigner, dict) or not assigner.get("vcard:fn"):
        errors.append("assigner debe existir e incluir vcard:fn (nombre del titular)")
    else:
        unknown = set(assigner) - _VCARD_KEYS
        if unknown:
            errors.append(f"assigner con propiedades no vCard: {sorted(unknown)}")
        email = assigner.get("vcard:hasEmail")
        if email is not None and not str(email).startswith("mailto:"):
            errors.append("vcard:hasEmail debe ser un URI mailto:")

    permissions = policy.get("permission")
    if not isinstance(permissions, list) or not permissions:
        errors.append(
            "permission debe ser un arreglo con al menos un permiso: una política que no "
            "ofrece ningún uso no sirve como oferta (en ese caso no publique tdm-policy)"
        )
        return errors
    for i, perm in enumerate(permissions, start=1):
        if not isinstance(perm, dict) or perm.get("action") != "tdm:mine":
            errors.append(f"permiso {i}: la acción debe ser tdm:mine")
            continue
        for duty in perm.get("duty", []):
            if not isinstance(duty, dict) or duty.get("action") not in _DUTIES:
                errors.append(f"permiso {i}: deber no definido por TDMRep: {duty!r}")
        for constraint in perm.get("constraint", []):
            ok = (
                isinstance(constraint, dict)
                and constraint.get("leftOperand") == "purpose"
                and constraint.get("operator") == "eq"
                and constraint.get("rightOperand") in PURPOSES.values()
            )
            if not ok:
                errors.append(f"permiso {i}: restricción no definida por TDMRep: {constraint!r}")
    return errors
