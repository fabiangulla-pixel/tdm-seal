"""CLI de TDM Seal (sección 11 de la especificación)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from tdmseal.config import SealConfig
from tdmseal.models import TDMPolicy
from tdmseal.pdf.inspector import inspect_pdf
from tdmseal.reporting.json_report import write_report
from tdmseal.seal import seal_pdf


def _iter_pdfs(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        return [target]
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in target.glob(pattern) if p.is_file())


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
@click.option("--reservation", type=click.IntRange(0, 1), default=1, show_default=True)
@click.option("--policy", "policy_url", default=None, help="URL de la política TDM (opcional).")
@click.option("--recursive", is_flag=True, help="Procesar subcarpetas si TARGET es una carpeta.")
@click.option("--suffix", default="_TDM", show_default=True, help="Sufijo del archivo de salida.")
@click.option("--force-signed", is_flag=True, help="PELIGROSO: modifica PDF con firma digital.")
@click.option("--allow-encrypted", is_flag=True, help="Permite procesar PDF cifrados.")
def seal(
    target: Path,
    reservation: int,
    policy_url: str | None,
    recursive: bool,
    suffix: str,
    force_signed: bool,
    allow_encrypted: bool,
) -> None:
    """Sella un PDF o una carpeta de PDF con una declaración TDMRep."""
    policy = TDMPolicy(reservation=reservation, policy_url=policy_url)
    config = SealConfig(
        policy=policy,
        output_suffix=suffix,
        force_signed=force_signed,
        allow_encrypted=allow_encrypted,
    )

    pdfs = _iter_pdfs(target, recursive)
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
            write_report(result, report_path)

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
    pdfs = _iter_pdfs(target, recursive)
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


if __name__ == "__main__":
    main()
