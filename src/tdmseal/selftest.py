"""Autoprueba de punta a punta: comprueba que esta instalación funciona.

Genera un PDF y un EPUB de ejemplo en una carpeta temporal y recorre todas
las vías: sellado con ISCC, política ODRL, señales del sitio y manifiesto.
Sirve para el `.exe` congelado (`TDM-Seal.exe --autoprueba`), que no tiene
consola, y para `tdmseal selftest`. No toca ningún archivo del usuario ni usa
la red.
"""

from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path

from tdmseal import __version__


def run_selftest(workdir: Path | None = None) -> dict:
    from tdmseal.aipref import default_preferences
    from tdmseal.config import SealConfig
    from tdmseal.documents import seal_document
    from tdmseal.iscc.content import content_extra_available
    from tdmseal.manifest import build_manifest
    from tdmseal.models import PublisherInfo, TDMPolicy
    from tdmseal.policy.builder import PolicyOptions, write_policy_artifacts
    from tdmseal.policy.policy_validator import validate_policy_jsonld
    from tdmseal.samples import SAMPLE_TEXT, build_epub, build_text_pdf
    from tdmseal.site import build_site_artifacts, validate_tdmrep_json, write_site_artifacts
    from tdmseal.tools import tools_status

    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="tdmseal-autoprueba-"))
    work.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    policy = TDMPolicy(1, "https://editorial.ejemplo.org/tdm/policies/1")
    publisher = PublisherInfo(
        name="Editorial de prueba",
        website="https://editorial.ejemplo.org",
        rights_email="derechos@editorial.ejemplo.org",
    )

    def step(name: str, func) -> None:
        try:
            ok, detail = func()
        except Exception:  # noqa: BLE001 — la autoprueba registra cualquier fallo
            ok, detail = False, traceback.format_exc(limit=4)
        steps.append({"paso": name, "ok": bool(ok), "detalle": detail})

    def seal_pdf_step():
        pdf = build_text_pdf(work / "libro.pdf", SAMPLE_TEXT, title="Libro de prueba")
        r = seal_document(pdf, SealConfig(policy=policy, compute_iscc=True))
        text_ok = (not content_extra_available()) or bool(r.iscc_input and r.iscc_input.text_code)
        return r.status == "success" and text_ok, {
            "estado": r.status,
            "validaciones": r.validations,
            "iscc": r.iscc_input.iscc if r.iscc_input else None,
        }

    def seal_epub_step():
        epub = build_epub(work / "libro.epub")
        r = seal_document(epub, SealConfig(policy=policy, compute_iscc=True))
        return r.status == "success", {"estado": r.status, "validaciones": r.validations}

    def pdfa_templates_step():
        # Comprueba que las plantillas del esquema de extensión PDF/A están
        # disponibles (en el .exe van empaquetadas aparte del código).
        import pikepdf

        from tdmseal.pdf.inspector import read_document_xmp_bytes

        xmp = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
            b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            b'<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
            b'pdfaid:part="2" pdfaid:conformance="B"/></rdf:RDF></x:xmpmeta>'
        )
        path = build_text_pdf(work / "pdfa.pdf", SAMPLE_TEXT, xmp_bytes=xmp)
        r = seal_document(path, SealConfig(policy=policy, compute_iscc=True, run_verapdf=False))
        with pikepdf.open(r.output_path) as pdf:
            sealed_xmp = read_document_xmp_bytes(pdf) or b""
        ok = (
            r.status == "success"
            and b"http://www.w3.org/ns/tdmrep/</pdfaSchema:namespaceURI>" in sealed_xmp
            and b"/ns/iscc/1.0/</pdfaSchema:namespaceURI>" in sealed_xmp
        )
        return ok, {"estado": r.status}

    def policy_step():
        paths = write_policy_artifacts(
            work / "politica", publisher, PolicyOptions(aipref=default_preferences())
        )
        errors = validate_policy_jsonld(json.loads(paths["policy.jsonld"].read_text("utf-8")))
        return not errors, {"errores": errors}

    def site_step():
        files = build_site_artifacts(publisher.website, 1, policy.policy_url, default_preferences())
        write_site_artifacts(work / "sitio", files)
        errors, _ = validate_tdmrep_json(json.loads(files[".well-known/tdmrep.json"]))
        return not errors, {"archivos": sorted(files), "errores": errors}

    def manifest_step():
        docs = [work / "libro_TDM.pdf", work / "libro_TDM.epub"]
        m = build_manifest([d for d in docs if d.exists()], base_dir=work)
        m.write(work / "catalogo.csv")
        ok = len(m.rows) == 2 and all(r.get("estado") == "ok" for r in m.rows)
        return ok, {"filas": len(m.rows)}

    step("sellar PDF con ISCC", seal_pdf_step)
    step("sellar EPUB con ISCC", seal_epub_step)
    step("esquema de extensión PDF/A", pdfa_templates_step)
    step("política ODRL", policy_step)
    step("señales del sitio", site_step)
    step("manifiesto del catálogo", manifest_step)

    return {
        "tdm_seal": __version__,
        "carpeta": str(work),
        "iscc_de_contenido_pdf": content_extra_available(),
        "herramientas": tools_status(),
        "pasos": steps,
        "ok": all(s["ok"] for s in steps),
    }
