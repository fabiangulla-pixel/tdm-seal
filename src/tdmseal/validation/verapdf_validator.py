"""Validación PDF/A con veraPDF (opcional, degrada a SKIPPED si no está instalado).

veraPDF es una herramienta Java externa: no se distribuye con TDM Seal. Se
localiza con `tdmseal.tools.find_verapdf()` (variable `TDMSEAL_VERAPDF`,
carpeta de herramientas de TDM Seal o PATH; ver
`scripts\\instalar_herramientas.ps1`).

Muchos PDF/A reales ya traen incumplimientos. Por eso se validan el original
y el sellado y solo falla si el sellado tiene reglas incumplidas que el
original no tenía (lo que sí sería culpa del sello).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tdmseal import tools

NOT_INSTALLED = (
    "Validación PDF/A omitida (SKIPPED): veraPDF no está instalado en este equipo. "
    "El sello se aplicó igual, pero no se comprobó la conformidad PDF/A del resultado. "
    "Para activarla, ejecute scripts\\instalar_herramientas.ps1 o instale veraPDF "
    "(https://software.verapdf.org/, requiere Java)."
)


def _iter_results(report: dict):
    """validationResult puede ser un objeto o una lista según la versión de veraPDF."""
    for job in report.get("report", {}).get("jobs", []) or []:
        results = job.get("validationResult")
        if isinstance(results, dict):
            yield results
        elif isinstance(results, list):
            yield from (r for r in results if isinstance(r, dict))


def parse_verapdf_json(text: str) -> tuple[bool | None, set[str]]:
    """(conforme, reglas incumplidas) a partir de la salida JSON de veraPDF."""
    report = json.loads(text)
    compliant: bool | None = None
    failed: set[str] = set()
    for result in _iter_results(report):
        if result.get("compliant") is not None:
            compliant = (
                bool(result["compliant"])
                if compliant is None
                else (compliant and bool(result["compliant"]))
            )
        details = result.get("details") or {}
        for rule in details.get("ruleSummaries", []) or []:
            if rule.get("status", "failed") == "failed":
                failed.add(
                    f"{rule.get('specification', '')} {rule.get('clause', '')}"
                    f"-{rule.get('testNumber', '')}: {rule.get('description', '')}".strip()
                )
    return compliant, failed


def _validate(command: list[str], path: Path) -> tuple[bool | None, set[str]]:
    proc = subprocess.run(
        [*command, "--format", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
        env=tools.java_env(),
        **tools.no_window(),
    )
    start = proc.stdout.find("{")
    if start < 0:
        raise ValueError(f"salida inesperada de veraPDF: {(proc.stdout or proc.stderr)[:300]}")
    return parse_verapdf_json(proc.stdout[start:])


def run_verapdf(output_path: Path, input_path: Path | None = None) -> dict:
    command = tools.find_verapdf()
    if command is None:
        return {"status": "SKIPPED", "issues": [NOT_INSTALLED]}
    try:
        after_ok, after_failed = _validate(command, output_path)
        before_ok, before_failed = (
            _validate(command, input_path) if input_path is not None else (None, set())
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAIL", "issues": [f"No se pudo ejecutar veraPDF: {exc}"]}
    except (json.JSONDecodeError, ValueError) as exc:
        return {"status": "FAIL", "issues": [f"No se pudo interpretar la salida de veraPDF: {exc}"]}

    if after_ok is True:
        return {"status": "PASS", "issues": []}
    if after_ok is None:
        return {"status": "FAIL", "issues": ["veraPDF no devolvió un resultado de conformidad"]}
    new = sorted(after_failed - before_failed)
    if input_path is not None and before_ok is False and not new:
        return {
            "status": "PASS",
            "issues": [
                f"veraPDF: el original ya incumplía {len(before_failed)} regla(s) PDF/A; "
                "el sellado no añadió ninguna."
            ],
        }
    detail = new or sorted(after_failed)
    return {
        "status": "FAIL",
        "issues": ["veraPDF reporta el PDF/A como no conforme"]
        + [f"veraPDF, regla incumplida: {r}" for r in detail[:10]],
    }
