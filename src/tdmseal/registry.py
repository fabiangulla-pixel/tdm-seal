"""Registro público de declaraciones TDM, alojado por la propia editorial.

Equivale a un registro centralizado de declaraciones (una ficha pública por
obra, legible por personas y por máquinas, con prueba de fecha), pero como un
sitio estático que la editorial publica donde quiera (su dominio, GitHub
Pages…), sin intermediarios ni cuotas. Se genera desde el manifiesto:

    registro/
      index.html              listado con buscador y verificador de archivos
      registro.json           todas las declaraciones, legibles por máquina
      obra/<id>.html          ficha de cada obra con JSON-LD schema.org
      obra/<id>.json          la declaración de esa obra
      prueba/manifiesto.json  (+ .tsr y .tsr.json si se selló con RFC 3161)

Las señales del sitio (/.well-known/tdmrep.json, cabeceras) las genera
`tdmseal site`, porque van en la raíz del dominio.

El verificador del índice calcula la huella SHA-256 de un archivo **en el
navegador** (Web Crypto): el archivo no se sube a ninguna parte.
No se publica nada: se generan archivos.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path

from tdmseal import __version__
from tdmseal.notice import (
    NOTICE_EN,
    NOTICE_ES,
    NOTICE_MACHINE_EN,
    NOTICE_MACHINE_ES,
    NOTICE_TITLE_EN,
    NOTICE_TITLE_ES,
)
from tdmseal.site import _validate_base_url

# Tipos de declaración (equivalentes a los niveles habituales de los registros TDM).
DECLARATION_LABELS = {
    "autoriza": ("Minería autorizada", "Text and data mining permitted"),
    "reserva": ("Todos los derechos reservados para TDM", "All TDM rights reserved"),
    "licencia": (
        "Reservado; licencia disponible",
        "Reserved; licence available",
    ),
}
LEGAL_BASIS = [
    "Directiva (UE) 2019/790, art. 4.3 (reserva expresa de la excepción de minería "
    "de textos y datos)",
    "Reglamento (UE) 2024/1689 de IA, art. 53.1.c (los proveedores de modelos de uso "
    "general deben respetar esa reserva)",
    "Decisión Andina 351 de 1993 y la legislación nacional aplicable (derecho exclusivo "
    "de reproducción)",
]
PERMITTED_ES = (
    "{editorial} autoriza la minería de textos y datos sobre esta obra. Consulte las "
    "condiciones en la política enlazada, si la hay."
)
PERMITTED_EN = (
    "{editorial} permits text and data mining of this work. See the linked policy for "
    "conditions, if any."
)


@dataclass
class RegistryResult:
    out_dir: Path
    works: int
    skipped: int
    timestamped: bool


def declaration_kind(reservation: int | None, policy_url: str | None) -> str | None:
    if reservation is None:
        return None
    if reservation == 0:
        return "autoriza"
    return "licencia" if policy_url else "reserva"


def work_id(row: dict) -> str:
    if row.get("isbn"):
        return str(row["isbn"])
    if row.get("sha256"):
        return str(row["sha256"])[:16]
    return re.sub(r"[^A-Za-z0-9]+", "-", str(row.get("archivo", "obra"))).strip("-")[:40]


def _publisher_name(publisher: dict | None) -> str:
    return (publisher or {}).get("name") or "La editorial"


def _contact(publisher: dict | None) -> str:
    p = publisher or {}
    return p.get("rights_email") or p.get("website") or "la editorial"


def _declaration_texts(kind: str, publisher: dict | None, policy: str | None) -> dict:
    values = {"editorial": _publisher_name(publisher), "contacto": _contact(publisher)}
    if kind == "autoriza":
        es, en = PERMITTED_ES.format(**values), PERMITTED_EN.format(**values)
    else:
        es = f"{NOTICE_ES.format(**values)} {NOTICE_MACHINE_ES}"
        en = f"{NOTICE_EN.format(**values)} {NOTICE_MACHINE_EN}"
    # La política va aparte (tdm_policy / usageInfo), con su propio enlace.
    return {"es": es, "en": en}


def declaration_record(row: dict, publisher: dict | None, proof: dict | None) -> dict | None:
    """Declaración de una obra (lo que va en obra/<id>.json y en registro.json)."""
    kind = declaration_kind(row.get("tdm_reserva"), row.get("tdm_politica"))
    if kind is None:
        return None
    label_es, label_en = DECLARATION_LABELS[kind]
    identifiers = {
        k: row.get(src)
        for k, src in (
            ("isbn", "isbn"),
            ("iscc", "iscc"),
            ("iscc_texto", "iscc_texto"),
            ("iscc_datos", "iscc_datos"),
            ("iscc_instancia", "iscc_instancia"),
            ("sha256", "sha256"),
        )
        if row.get(src)
    }
    return {
        "id": work_id(row),
        "titulo": row.get("titulo") or row.get("archivo"),
        "formato": row.get("formato"),
        "archivo": row.get("archivo"),
        "identificadores": identifiers,
        "declaracion": {
            "tipo": kind,
            "etiqueta": {"es": label_es, "en": label_en},
            "tdm_reservation": row.get("tdm_reserva"),
            "tdm_policy": row.get("tdm_politica"),
            "aipref": row.get("aipref"),
            "texto": _declaration_texts(kind, publisher, row.get("tdm_politica")),
            "base_juridica": LEGAL_BASIS if kind != "autoriza" else [],
            "fecha_declarada_utc": row.get("fecha_utc"),
        },
        "titular": publisher,
        "prueba_de_fecha": proof,
    }


def _json_ld(record: dict, base_url: str | None) -> dict:
    ids = record["identificadores"]
    decl = record["declaracion"]
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": record["titulo"],
        "identifier": [
            {"@type": "PropertyValue", "propertyID": k.upper(), "value": v} for k, v in ids.items()
        ],
        "copyrightNotice": decl["texto"]["es"],
        "conditionsOfAccess": decl["etiqueta"]["en"],
    }
    if ids.get("isbn"):
        data["isbn"] = ids["isbn"]
    if decl.get("tdm_policy"):
        data["usageInfo"] = decl["tdm_policy"]
    if record.get("titular") and record["titular"].get("name"):
        data["copyrightHolder"] = {"@type": "Organization", "name": record["titular"]["name"]}
        if record["titular"].get("website"):
            data["copyrightHolder"]["url"] = record["titular"]["website"]
    if base_url:
        data["@id"] = f"{base_url}obra/{record['id']}.html"
        data["url"] = data["@id"]
    return data


_CSS = """
:root { --fg:#1d2327; --muted:#5f6b73; --line:#d9dee2; --bg:#fbfbfa; --card:#fff;
        --ok:#1e7e34; --okbg:#eef7f0; --warn:#9a6700; --accent:#204f7a; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e6e8ea; --muted:#9aa5ad; --line:#38424a; --bg:#15191c; --card:#1d2327;
          --ok:#6fcf86; --okbg:#18281d; --warn:#e0b44c; --accent:#8ab8e6; } }
* { box-sizing: border-box; }
body { font-family: Georgia, "Times New Roman", serif; background: var(--bg); color: var(--fg);
       max-width: 860px; margin: 0 auto; padding: 2rem 1rem 4rem; line-height: 1.6; }
h1 { font-size: 1.6rem; margin-bottom: .2rem; } h2 { font-size: 1.15rem; margin-top: 2rem; }
.sub { color: var(--muted); margin-top: 0; }
a { color: var(--accent); }
code, .mono { font-family: Consolas, "Courier New", monospace; font-size: .88em;
              word-break: break-all; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
        padding: 1rem 1.2rem; margin: 1rem 0; }
.badge { display: inline-block; border-radius: 999px; padding: .1rem .7rem; font-size: .85rem;
         background: var(--okbg); color: var(--ok); border: 1px solid var(--ok); }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--line);
         vertical-align: top; }
