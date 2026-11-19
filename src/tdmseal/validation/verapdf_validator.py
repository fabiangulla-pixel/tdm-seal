"""Validación PDF/A con veraPDF (opcional, degrada a SKIPPED si no está instalado).

veraPDF es una herramienta Java externa: no se distribuye con TDM Seal. Si el
binario `verapdf` (o `verapdf.bat` en Windows) está disponible en el PATH,
se usa para validar de verdad; si no, la validación se marca `SKIPPED` sin
hacer fallar el sellado — el resto del programa es local-first y no debe
depender de una instalación de Java para funcionar.

Instalación manual (no automatizable de forma fiable): descargar
`verapdf-installer.zip` desde https://software.verapdf.org/, requiere un
JRE/JDK. El instalador es un asistente gráfico (IzPack); no expone una
opción de instalación desatendida confiable para Windows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _find_verapdf() -> str | None:
    for name in ("verapdf", "verapdf.bat", "verapdf.cmd"):
        found = shutil.which(name)
        if found:
            return found
    return None


def run_verapdf(output_path: Path) -> dict:
    binary = _find_verapdf()
    if binary is None:
        return {
            "status": "SKIPPED",
            "issues": [
                "Validación PDF/A omitida (SKIPPED): veraPDF no está instalado en este "
                "equipo. El sello se aplicó igual, pero no se comprobó la conformidad "
                "PDF/A del resultado. Para activarla, instale veraPDF "
                "(https://software.verapdf.org/, requiere Java) y agregue su carpeta al PATH."
            ],
        }

    try:
        proc = subprocess.run(
            [binary, "--format", "json", str(output_path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAIL", "issues": [f"No se pudo ejecutar veraPDF: {exc}"]}

    try:
        report = json.loads(proc.stdout)
        compliant = (
            report.get("report", {})
            .get("jobs", [{}])[0]
            .get("validationResult", {})
            .get("compliant")
        )
    except (json.JSONDecodeError, KeyError, IndexError, AttributeError):
        return {
            "status": "FAIL",
            "issues": [f"No se pudo interpretar la salida de veraPDF: {proc.stdout[:500]}"],
        }

    if compliant is True:
        return {"status": "PASS", "issues": []}
    if compliant is False:
        return {"status": "FAIL", "issues": ["veraPDF reporta el PDF/A como no conforme"]}
    return {"status": "FAIL", "issues": ["veraPDF no devolvió un resultado de conformidad"]}
