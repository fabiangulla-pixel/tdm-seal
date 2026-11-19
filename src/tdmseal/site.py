"""Señales TDM a nivel de sitio web: `/.well-known/tdmrep.json`, cabeceras HTTP,
robots.txt y metaetiquetas HTML.

Fuentes:
- TDMRep, Final CG Report 10-may-2024: sec. 6.1 (`tdmrep.json`), 6.2
  (cabeceras `tdm-reservation` / `tdm-policy`, la técnica preferida; tienen
  prioridad sobre `tdmrep.json`), 6.3 (metaetiquetas HTML).
- draft-ietf-aipref-attach-05: cabecera `Content-Usage` y regla
  `Content-Usage:` en robots.txt (ver tdmseal/aipref.py).

Nada de esto se sube a ningún servidor: se generan archivos para que la
editorial los publique.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from tdmseal.aipref import ATTACH_DRAFT, AiPreferences

_LOCATION_RE = re.compile(r"^[/*][^\s$]*\$?$")


def validate_tdmrep_json(data: object) -> tuple[list[str], list[str]]:
    """Valida un `tdmrep.json` ya parseado. Devuelve (errores, avisos)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, list):
        return ["tdmrep.json debe ser un arreglo JSON (corchetes obligatorios, sec. 6.1)"], []
    if not data:
        errors.append("tdmrep.json no tiene ninguna regla")
    for i, rule in enumerate(data):
        where = f"regla {i + 1}"
        if not isinstance(rule, dict):
            errors.append(f"{where}: debe ser un objeto JSON")
            continue
        location = rule.get("location")
        if not isinstance(location, str) or not location:
            errors.append(f"{where}: falta 'location' (texto obligatorio)")
        elif not _LOCATION_RE.match(location):
            errors.append(
                f"{where}: 'location' inválida {location!r}: debe empezar por '/' o '*', "
                "sin espacios, y '$' solo puede ir al final (sec. 6.1.1)"
            )
        reservation = rule.get("tdm-reservation")
        if isinstance(reservation, bool) or reservation not in (0, 1):
            errors.append(f"{where}: 'tdm-reservation' debe ser 0 o 1 (número)")
        policy = rule.get("tdm-policy")
        if policy is not None:
            parsed = urlparse(policy) if isinstance(policy, str) else None
            if parsed is None or parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(f"{where}: 'tdm-policy' debe ser una URL absoluta http(s)")
            elif reservation == 0:
                warnings.append(
                    f"{where}: hay 'tdm-policy' con reserva 0; los agentes no deberían "
                    "procesarla (sec. 5.2)"
                )
        extra = set(rule) - {"location", "tdm-reservation", "tdm-policy"}
        if extra:
            warnings.append(f"{where}: propiedades no definidas por TDMRep: {sorted(extra)}")
    return errors, warnings


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"--base-url debe ser una URL absoluta http(s): {base_url!r}")
    return base_url if base_url.endswith("/") else base_url + "/"