th { font-weight: normal; color: var(--muted); width: 32%; }
input[type=search] { width: 100%; padding: .6rem .8rem; font-size: 1rem; border-radius: 6px;
        border: 1px solid var(--line); background: var(--card); color: var(--fg); }
.drop { border: 2px dashed var(--line); border-radius: 8px; padding: 1.2rem; text-align: center;
        color: var(--muted); cursor: pointer; }
.drop.over { border-color: var(--accent); }
#resultado { margin-top: .8rem; }
footer { margin-top: 3rem; font-size: .85rem; color: var(--muted); }
@media (max-width: 600px) { th { width: auto; display: block; border: 0; padding-bottom: 0; }
  td { display: block; } }
"""


def _page(title: str, head_extra: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{head_extra}<style>{_CSS}</style>
</head>
<body>
{body}
<footer>Registro generado con TDM Seal {__version__} (software libre, MIT).
Las declaraciones no bloquean el acceso: expresan la reserva de derechos y la forma de
pedir licencia.</footer>
</body>
</html>
"""


def _proof_html(proof: dict | None, prefix: str) -> str:
    if not proof:
        return (
            "<p>Fecha declarada por la editorial. Sin sello de tiempo de terceros "
            "(<code>tdmseal timestamp create</code>).</p>"
        )
    return (
        f"<p><span class='badge'>Sello de tiempo RFC 3161</span> "
        f"{escape(proof['fecha_sellada_utc'])} (UTC), emitido por "
        f"<code>{escape(proof['tsa'])}</code> sobre el manifiesto del catálogo, que incluye "
        f"la huella de esta obra.</p><p>Pruebas: <a href='{prefix}prueba/manifiesto.json'>"
        f"manifiesto</a> · <a href='{prefix}prueba/manifiesto.json.tsr'>respuesta de la TSA "
        f"(.tsr)</a> · <a href='{prefix}prueba/manifiesto.json.tsr.json'>recibo</a>. "
        "Verificación: <code>openssl ts -verify -data manifiesto.json -in "
        "manifiesto.json.tsr -CAfile ca-de-la-tsa.pem</code></p>"
    )


