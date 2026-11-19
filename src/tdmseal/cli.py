"""CLI de TDM Seal (sección 11 de la especificación)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from tdmseal.aipref import AiPreferences, AiPrefError
from tdmseal.appconfig import AppDefaults, load_defaults, save_defaults
from tdmseal.config import SealConfig
from tdmseal.discovery import iter_documents
from tdmseal.documents import inspect_document, seal_document
from tdmseal.errors import TDMSealError
from tdmseal.iscc.content import (
    NO_EXTRA_WARNING,
    compute_content_iscc,
    content_extra_available,
)
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.notice import notice_from_publisher
from tdmseal.policy.builder import PolicyOptions, write_policy_artifacts
from tdmseal.policy.policy_validator import validate_policy_jsonld
from tdmseal.reporting.json_report import write_report
from tdmseal.site import build_site_artifacts, validate_tdmrep_json, write_site_artifacts
from tdmseal.xmp.tdmrep import validate_policy_url


def _format_pdfa(info) -> str:
    if info.pdfa_part is None:
        return "no"
    conformance = (info.pdfa_conformance or "").lower()
    return f"PDF/A-{info.pdfa_part}{conformance}"


def _parse_aipref_or_exit(text: str) -> AiPreferences:
    try:
        return AiPreferences.parse(text)
    except AiPrefError as exc:
        click.echo(f"Error: {exc}")
        sys.exit(2)


@click.group()
def main() -> None:
    """TDM Seal — declaraciones TDMRep para PDF y EPUB editoriales."""


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--reservation", type=click.IntRange(0, 1), default=None)
@click.option("--policy", "policy_url", default=None, help="URL de la política TDM (opcional).")
@click.option("--recursive", is_flag=True, help="Procesar subcarpetas si TARGET es una carpeta.")
@click.option("--suffix", default="_TDM", show_default=True, help="Sufijo del archivo de salida.")
@click.option("--force-signed", is_flag=True, help="PELIGROSO: modifica PDF con firma digital.")
@click.option("--allow-encrypted", is_flag=True, help="Permite procesar PDF cifrados.")
@click.option("--publisher-name", default=None, help="Nombre de la editorial (para el reporte).")
@click.option("--publisher-acronym", default=None)
@click.option("--publisher-website", default=None)
@click.option("--publisher-email", default=None, help="Correo de derechos (para el reporte).")
@click.option(
    "--iscc",
    "with_iscc",
    is_flag=True,
    help="Calcular el ISCC completo y escribirlo en el XMP (ver `tdmseal iscc`).",
)
@click.option(
    "--aipref",
    default=None,
    help='Preferencias IETF AIPREF, p. ej. "train-ai=n, ai-use=n, search=y" '
    "(se registran en el reporte; ver `tdmseal site`).",
)
@click.option(
    "--visible-notice",
    is_flag=True,
    help="Añade una página final (PDF) o un documento final (EPUB) con el aviso de "
    "reserva en lenguaje claro. Cambia el contenido visible: desactivado por defecto.",
)
def seal(
    target: Path,
    reservation: int | None,
    policy_url: str | None,
    recursive: bool,
    suffix: str,
    force_signed: bool,
    allow_encrypted: bool,
    publisher_name: str | None,
    publisher_acronym: str | None,
    publisher_website: str | None,
    publisher_email: str | None,
    with_iscc: bool,
    aipref: str | None,
    visible_notice: bool,
) -> None:
    """Sella un PDF/EPUB o una carpeta de ellos con una declaración TDMRep.

    Los valores no indicados por línea de comandos se toman de los valores
    por defecto guardados con `tdmseal config set` (editorial, reserva,
    política). Ver `tdmseal config show`.
    """
    defaults = load_defaults()
    policy = TDMPolicy(
        reservation=reservation if reservation is not None else defaults.reservation,
        policy_url=policy_url or defaults.policy_url,
    )
    publisher = PublisherInfo(
        name=publisher_name or defaults.publisher.name,
        acronym=publisher_acronym or defaults.publisher.acronym,
        website=publisher_website or defaults.publisher.website,
        rights_email=publisher_email or defaults.publisher.rights_email,
    )
    config = SealConfig(
        policy=policy,
        output_suffix=suffix,
        force_signed=force_signed,
        allow_encrypted=allow_encrypted,
        compute_iscc=with_iscc,
        aipref=_parse_aipref_or_exit(aipref or defaults.aipref),
    )
    if visible_notice:
        try:
            config.notice = notice_from_publisher(publisher, policy.policy_url)
        except ValueError as exc:
            click.echo(f"Error: {exc} Use --publisher-name y --publisher-email.")
            sys.exit(2)

    pdfs = iter_documents(target, recursive)
    if not pdfs:
        click.echo("No se encontraron PDF ni EPUB para procesar.")
        return
    if with_iscc and not content_extra_available():
        click.echo(f"Aviso: {NO_EXTRA_WARNING}")

    ok = skipped = failed = 0
    for pdf_path in pdfs:
        result = seal_document(pdf_path, config)
        if result.status == "success":
            ok += 1
            click.echo(f"[OK] {pdf_path} -> {result.output_path}")
            if result.iscc_input is not None:
                click.echo(f"     ISCC original: {result.iscc_input.iscc}")
        elif result.status == "skipped":
            skipped += 1
            click.echo(f"[OMITIDO {result.reason_code}] {pdf_path}: {'; '.join(result.errors)}")
        else:
            failed += 1
            click.echo(f"[ERROR {result.reason_code}] {pdf_path}: {'; '.join(result.errors)}")

        if result.output_path is not None:
            report_suffix = result.output_path.suffix + ".report.json"
            report_path = result.output_path.with_suffix(report_suffix)
            write_report(result, report_path, publisher)

    click.echo(
        f"\n{len(pdfs)} archivos procesados: {ok} correctos, {skipped} omitidos, {failed} con error"
    )
    if failed:
        sys.exit(1)


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
def inspect(target: Path) -> None:
    """Audita un PDF o EPUB sin modificarlo."""
    info = inspect_document(target)
    click.echo(f"Archivo: {info.path}")
    click.echo(f"ISCC: {info.iscc}")
    if info.kind == "epub":
        click.echo(f"EPUB version: {info.epub_version}")
        click.echo(f"Paquete OPF: {info.opf_path}")
        click.echo(f"DRM / cifrado: {info.drm or 'no'}")
    else:
        click.echo(f"PDF version: {info.pdf_version}")
        click.echo(f"PDF/A: {_format_pdfa(info)}")
        click.echo(f"Firma digital: {'sí' if info.signed else 'no'}")
        click.echo(f"Cifrado: {'sí' if info.encrypted else 'no'}")
    click.echo(f"TDM reservation: {info.tdm.reservation}")
    click.echo(f"TDM policy: {info.tdm.policy_url}")
    if info.declared_iscc is not None:
        click.echo(f"ISCC de contenido declarado: {info.declared_iscc.content_code}")
        click.echo(f"ISCC del original declarado: {info.declared_iscc.source_iscc}")


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["json"]), default="json")
def show(target: Path, fmt: str) -> None:
    """Extrae la declaración TDMRep de un PDF o EPUB en formato JSON."""
    info = inspect_document(target)
    source = "document-level-xmp" if info.kind == "pdf" else "opf-package-metadata"
    payload = {
        "iscc": info.iscc,
        "tdm_reservation": info.tdm.reservation,
        "tdm_policy": info.tdm.policy_url,
        "source": source if info.tdm.present else None,
        "declared_iscc": info.declared_iscc.to_dict() if info.declared_iscc else None,
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@main.command("iscc")
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", is_flag=True, help="Procesar subcarpetas si TARGET es una carpeta.")
@click.option("--json", "as_json", is_flag=True, help="Salida en JSON.")
def iscc_command(target: Path, recursive: bool, as_json: bool) -> None:
    """Calcula el ISCC completo de uno o varios PDF/EPUB, sin modificarlos.

    ISCC-CODE = Meta-Code + Text-Code + Data-Code + Instance-Code, compatible
    con iscc-sdk. El Text-Code se calcula sobre el texto y no cambia al
    sellar; requiere el extra `tdm-seal[iscc]` (PDF) o `[iscc-epub]` (EPUB).
    """
    pdfs = iter_documents(target, recursive)
    if not pdfs:
        click.echo("No se encontraron PDF ni EPUB para procesar.")
        return
    results: dict[str, dict] = {}
    failed = 0
    for pdf_path in pdfs:
        try:
            result = compute_content_iscc(pdf_path)
        except Exception as exc:  # noqa: BLE001 — se reporta y se sigue con el resto
            failed += 1
            results[str(pdf_path)] = {"error": str(exc)}
            if not as_json:
                click.echo(f"{pdf_path.name}\tERROR\t{exc}")
            continue
        results[str(pdf_path)] = result.to_dict()
        if not as_json:
            click.echo(f"{pdf_path.name}")
            click.echo(f"  ISCC-CODE:    {result.iscc}")
            click.echo(f"  Meta-Code:    {result.meta_code}  ({result.name})")
            click.echo(f"  Text-Code:    {result.text_code or '—'}")
            click.echo(f"  Data-Code:    {result.data_code}")
            click.echo(f"  Instance:     {result.instance_code}")
            for warning in result.warnings:
                click.echo(f"  Aviso: {warning}")
    if as_json:
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))
    if failed:
        sys.exit(1)


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", is_flag=True)
def audit(target: Path, recursive: bool) -> None:
    """Audita un catálogo de PDF y EPUB y resume su estado TDM (sección 36)."""
    pdfs = iter_documents(target, recursive)
    for pdf_path in pdfs:
        try:
            info = inspect_document(pdf_path)
        except Exception as exc:  # noqa: BLE001 — se reporta y se sigue con el resto
            click.echo(f"{pdf_path.name}\tERROR\t{exc}")
            continue
        pdfa = f"EPUB {info.epub_version}" if info.kind == "epub" else _format_pdfa(info)
        estado = "OK" if info.tdm.reservation is not None else "FALTA TDM"
        policy = info.tdm.policy_url or "-"
        click.echo(
            f"{pdf_path.name}\t{info.iscc}\t{info.tdm.reservation}\t{policy}\t{pdfa}\t{estado}"
        )


@main.group()
def config() -> None:
    """Valores por defecto guardados (editorial, reserva TDM, política)."""


@config.command("show")
def config_show() -> None:
    """Muestra los valores por defecto guardados."""
    defaults = load_defaults()
    click.echo(json.dumps(_publisher_to_dict(defaults), ensure_ascii=False, indent=2))


@config.command("set")
@click.option("--publisher-name", default=None)
@click.option("--publisher-acronym", default=None)
@click.option("--publisher-website", default=None)
@click.option("--publisher-email", default=None)
@click.option("--reservation", type=click.IntRange(0, 1), default=None)
@click.option("--policy", "policy_url", default=None)
@click.option("--aipref", default=None, help='Ej.: "train-ai=n, ai-use=n, search=y"')
def config_set(
    publisher_name: str | None,
    publisher_acronym: str | None,
    publisher_website: str | None,
    publisher_email: str | None,
    reservation: int | None,
    policy_url: str | None,
    aipref: str | None,
) -> None:
    """Actualiza los valores por defecto guardados (solo lo indicado cambia)."""
    defaults = load_defaults()
    if publisher_name is not None:
        defaults.publisher.name = publisher_name
    if publisher_acronym is not None:
        defaults.publisher.acronym = publisher_acronym
    if publisher_website is not None:
        defaults.publisher.website = publisher_website
    if publisher_email is not None:
        defaults.publisher.rights_email = publisher_email
    if reservation is not None:
        defaults.reservation = reservation
    if policy_url is not None:
        defaults.policy_url = policy_url
    if aipref is not None:
        defaults.aipref = _parse_aipref_or_exit(aipref).serialize()
    save_defaults(defaults)
    click.echo("Valores por defecto actualizados.")


@main.command()
@click.option(
    "--base-url", default=None, help="URL raíz del sitio, p. ej. https://editorial.ejemplo/"
)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(path_type=Path),
    default=Path("publicar"),
    show_default=True,
    help="Carpeta donde se generan los archivos (no se sube nada).",
)
@click.option("--reservation", type=click.IntRange(0, 1), default=None)
@click.option("--policy", "policy_url", default=None, help="URL de la política TDM.")
@click.option("--aipref", default=None, help='Ej.: "train-ai=n, ai-use=n, search=y"')
@click.option("--location", default="/", show_default=True, help="Patrón de rutas de la regla.")
@click.option(
    "--check",
    "check_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Solo validar un tdmrep.json existente.",
)
def site(
    base_url: str | None,
    out_dir: Path,
    reservation: int | None,
    policy_url: str | None,
    aipref: str | None,
    location: str,
    check_file: Path | None,
) -> None:
    """Genera las señales TDM del sitio web: /.well-known/tdmrep.json, cabeceras
    HTTP para Apache y Nginx, la regla Content-Usage de robots.txt y las
    metaetiquetas HTML. No publica nada: deja los archivos en --out.
    """
    if check_file is not None:
        try:
            data = json.loads(check_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            click.echo(f"[ERROR] JSON inválido: {exc}")
            sys.exit(1)
        errors, warnings = validate_tdmrep_json(data)
        for warning in warnings:
            click.echo(f"[AVISO] {warning}")
        for error in errors:
            click.echo(f"[ERROR] {error}")
        if errors:
            sys.exit(1)
        click.echo(f"[OK] {check_file} cumple TDMRep (sec. 6.1).")
        return

    if not base_url:
        click.echo("Error: falta --base-url (o use --check ARCHIVO para validar).")
        sys.exit(2)
    defaults = load_defaults()
    reservation = reservation if reservation is not None else defaults.reservation
    policy_url = policy_url or defaults.policy_url
    prefs = _parse_aipref_or_exit(aipref or defaults.aipref)
    for warning in prefs.check_consistency(reservation):
        click.echo(f"[AVISO] {warning}")
    try:
        if policy_url:
            validate_policy_url(policy_url)
        files = build_site_artifacts(base_url, reservation, policy_url, prefs, location)
    except (ValueError, TDMSealError) as exc:
        click.echo(f"Error: {exc}")
        sys.exit(2)
    for rel, path in write_site_artifacts(out_dir, files).items():
        click.echo(f"[OK] {rel} -> {path}")
    click.echo(f"\nLea {out_dir / 'LEEME.txt'} para saber dónde va cada archivo.")


def _publisher_to_dict(defaults: AppDefaults) -> dict:
    return {
        "publisher": {
            "name": defaults.publisher.name,
            "acronym": defaults.publisher.acronym,
            "website": defaults.publisher.website,
            "rights_email": defaults.publisher.rights_email,
        },
        "tdm": {"reservation": defaults.reservation, "policy_url": defaults.policy_url},
        "aipref": defaults.aipref,
    }


@main.group()
def policy() -> None:
    """Policy Builder: genera policy.jsonld, policy.html y tdmrep.json (sección 27)."""


@policy.command("build")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("."))
@click.option("--publisher-name", default=None)
@click.option("--publisher-website", default=None, help="URL del sitio web (se deriva el dominio).")
@click.option("--publisher-email", default=None, help="Correo de derechos.")
@click.option(
    "--require-compensation",
    is_flag=True,
    help="Exigir compensación económica además de consentimiento.",
)
@click.option("--policy-id", default="1", show_default=True)
@click.option(
    "--policy-url",
    default=None,
    help="URL donde se publicará policy.jsonld (por defecto https://DOMINIO/tdm/policies/ID).",
)
@click.option(
    "--research",
    type=click.Choice(["free", "consent", "compensate", "none"]),
    default=None,
    help="Condiciones para investigación (por defecto: consent).",
)
@click.option(
    "--non-research",
    type=click.Choice(["free", "consent", "compensate", "none"]),
    default=None,
    help="Condiciones para otros fines, incluido el comercial (por defecto: consent).",
)
@click.option("--license-url", default=None, help="Página o formulario para pedir licencias.")
@click.option("--aipref", default=None, help='Ej.: "train-ai=n, ai-use=n, search=y"')
def policy_build(
    output_dir: Path,
    publisher_name: str | None,
    publisher_website: str | None,
    publisher_email: str | None,
    require_compensation: bool,
    policy_id: str,
    policy_url: str | None,
    research: str | None,
    non_research: str | None,
    license_url: str | None,
    aipref: str | None,
) -> None:
    """Genera los artefactos de política TDM a partir de los datos de la editorial.

    La política es una oferta de licencia (ODRL, perfil TDMRep): describe en
    qué condiciones se puede pedir permiso, por finalidad. Los datos no
    indicados se toman de los valores por defecto (`tdmseal config set`).
    """
    defaults = load_defaults()
    publisher = PublisherInfo(
        name=publisher_name or defaults.publisher.name,
        acronym=defaults.publisher.acronym,
        website=publisher_website or defaults.publisher.website,
        rights_email=publisher_email or defaults.publisher.rights_email,
    )
    options = PolicyOptions(
        require_compensation=require_compensation,
        policy_id=policy_id,
        policy_url=policy_url,
        research=research,
        non_research=non_research,
        license_contact_url=license_url,
        aipref=_parse_aipref_or_exit(aipref or defaults.aipref),
    )

    try:
        paths = write_policy_artifacts(output_dir, publisher, options)
    except ValueError as exc:
        click.echo(f"Error: {exc}")
        sys.exit(1)

    for name, path in paths.items():
        click.echo(f"[OK] {name} -> {path}")


@policy.command("check")
@click.argument("policy_file", type=click.Path(exists=True, path_type=Path))
def policy_check(policy_file: Path) -> None:
    """Valida un policy.jsonld contra el perfil ODRL de TDMRep."""
    try:
        data = json.loads(policy_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        click.echo(f"[ERROR] JSON inválido: {exc}")
        sys.exit(1)
    errors = validate_policy_jsonld(data)
    for error in errors:
        click.echo(f"[ERROR] {error}")
    if errors:
        sys.exit(1)
    click.echo(f"[OK] {policy_file} cumple el perfil ODRL de TDMRep.")


if __name__ == "__main__":
    main()
