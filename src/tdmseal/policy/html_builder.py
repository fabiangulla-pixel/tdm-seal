"""Versión HTML humana de la política TDM, basada en el borrador de la sección 22."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tdmseal.models import PublisherInfo
    from tdmseal.policy.builder import PolicyOptions

_TDMREP_SPEC_URL = "https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/"


def build_policy_html(publisher: PublisherInfo, options: PolicyOptions) -> str:
    name = escape(publisher.name or "")
    email = escape(publisher.rights_email or "")
    website = escape(publisher.website or "")

    contact_line = f'<a href="mailto:{email}">{email}</a>'
    if website:
        contact_line += f' o visitando <a href="{website}">{website}</a>'

    request_fields = [
        "identidad de la entidad solicitante",
        "finalidad del proyecto",
        "obras o colección solicitadas",
        "técnicas de procesamiento previstas",
        "volumen de contenido",
        "duración del uso",
    ]
    if options.require_compensation:
        request_fields.append("posibilidad de compensación económica")
    request_list = "".join(f"<li>{item}.</li>" for item in request_fields)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Política de minería de textos y datos — {name}</title>
<style>
  body {{ font-family: Georgia, "Times New Roman", serif; max-width: 760px;
          margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  code {{ background: #f2f2f2; padding: 0.1rem 0.3rem; }}
  footer {{ margin-top: 3rem; font-size: 0.85rem; color: #666; }}
</style>
</head>
<body>
<h1>Política sobre minería de textos y datos y uso para sistemas de inteligencia artificial</h1>
<p><strong>{name}</strong></p>

<h2>1. Objeto</h2>
<p>La presente política establece las condiciones aplicables a la minería de
textos y datos, extracción automatizada, indexación para conjuntos de datos y
utilización de contenidos publicados por <strong>{name}</strong> en procesos
de entrenamiento o desarrollo de sistemas de inteligencia artificial y
aprendizaje automático.</p>

<h2>2. Reserva de derechos</h2>
<p>Salvo que una obra o colección indique expresamente lo contrario mediante
una licencia específica, {name} reserva los derechos aplicables a la minería
de textos y datos sobre los contenidos respecto de los cuales se encuentre
facultada para efectuar dicha reserva.</p>
<p>Esta reserva se expresa también, cuando técnicamente resulte posible,
mediante mecanismos legibles por máquinas, incluido
<a href="{_TDMREP_SPEC_URL}">TDMRep</a>.</p>

<h2>3. Usos sujetos a autorización</h2>
<p>Salvo autorización previa o una excepción legal aplicable, la reserva
comprende el uso sistemático o automatizado de los contenidos para minería de
textos y datos, recolección masiva o scraping destinado a construir corpus,
entrenamiento o fine-tuning de modelos de inteligencia artificial, y
construcción de datasets de entrenamiento, evaluación o validación.</p>

<h2>4. Investigación y usos académicos</h2>
<p>La condición académica, científica o sin ánimo de lucro de un proyecto no
implica por sí sola una autorización general. Las personas o instituciones
interesadas en realizar minería de textos y datos con fines de investigación
podrán solicitar autorización escribiendo a {contact_line}.</p>

<h2>5. Solicitudes de licencia</h2>
<p>Las solicitudes deberán indicar al menos:</p>
<ul>
{request_list}
</ul>

<h2>6. Señales legibles por máquinas</h2>
<p>Cuando un archivo contenga <code>tdm:reservation = 1</code>, deberá
interpretarse como una manifestación de reserva de derechos TDM conforme a
esta política.</p>

<h2>7. Ausencia de autorización implícita</h2>
<p>La disponibilidad pública de un contenido, su indexación por buscadores o
la posibilidad técnica de descargarlo no constituyen por sí mismas una
autorización para utilizarlo en minería de textos y datos o entrenamiento de
sistemas de inteligencia artificial.</p>

<h2>8. Excepciones legales</h2>
<p>Nada en esta política pretende excluir usos que una norma imperativa
permita sin autorización del titular.</p>

<footer>Generado con TDM Seal. Contacto: {contact_line}</footer>
</body>
</html>
"""
