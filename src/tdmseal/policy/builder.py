"""Policy Builder: genera policy.jsonld, policy.html y tdmrep.json (sección 27)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from tdmseal.models import PublisherInfo
from tdmseal.policy.html_builder import build_policy_html
from tdmseal.policy.odrl import TERMS, build_policy_jsonld, build_tdmrep_json
from tdmseal.policy.policy_validator import validate_policy_jsonld, validate_publisher_for_policy


@dataclass
class PolicyOptions:
    """Opciones de la política.

    `research` y `non_research` fijan las condiciones por finalidad: "free"
    (sin condiciones), "consent" (pedir autorización), "compensate"
    (autorización y pago) o "none" (no se ofrece). Si no se indican, se
    derivan de `require_consent` / `require_compensation` (compatibilidad).
    """

    require_consent: bool = True
    require_compensation: bool = False
    policy_id: str = "1"
    tdmrep_location: str = "/"
    policy_url: str | None = None  # URL donde se publicará policy.jsonld
    research: str | None = None
    non_research: str | None = None
    license_contact_url: str | None = None  # página o formulario de licencias
    aipref: object | None = None  # AiPreferences, solo para la página HTML

    def resolved_terms(self) -> tuple[str, str]:
        default = "consent" if self.require_consent else "free"
        if self.require_compensation:
            default = "compensate"
        research = self.research or default
        non_research = self.non_research or default
        for term in (research, non_research):
            if term not in TERMS:
                raise ValueError(f"condición desconocida: {term!r} (use {', '.join(TERMS)})")
        return research, non_research


def domain_from_website(website: str) -> str:
    """Extrae el dominio (sin esquema) de una URL de sitio web."""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        raise ValueError(f"No se pudo derivar un dominio del sitio web: {website!r}")
    return parsed.netloc


def resolve_policy_url(publisher: PublisherInfo, options: PolicyOptions) -> str:
    if options.policy_url:
        parsed = urlparse(options.policy_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"La URL de la política debe ser http(s): {options.policy_url!r}")
        return options.policy_url
    domain = domain_from_website(publisher.website)
    return f"https://{domain}/tdm/policies/{options.policy_id}"


def build_policy_artifacts(publisher: PublisherInfo, options: PolicyOptions) -> dict[str, str]:
    """Genera el contenido de los tres artefactos, sin escribir nada a disco."""
    validate_publisher_for_policy(publisher)
    domain = domain_from_website(publisher.website)
    policy_url = resolve_policy_url(publisher, options)

    jsonld = build_policy_jsonld(publisher, domain, options, policy_url)
    errors = validate_policy_jsonld(jsonld)
    if errors:
        raise ValueError("La política no cumple el perfil ODRL de TDMRep: " + "; ".join(errors))
    html = build_policy_html(publisher, options, policy_url)
    tdmrep = build_tdmrep_json(
        reservation=1, policy_url=policy_url, location=options.tdmrep_location
    )

    return {
        "policy.jsonld": json.dumps(jsonld, indent=2, ensure_ascii=False),
        "policy.html": html,
        "tdmrep.json": json.dumps(tdmrep, indent=2, ensure_ascii=False),
    }


def write_policy_artifacts(
    output_dir: Path, publisher: PublisherInfo, options: PolicyOptions
) -> dict[str, Path]:
    """Genera y escribe los tres artefactos en `output_dir`. Devuelve sus rutas."""
    artifacts = build_policy_artifacts(publisher, options)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for name, content in artifacts.items():
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
