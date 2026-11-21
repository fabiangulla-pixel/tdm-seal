"""¿Es este archivo uno de mis libros? Compara una copia encontrada (renombrada,
re-guardada, sin metadatos, convertida, recortada o mezclada con otros
textos) con el catálogo, sin conexión.

Escalones, del más fuerte al más débil:
1. SHA-256 o Instance-Code iguales: es el mismo archivo, byte a byte.
2. Text-Code (ISCC de contenido, 64 bits) a poca distancia de Hamming: el mismo
   texto, aunque el archivo sea otro (metadatos quitados, re-guardado,
   otro nombre, PDF regenerado). Ver `TEXT_SAME` y `TEXT_SIMILAR`.
3. Data-Code cercano: bytes muy parecidos.
4. Huellas por fragmentos (`fingerprint.py`, si el manifiesto las tiene):
   extractos de la obra, o la obra dentro de un volcado de texto (.txt,
   .jsonl…), como los conjuntos de datos de entrenamiento.

Sirve contra el manifiesto (`tdmseal manifest`) o el `registro.json`; las
huellas por fragmentos solo están junto al manifiesto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from iscc_core import iscc_distance

from tdmseal import fingerprint as fp

TEXT_SAME = 4  # bits de 64: mismo texto (cambios mínimos de extracción)
TEXT_SIMILAR = 12  # texto muy parecido (otra edición, pequeñas correcciones)
DATA_SIMILAR = 10
EXTRACT_SHARE = 0.5  # parte del archivo que debe venir de la obra para llamarlo extracto
WHOLE_SHARE = 0.8  # parte de la obra presente para decir que la contiene entera


@dataclass
class Match:
    title: str | None
    work: str  # archivo o id del registro
    level: str
    text_distance: int | None
    data_distance: int | None
    reservation: int | None
    policy: str | None
    suspect_share: float | None = None  # parte del archivo que viene de la obra
    work_share: float | None = None  # parte de la obra presente en el archivo
    common: int | None = None

    def describe(self) -> str:
        extra = []
        if self.text_distance is not None:
            extra.append(f"texto a {self.text_distance}/64 bits")
        if self.data_distance is not None:
            extra.append(f"datos a {self.data_distance}/64 bits")
        if self.suspect_share is not None:
            extra.append(
                f"{self.suspect_share:.0%} del archivo viene de la obra; "
                f"contiene el {self.work_share:.0%} de la obra"
            )
        detail = f" ({'; '.join(extra)})" if extra else ""
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
                    "work": record.get("archivo") or record.get("id"),
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


def _iscc_level(suspect, entry, sha256: str) -> tuple[str, int, int | None, int | None] | None:
    text_d = _distance(suspect.text_code, entry["text"])
    data_d = _distance(suspect.data_code, entry["data"])
    if sha256 == entry["sha256"] or (
        entry["instance"] and entry["instance"] == suspect.instance_code
    ):
        return "idéntico", 0, text_d, data_d
    if text_d is not None and text_d <= TEXT_SAME:
        return "mismo texto", 1, text_d, data_d
    if text_d is not None and text_d <= TEXT_SIMILAR:
        return "texto parecido", 2, text_d, data_d
    if data_d is not None and data_d <= DATA_SIMILAR:
        return "datos parecidos", 3, text_d, data_d
    return None


def match_file(path: Path, catalog: Path) -> list[Match]:
    """Obras del catálogo que corresponden a `path`, de la más segura a la menos."""
    path = Path(path)
    entries = _entries(catalog)
    ranked: list[tuple[float, Match]] = []
    found: set[str] = set()

    if path.suffix.lower() in (".pdf", ".epub"):
        from tdmseal.iscc.content import compute_content_iscc
        from tdmseal.timestamp import sha256_file

        suspect = compute_content_iscc(path)
        sha256 = sha256_file(path).hex()
        for entry in entries:
            hit = _iscc_level(suspect, entry, sha256)
            if hit is None:
                continue
            level, rank, text_d, data_d = hit
            found.add(entry["work"])
            match = Match(
                entry["title"],
                entry["work"],
                level,
                text_d,
                data_d,
                entry["reservation"],
                entry["policy"],
            )
            ranked.append((rank * 1000 + (text_d if text_d is not None else 99), match))

    prints = fp.load_fingerprints(catalog)
    if prints:
        suspect_hashes = fp.sample_hashes(fp.extract_text(path))
        by_work = {e["work"]: e for e in entries}
        for work, hashes in prints.items():
            if work in found or work not in by_work:
                continue
            common = len(suspect_hashes & hashes)
            if common < fp.MIN_SAMPLES:
                continue
            s_share, w_share = fp.containment(suspect_hashes, hashes)
            if w_share >= WHOLE_SHARE:
                level, rank = "contiene la obra", 4
            elif s_share >= EXTRACT_SHARE:
                level, rank = "extracto de la obra", 5
            else:
                level, rank = "contiene fragmentos de la obra", 6
            entry = by_work[work]
            match = Match(
                entry["title"],
                work,
                level,
                None,
                None,
                entry["reservation"],
                entry["policy"],
                s_share,
                w_share,
                common,
            )
            ranked.append((rank * 1000 - common / 1e6, match))
    return [m for _, m in sorted(ranked, key=lambda pair: pair[0])]