def _work_page(record: dict, base_url: str | None) -> str:
    decl = record["declaracion"]
    ids = record["identificadores"]
    rows = "".join(
        f"<tr><th>{escape(k.upper().replace('_', ' '))}</th><td class='mono'>{escape(str(v))}"
        "</td></tr>"
        for k, v in ids.items()
    )
    reservation = decl["tdm_reservation"]
    meta = f'<meta name="tdm-reservation" content="{reservation}">\n'
    if decl.get("tdm_policy"):
        meta += f'<meta name="tdm-policy" content="{escape(decl["tdm_policy"])}">\n'
    ld = json.dumps(_json_ld(record, base_url), ensure_ascii=False, indent=1)
    ld = ld.replace("</", "<\\/")
    head = meta + f'<script type="application/ld+json">\n{ld}\n</script>\n'
    basis = "".join(f"<li>{escape(b)}</li>" for b in decl["base_juridica"])
    policy = (
        f"<p>Política de licencia: <a href='{escape(decl['tdm_policy'])}'>"
        f"{escape(decl['tdm_policy'])}</a></p>"
        if decl.get("tdm_policy")
        else ""
    )
    rid = escape(record["id"])
    body = f"""<p><a href="../index.html">← Registro</a></p>
<h1>{escape(str(record["titulo"]))}</h1>
<p class="sub"><span class="badge">{escape(decl["etiqueta"]["es"])}</span>
 · {escape(decl["etiqueta"]["en"])}</p>
<div class="card">
<h2>{escape(NOTICE_TITLE_ES)}</h2>
<p>{escape(decl["texto"]["es"])}</p>
{policy}
<h2 lang="en">{escape(NOTICE_TITLE_EN)}</h2>
<p lang="en">{escape(decl["texto"]["en"])}</p>
</div>
<h2>Identificación de la obra</h2>
<p>El ISCC (ISO 24138) se calcula a partir del contenido: una copia renombrada o sin
metadatos conserva el mismo código de texto. La huella SHA-256 identifica el archivo
exacto.</p>
<table>{rows}</table>
<h2>Fecha y prueba</h2>
<p>Declarada el {escape(str(decl["fecha_declarada_utc"] or "—"))} (UTC).</p>
{_proof_html(record.get("prueba_de_fecha"), "../")}
{"<h2>Base jurídica invocada</h2><ul>" + basis + "</ul>" if basis else ""}
<p>Versión legible por máquina: <a href="{rid}.json">{rid}.json</a></p>
"""
    return _page(f"{record['titulo']} — reserva TDM", head, body)


