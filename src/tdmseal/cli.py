"""CLI de TDM Seal (sección 11 de la especificación)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from tdmseal.appconfig import AppDefaults, load_defaults, save_defaults
from tdmseal.config import SealConfig
from tdmseal.discovery import iter_pdfs
from tdmseal.models import PublisherInfo, TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.policy.builder import PolicyOptions, write_policy_artifacts
from tdmseal.reporting.json_report import write_report
from tdmseal.seal import seal_pdf


def _format_pdfa(info) -> str:
    if info.pdfa_part is None:
        return "no"
    conformance = (info.pdfa_conformance or "").lower()
    return f"PDF/A-{info.pdfa_part}{conformance}"


@click.group()
def main() -> None:
    """TDM Seal — declaraciones TDMRep para PDF editoriales."""


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
) -> None:
    """Sella un PDF o una carpeta de PDF con una declaración TDMRep.

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
    )

    pdfs = iter_pdfs(target, recursive)
    if not pdfs:
        click.echo("No se encontraron PDF para procesar.")
        return

    ok = skipped = failed = 0
    for pdf_path in pdfs:
        result = seal_pdf(pdf_path, config)
        if result.status == "success":
            ok += 1
            click.echo(f"[OK] {pdf_path} -> {result.output_path}")
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
    """Audita un PDF sin modificarlo."""
    info = inspect_pdf(target)
    pdfa = _format_pdfa(info)
    click.echo(f"Archivo: {info.path}")
    click.echo(f"PDF version: {info.pdf_version}")
    click.echo(f"PDF/A: {pdfa}")
    click.echo(f"TDM reservation: {info.tdm.reservation}")
    click.echo(f"TDM policy: {info.tdm.policy_url}")
    click.echo(f"Firma digital: {'sí' if info.signed else 'no'}")
    click.echo(f"Cifrado: {'sí' if info.encrypted else 'no'}")


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["json"]), default="json")
def show(target: Path, fmt: str) -> None:
    """Extrae la declaración TDMRep de un PDF en formato JSON."""
    info = inspect_pdf(target)
    payload = {
        "tdm_reservation": info.tdm.reservation,
        "tdm_policy": info.tdm.policy_url,
        "source": "document-level-xmp" if info.tdm.present else None,
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--recursive", is_flag=True)
def audit(target: Path, recursive: bool) -> None:
    """Audita un catálogo de PDF y resume su estado TDM (sección 36)."""
    pdfs = iter_pdfs(target, recursive)
    for pdf_path in pdfs:
        try:
            info = inspect_pdf(pdf_path)
        except Exception as exc:  # noqa: BLE001 — se reporta y se sigue con el resto
            click.echo(f"{pdf_path.name}\tERROR\t{exc}")
            continue
        pdfa = _format_pdfa(info)
        estado = "OK" if info.tdm.reservation is not None else "FALTA TDM"
        policy = info.tdm.policy_url or "-"
        click.echo(f"{pdf_path.name}\t{info.tdm.reservation}\t{policy}\t{pdfa}\t{estado}")


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
def config_set(
    publisher_name: str | None,
    publisher_acronym: str | None,
    publisher_website: str | None,
    publisher_email: str | None,
    reservation: int | None,
    policy_url: str | None,
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
    save_defaults(defaults)
    click.echo("Valores por defecto actualizados.")


def _publisher_to_dict(defaults: AppDefaults) -> dict:
    return {
        "publisher": {
            "name": defaults.publisher.name,
            "acronym": defaults.publisher.acronym,
            "website": defaults.publisher.website,
            "rights_email": defaults.publisher.rights_email,
        },
        "tdm": {"reservation": defaults.reservation, "policy_url": defaults.policy_url},
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
def policy_build(
    output_dir: Path,
    publisher_name: str | None,
    publisher_website: str | None,
    publisher_email: str | None,
    require_compensation: bool,
    policy_id: str,
) -> None:
    """Genera los artefactos de política TDM a partir de los datos de la editorial.

    Los datos no indicados se toman de los valores por defecto guardados con
    `tdmseal config set`.
    """
    defaults = load_defaults()
    publisher = PublisherInfo(
        name=publisher_name or defaults.publisher.name,
        acronym=defaults.publisher.acronym,
        website=publisher_website or defaults.publisher.website,
        rights_email=publisher_email or defaults.publisher.rights_email,
    )
    options = PolicyOptions(require_compensation=require_compensation, policy_id=policy_id)

    try:
        paths = write_policy_artifacts(output_dir, publisher, options)
    except ValueError as exc:
        click.echo(f"Error: {exc}")
        sys.exit(1)

    for name, path in paths.items():
        click.echo(f"[OK] {name} -> {path}")


if __name__ == "__main__":
    main()
