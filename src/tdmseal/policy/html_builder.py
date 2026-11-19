"""Versión HTML humana de la política TDM (sección 22 de la especificación).

La página deja claro que la reserva **no es un «no» cerrado sino una
invitación a licenciar**: explica qué se reserva, cómo pedir licencia y en
qué condiciones según la finalidad, y enlaza la versión legible por máquinas.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tdmseal.models import PublisherInfo
    from tdmseal.policy.builder import PolicyOptions

_TDMREP_SPEC_URL = "https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/"

TERMS_ES = {
    "free": "Permitida sin solicitud previa.",
    "consent": "Requiere autorización previa: escríbanos y le responderemos.",
    "compensate": (
        "Requiere autorización previa y una compensación económica, que se acuerda en la licencia."
    ),
    "none": "Por ahora no ofrecemos licencias para esta finalidad.",
}
TERMS_EN = {
    "free": "allowed without prior request",
    "consent": "requires prior permission",
    "compensate": "requires prior permission and payment",
    "none": "not currently licensed",
}
AIPREF_LABELS = {
    "train-ai": "Entrenamiento de modelos de IA generativa",
    "ai-use": "Uso como entrada de sistemas de IA generativa (p. ej., respuestas con búsqueda)",
    "search": "Búsqueda e indexación que enlaza al contenido",
}


def _contact(publisher: PublisherInfo, contact_url: str | None) -> str:
    email = escape(publisher.rights_email or "")
    line = f'<a href="mailto:{email}">{email}</a>'
    url = contact_url or publisher.website
    if url:
        safe = escape(url)
        line += f' o en <a href="{safe}">{safe}</a>'
    return line


def _aipref_section(aipref) -> str:
    if aipref is None:
        return ""
    rows = []
    for category, value in aipref.values:
        label = escape(AIPREF_LABELS.get(category, category))
        state = "Permitido" if value == "y" else "Reservado (requiere licencia)"
        rows.append(f"<tr><td>{label}</td><td><code>{category}</code></td><td>{state}</td></tr>")
    return f"""
<h2>4. Preferencias sobre usos de inteligencia artificial</h2>
<p>Además de la reserva general, declaramos estas preferencias con el
vocabulario del IETF (AIPREF, todavía en borrador). Se publican en la
cabecera HTTP <code>Content-Usage</code> y en el archivo robots.txt del sitio:
<code>{escape(aipref.serialize())}</code>.</p>
<table>
<thead><tr><th>Uso</th><th>Categoría</th><th>Estado</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
"""


def build_policy_html(
    publisher: PublisherInfo, options: PolicyOptions, policy_url: str | None = None
) -> str:
    name = escape(publisher.name or "")
    contact = _contact(publisher, options.license_contact_url)
    research, non_research = options.resolved_terms()

    request_fields = [
        "identidad de la persona o entidad solicitante",
        "finalidad del proyecto (investigación u otra)",
        "obras o colección solicitadas",
        "técnicas de procesamiento previstas",
        "volumen de contenido",
        "duración del uso",
    ]
    if "compensate" in (research, non_research):
        request_fields.append("propuesta de compensación económica")
    request_list = "\n".join(f"<li>{item}.</li>" for item in request_fields)

    aipref_html = _aipref_section(options.aipref)
    n = 5 if aipref_html else 4
    machine_link = ""
    if policy_url:
        safe = escape(policy_url)
        machine_link = (
            "<p>Versión legible por máquinas (ODRL, perfil TDMRep): "
            f'<a href="{safe}">{safe}</a></p>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="tdm-reservation" content="1">
{f'<meta name="tdm-policy" content="{escape(policy_url)}">' if policy_url else ""}
<title>Política de minería de textos y datos — {name}</title>
<style>
  body {{ font-family: Georgia, "Times New Roman", serif; max-width: 760px;
          margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  code {{ background: #f2f2f2; padding: 0.1rem 0.3rem; }}
  .resumen {{ border-left: 4px solid #1e7e34; background: #f4faf5; padding: 0.8rem 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left;
            vertical-align: top; }}
  footer {{ margin-top: 3rem; font-size: 0.85rem; color: #666; }}
</style>
</head>
<body>
<h1>Política sobre minería de textos y datos y uso para inteligencia artificial</h1>
<p><strong>{name}</strong></p>

<div class="resumen">
<p><strong>En resumen:</strong> {name} reserva sus derechos de minería de
textos y datos sobre sus publicaciones. La reserva <strong>no es una negativa
definitiva, sino una invitación a pedir licencia</strong>. Si quiere usar
nuestras obras para minería de textos, construir corpus o entrenar sistemas de
inteligencia artificial, escríbanos a {contact}.</p>
</div>

<h2>1. Qué reservamos</h2>
<p>Salvo que una obra o colección indique lo contrario mediante una licencia
específica, {name} reserva los derechos de minería de textos y datos sobre los
contenidos respecto de los cuales está facultada para hacerlo. La reserva
comprende el uso sistemático o automatizado de los contenidos para minería de
textos y datos, la recolección masiva para construir corpus, el entrenamiento
o ajuste de modelos de inteligencia artificial y la construcción de conjuntos
de datos de entrenamiento, evaluación o validación.</p>

<h2>2. Cómo obtener una licencia</h2>
<table>
<thead><tr><th>Finalidad</th><th>Condiciones</th></tr></thead>
<tbody>
<tr><td>Investigación científica o académica</td><td>{TERMS_ES[research]}</td></tr>
<tr><td>Otros fines, incluidos los comerciales y el entrenamiento de IA</td>
<td>{TERMS_ES[non_research]}</td></tr>
</tbody>
</table>
<p>Para solicitar una licencia, escríbanos a {contact}.</p>

<h2>3. Qué debe incluir la solicitud</h2>
<ul>
{request_list}
</ul>
{aipref_html}
<h2>{n}. Señales legibles por máquinas</h2>
<p>La reserva se expresa también con el protocolo
<a href="{_TDMREP_SPEC_URL}">TDMRep</a> del W3C: dentro de cada archivo
(metadatos XMP en PDF, paquete OPF en EPUB), en
<code>/.well-known/tdmrep.json</code> y en las cabeceras HTTP del sitio. Un
valor <code>tdm-reservation = 1</code> significa que los derechos están
reservados conforme a esta política.</p>
{machine_link}

<h2>{n + 1}. Ausencia de autorización implícita</h2>
<p>Que un contenido sea público, esté indexado por buscadores o pueda
descargarse no constituye por sí mismo una autorización para usarlo en
minería de textos y datos o en el entrenamiento de sistemas de inteligencia
artificial.</p>

<h2>{n + 2}. Excepciones legales</h2>
<p>Nada en esta política pretende excluir los usos que una norma imperativa
permita sin autorización del titular.</p>

<h2 lang="en">Summary in English</h2>
<p lang="en">{name} reserves its text and data mining rights. This is an
invitation to license, not a final refusal. Research use:
{TERMS_EN[research]}. Other uses, including commercial use and AI training:
{TERMS_EN[non_research]}. Contact: {contact}.</p>

<footer>Generado con TDM Seal. Esta página declara una reserva de derechos;
no es un bloqueo técnico.</footer>
</body>
</html>
"""