def build_site_artifacts(
    base_url: str,
    reservation: int,
    policy_url: str | None,
    aipref: AiPreferences | None,
    location: str = "/",
) -> dict[str, str]:
    """Contenido de cada archivo a publicar (ruta relativa → texto). No escribe nada."""
    base_url = _validate_base_url(base_url)
    rule: dict = {"location": location, "tdm-reservation": reservation}
    if policy_url:
        rule["tdm-policy"] = policy_url
    rules = [rule]
    errors, _ = validate_tdmrep_json(rules)
    if errors:
        raise ValueError("; ".join(errors))

    usage = aipref.serialize() if aipref else None
    files: dict[str, str] = {
        ".well-known/tdmrep.json": json.dumps(rules, indent=2, ensure_ascii=False) + "\n"
    }

    apache = [
        "# TDM Seal: cabeceras TDMRep (sec. 6.2) y AIPREF Content-Usage.",
        "# Copie esto en la configuración del sitio o en .htaccess (requiere mod_headers).",
        "<IfModule mod_headers.c>",
        f'  Header always set tdm-reservation "{reservation}"',
    ]
    if policy_url:
        apache.append(f'  Header always set tdm-policy "{policy_url}"')
    if usage:
        apache.append(f'  Header always set Content-Usage "{usage}"')
    apache += [
        "</IfModule>",
        "",
        "# Servir /.well-known/tdmrep.json como JSON:",
        '<Files "tdmrep.json">',
        "  ForceType application/json",
        "</Files>",
        "",
    ]
    files["servidor/apache.conf"] = "\n".join(apache)

    nginx = [
        "# TDM Seal: cabeceras TDMRep (sec. 6.2) y AIPREF Content-Usage.",
        "# Dentro del bloque server { }. Ojo: si un bloque location tiene sus propios",
        "# add_header, Nginx no hereda estos; repítalos allí.",
        f'add_header tdm-reservation "{reservation}" always;',
    ]
    if policy_url:
        nginx.append(f'add_header tdm-policy "{policy_url}" always;')
    if usage:
        nginx.append(f'add_header Content-Usage "{usage}" always;')
    nginx += [
        "",
        "location = /.well-known/tdmrep.json {",
        "    default_type application/json;",
        "}",
        "",
    ]
    files["servidor/nginx.conf"] = "\n".join(nginx)

    if usage:
        files["servidor/robots-content-usage.txt"] = (
            f"# Preferencias de uso para IA ({ATTACH_DRAFT}, sec. 3).\n"
            "# AÑADA estas líneas al final de su robots.txt actual; no lo sustituya.\n"
            "# Los grupos con el mismo User-Agent se combinan (RFC 9309).\n"
            "User-Agent: *\n"
            f"Content-Usage: {usage}\n"
        )

    meta = [
        "<!-- TDM Seal: metaetiquetas TDMRep (sec. 6.3) para el <head> de cada página. -->",
        f'<meta name="tdm-reservation" content="{reservation}">',
    ]
    if policy_url:
        meta.append(f'<meta name="tdm-policy" content="{policy_url}">')
    files["servidor/html-meta.html"] = "\n".join(meta) + "\n"

    files["LEEME.txt"] = _readme(base_url, reservation, policy_url, usage)
    return files


def _readme(base_url: str, reservation: int, policy_url: str | None, usage: str | None) -> str:
    lines = [
        "SEÑALES TDM PARA EL SITIO WEB (generado por TDM Seal)",
        "",
        "Nada de esto se ha publicado: suba usted cada archivo a su servidor.",
        "",
        f"1. .well-known/tdmrep.json  ->  {base_url}.well-known/tdmrep.json",
        "   Declara la reserva TDM para todo el sitio. Debe servirse como JSON.",
        "",
        "2. servidor/apache.conf o servidor/nginx.conf",
        "   Añaden las cabeceras HTTP tdm-reservation"
        + (", tdm-policy" if policy_url else "")
        + (" y Content-Usage" if usage else "")
        + " a todas las respuestas.",
        "   Según TDMRep es la vía preferida y tiene prioridad sobre tdmrep.json.",
        "",
    ]
    if usage:
        lines += [
            "3. servidor/robots-content-usage.txt",
            "   Líneas para AÑADIR a su robots.txt (no lo sustituya).",
            f"   Preferencias de IA: {usage}",
            "   (vocabulario IETF AIPREF; todavía es un borrador, puede cambiar).",
            "",
        ]
    lines += [
        "4. servidor/html-meta.html",
        "   Metaetiquetas para el <head> de las páginas HTML.",
        "",
        f"Reserva TDM: {reservation} ({'reservado' if reservation == 1 else 'no reservado'})",
        f"Política: {policy_url or '(ninguna)'}",
        "",
        "Recuerde: estas señales declaran la reserva de derechos; no bloquean",
        "técnicamente el acceso. Son una invitación a licenciar.",
        "",
    ]
    return "\n".join(lines)


def write_site_artifacts(out_dir: Path, files: dict[str, str]) -> dict[str, Path]:
    out_dir = Path(out_dir)
    paths: dict[str, Path] = {}
    for rel, content in files.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        paths[rel] = path
    return paths
