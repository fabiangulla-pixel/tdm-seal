"""Policy Builder: genera policy.jsonld, policy.html y tdmrep.json (sección 27)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from tdmseal.models import PublisherInfo
from tdmseal.policy.html_builder import build_policy_html
from tdmseal.policy.odrl import build_policy_jsonld, build_tdmrep_json
from tdmseal.policy.policy_validator import validate_publisher_for_policy


@dataclass
class PolicyOptions:
    require_consent: bool = True
    require_compensation: bool = False
    policy_id: str = "1"
    tdmrep_location: str = "/"


def domain_from_website(website: str) -> str:
    """Extrae el dominio (sin esquema) de una URL de sitio web."""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        raise ValueError(f"No se pudo derivar un dominio del sitio web: {website!r}")
    return parsed.netloc


def build_policy_artifacts(publisher: PublisherInfo, options: PolicyOptions) -> dict[str, str]:
    """Genera el contenido de los tres artefactos, sin escribir nada a disco."""
    validate_publisher_for_policy(publisher)
    domain = domain_from_website(publisher.website)
    policy_url = f"https://{domain}/tdm/policies/{options.policy_id}"

    jsonld = build_policy_jsonld(publisher, domain, options)
    html = build_policy_html(publisher, options)
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
