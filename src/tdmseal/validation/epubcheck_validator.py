"""Validación EPUB con EPUBCheck (opcional, degrada a SKIPPED si no está).

EPUBCheck es una herramienta Java (W3C/DAISY, https://www.w3.org/publishing/epubcheck/).
Se localiza con `tdmseal.tools.find_epubcheck()`: `TDMSEAL_EPUBCHECK_JAR`, la
carpeta de herramientas de TDM Seal (`scripts\\instalar_herramientas.ps1`) o
un comando `epubcheck` en el PATH.

Muchos EPUB reales ya traen avisos o errores de EPUBCheck. Por eso no se
juzga el resultado en absoluto: se valida el original y el sellado, y solo
falla si el sellado tiene errores que el original no tenía.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tdmseal import tools

NOT_INSTALLED = (
    "Validación EPUB omitida (SKIPPED): EPUBCheck no está instalado en este equipo. "
    "El sello se aplicó igual, pero no se comprobó el EPUB resultante con EPUBCheck. "
    "Para activarla, ejecute scripts\\instalar_herramientas.ps1, o descargue EPUBCheck "
    "(https://www.w3.org/publishing/epubcheck/, requiere Java) y defina "
    "TDMSEAL_EPUBCHECK_JAR con la ruta a epubcheck.jar."
)


def _command() -> list[str] | None:
    return tools.find_epubcheck()


def epubcheck_errors(path: Path, command: list[str]) -> set[str]:
    """Identificadores de mensajes ERROR/FATAL de EPUBCheck para `path`."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run(
            [*command, str(path), "--json", str(report)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            **tools.no_window(),
        )
        data = json.loads(report.read_text(encoding="utf-8"))
    errors = set()
    for msg in data.get("messages", []):
        if msg.get("severity") in ("ERROR", "FATAL"):
            errors.add(f"{msg.get('ID')}: {msg.get('message')}")
    return errors


def run_epubcheck(input_path: Path, output_path: Path) -> dict:
    command = _command()
    if command is None:
        return {"status": "SKIPPED", "issues": [NOT_INSTALLED]}
    try:
        before = epubcheck_errors(input_path, command)
        after = epubcheck_errors(output_path, command)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "issues": [f"No se pudo ejecutar EPUBCheck: {exc}"]}
    new = sorted(after - before)
    if new:
        return {"status": "FAIL", "issues": [f"EPUBCheck, error nuevo: {e}" for e in new]}
    issues = []
    if before:
        issues.append(
            f"EPUBCheck: el original ya tenía {len(before)} error(es); "
            "el sellado no añadió ninguno."
        )
    return {"status": "PASS", "issues": issues}
