"""¿Es este archivo uno de mis libros? Compara una copia encontrada (renombrada,
re-guardada, sin metadatos, convertida) con el catálogo, sin conexión.

Escalones, del más fuerte al más débil:
1. SHA-256 o Instance-Code iguales: es el mismo archivo, byte a byte.
2. Text-Code (ISCC de contenido, 64 bits) a poca distancia de Hamming: el mismo
   texto, aunque el archivo sea otro (metadatos quitados, re-guardado,
   otro nombre, PDF regenerado). Ver `TEXT_SAME` y `TEXT_SIMILAR`.
3. Data-Code cercano: bytes muy parecidos (p. ej. el mismo PDF con una
   actualización incremental añadida).

Sirve contra el manifiesto (`tdmseal manifest`) o el `registro.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from iscc_core import iscc_distance

TEXT_SAME = 4  # bits de 64: mismo texto (cambios mínimos de extracción)
TEXT_SIMILAR = 12  # texto muy parecido (otra edición, pequeñas correcciones)
DATA_SIMILAR = 10


@dataclass
class Match:
    title: str | None
    work: str  # archivo o id del registro
    level: str  # "idéntico" | "mismo texto" | "texto parecido" | "datos parecidos"
    text_distance: int | None
    data_distance: int | None
    reservation: int | None
    policy: str | None

    def describe(self) -> str:
        extra = []
        if self.text_distance is not None:
            extra.append(f"texto a {self.text_distance}/64 bits")
        if self.data_distance is not None:
            extra.append(f"datos a {self.data_distance}/64 bits")
        detail = f" ({', '.join(extra)})" if extra else ""
        return f"{self.level}: {self.title or self.work}{detail}"


def _entries(catalog: Path) -> list[dict]:
    """Normaliza filas del manifiesto o declaraciones del registro a un formato común."""
    data = json.loads(Path(catalog).read_text(encoding="utf-8"))
    out = []
    if isinstance(data, dict) and "works" in data:
        for row in data["works"]:
            out.append(
                {
                    "work": row.get("archivo"),
                    "title": row.get("titulo"),
                    "sha256": row.get("sha256"),
                    "text": row.get("iscc_texto"),
                    "data": row.get("iscc_datos"),
                    "instance": row.get("iscc_instancia"),
                    "reservation": row.get("tdm_reserva"),
                    "policy": row.get("tdm_politica"),
                }
            )
    elif isinstance(data, dict) and "declarations" in data:
        for record in data["declarations"]:
            ids = record.get("identificadores", {})
            decl = record.get("declaracion", {})
            out.append(
                {
                    "work": record.get("id"),
                    "title": record.get("titulo"),
                    "sha256": ids.get("sha256"),
                    "text": ids.get("iscc_texto"),
                    "data": ids.get("iscc_datos"),
                    "instance": ids.get("iscc_instancia"),
                    "reservation": decl.get("tdm_reservation"),
                    "policy": decl.get("tdm_policy"),
                }
            )
    else:
        raise ValueError("se esperaba un manifiesto (.json) o un registro.json de TDM Seal")
    return out


def _distance(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return iscc_distance(a, b)
    except (ValueError, KeyError):
        return None


def match_file(path: Path, catalog: Path) -> list[Match]:
    """Obras del catálogo que corresponden a `path`, de la más segura a la menos."""
    from tdmseal.documents import inspect_document
    from tdmseal.iscc.content import compute_content_iscc

    info = inspect_document(path)
    full = compute_content_iscc(path)
    matches: list[tuple[int, Match]] = []
    for entry in _entries(catalog):
        text_d = _distance(full.text_code, entry["text"])
        data_d = _distance(full.data_code, entry["data"])
        if info.sha256 == entry["sha256"] or (
            entry["instance"] and entry["instance"] == full.instance_code
        ):
            level, rank = "idéntico", 0
        elif text_d is not None and text_d <= TEXT_SAME:
            level, rank = "mismo texto", 1
        elif text_d is not None and text_d <= TEXT_SIMILAR:
            level, rank = "texto parecido", 2
        elif data_d is not None and data_d <= DATA_SIMILAR:
            level, rank = "datos parecidos", 3
        else:
            continue
        matches.append(
            (
                rank * 1000 + (text_d if text_d is not None else 99),
                Match(
                    entry["title"],
                    entry["work"],
                    level,
                    text_d,
                    data_d,
                    entry["reservation"],
                    entry["policy"],
                ),
            )
        )
    return [m for _, m in sorted(matches, key=lambda pair: pair[0])]