def _index_page(records: list[dict], publisher: dict | None, proof: dict | None) -> str:
    name = escape(_publisher_name(publisher))
    items = []
    for r in records:
        hay = " ".join(
            [str(r["titulo"] or ""), *[str(v) for v in r["identificadores"].values()]]
        ).lower()
        items.append(
            f"<tr data-buscar='{escape(hay)}' "
            f"data-sha='{escape(r['identificadores'].get('sha256', ''))}'>"
            f"<td><a href='obra/{escape(r['id'])}.html'>{escape(str(r['titulo']))}</a></td>"
            f"<td>{escape(r['declaracion']['etiqueta']['es'])}</td>"
            f"<td class='mono'>{escape(r['identificadores'].get('isbn', '—'))}</td></tr>"
        )
    body = f"""<h1>Registro de reservas TDM</h1>
<p class="sub">{name} · {len(records)} obra(s) declarada(s)</p>
<div class="card">
<p>Este registro declara, obra por obra, si {name} reserva la minería de textos y datos
(incluido el entrenamiento de IA) y cómo pedir licencia. Cada ficha es legible por personas
y por máquinas (<a href="registro.json">registro.json</a>, JSON-LD schema.org y TDMRep).</p>
{_proof_html(proof, "")}
</div>
<h2>¿Este archivo está en el registro?</h2>
<div class="drop" id="drop" tabindex="0">Arrastre aquí un PDF o EPUB, o haga clic para elegirlo.
<br><small>La huella se calcula en su navegador: el archivo no se sube a ninguna parte.</small>
<input type="file" id="archivo" hidden></div>
<div id="resultado" aria-live="polite"></div>
<h2>Obras</h2>
<input type="search" id="buscar" placeholder="Buscar por título, ISBN o ISCC" aria-label="Buscar">
<table id="obras"><thead><tr><th>Obra</th><th>Declaración</th><th>ISBN</th></tr></thead>
<tbody>{"".join(items)}</tbody></table>
<script>
const filas = [...document.querySelectorAll('#obras tbody tr')];
document.getElementById('buscar').addEventListener('input', e => {{
  const q = e.target.value.trim().toLowerCase();
  filas.forEach(f => f.hidden = q && !f.dataset.buscar.includes(q));
}});
const drop = document.getElementById('drop'), input = document.getElementById('archivo');
const out = document.getElementById('resultado');
async function revisar(file) {{
  out.textContent = 'Calculando la huella…';
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', buf);
  const hex = [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
  const fila = filas.find(f => f.dataset.sha === hex);
  out.innerHTML = '';
  const p = document.createElement('p');
  if (fila) {{
    p.innerHTML = '<span class="badge">En el registro</span> ';
    p.append(fila.querySelector('a').cloneNode(true));
  }} else {{
    p.textContent = 'Este archivo exacto no está en el registro. Una copia modificada '
      + 'puede seguir siendo la misma obra: compruébelo con «tdmseal match».';
  }}
  const h = document.createElement('p'); h.className = 'mono'; h.textContent = 'SHA-256: ' + hex;
  out.append(p, h);
}}
drop.addEventListener('click', () => input.click());
drop.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === ' ') input.click(); }});
input.addEventListener('change', () => input.files[0] && revisar(input.files[0]));
drop.addEventListener('dragover', e => {{ e.preventDefault(); drop.classList.add('over'); }});
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', e => {{
  e.preventDefault(); drop.classList.remove('over');
  if (e.dataTransfer.files[0]) revisar(e.dataTransfer.files[0]);
}});
</script>
"""
    return _page("Registro de reservas TDM", "", body)


def build_registry(
    manifest_path: Path, out_dir: Path, base_url: str | None = None
) -> RegistryResult:
    """Genera el sitio del registro a partir de un manifiesto .json de `tdmseal manifest`."""
    manifest_path = Path(manifest_path)
    if manifest_path.suffix.lower() != ".json":
        raise ValueError(
            "el registro necesita el manifiesto en .json (tdmseal manifest --out X.json)"
        )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "works" not in data:
        raise ValueError("no es un manifiesto de TDM Seal (falta 'works')")
    base_url = _validate_base_url(base_url) if base_url else None
    publisher = data.get("publisher")
    out_dir = Path(out_dir)
    (out_dir / "obra").mkdir(parents=True, exist_ok=True)
    (out_dir / "prueba").mkdir(exist_ok=True)

    proof = None
    shutil.copyfile(manifest_path, out_dir / "prueba" / "manifiesto.json")
    tsr = Path(str(manifest_path) + ".tsr")
    receipt = Path(str(tsr) + ".json")
    if tsr.exists() and receipt.exists():
        from tdmseal.timestamp import verify_timestamp

        check = verify_timestamp(manifest_path, tsr)
        if not check.hash_matches:
            raise ValueError(f"el sello de tiempo no corresponde al manifiesto: {check.message}")
        shutil.copyfile(tsr, out_dir / "prueba" / "manifiesto.json.tsr")
        shutil.copyfile(receipt, out_dir / "prueba" / "manifiesto.json.tsr.json")
        proof = json.loads(receipt.read_text(encoding="utf-8"))

    records, skipped, seen = [], 0, set()
    for row in data["works"]:
        if str(row.get("estado", "")).startswith("error"):
            skipped += 1
            continue
        record = declaration_record(row, publisher, proof)
        if record is None:
            skipped += 1
            continue
        while record["id"] in seen:
            record["id"] += "-b"
        seen.add(record["id"])
        records.append(record)
        (out_dir / "obra" / f"{record['id']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "obra" / f"{record['id']}.html").write_text(
            _work_page(record, base_url), encoding="utf-8"
        )

    registry = {
        "tool": "TDM Seal",
        "tool_version": __version__,
        "generated_at_utc": data.get("generated_at_utc"),
        "publisher": publisher,
        "proof": proof,
        "declarations": records,
    }
    (out_dir / "registro.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "index.html").write_text(_index_page(records, publisher, proof), encoding="utf-8")
    return RegistryResult(out_dir, len(records), skipped, proof is not None)
