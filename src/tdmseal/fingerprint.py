"""Huellas de texto por fragmentos: reconocer extractos de un libro y libros
dentro de volcados de texto (p. ej. un conjunto de datos de entrenamiento).

El ISCC de contenido resume el libro entero en 64 bits: reconoce copias
completas aunque estén renombradas o sin metadatos, pero no un capítulo
suelto. Aquí se guarda una muestra de "tejas" (secuencias de 5 palabras
normalizadas) con muestreo por valor de hash, que no depende de dónde empieza
el extracto. Con ella se mide:

- qué parte del archivo sospechoso proviene de la obra (¿es un extracto?);
- qué parte de la obra está en el archivo sospechoso (¿la contiene entera?).

Solo se guardan hashes de 64 bits: el texto no se puede reconstruir a partir
de ellos. Se generan junto al manifiesto (`MANIFIESTO.huellas.json`) y no se
publican en el registro.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import iscc_core as ic

SHINGLE = 5
SAMPLE_MOD = 16  # se guarda ~1 de cada 16 tejas
MIN_SAMPLES = 12  # por debajo, demasiado poco texto para concluir
TEXT_SUFFIXES = (".txt", ".md", ".jsonl", ".json", ".csv", ".html", ".htm", ".xml")

_WORD = re.compile(r"\w+", re.UNICODE)


def normalize_words(text: str) -> list[str]:
    return _WORD.findall(ic.text_clean(text).lower())


def sample_hashes(text: str) -> set[int]:
    words = normalize_words(text)
    out: set[int] = set()
    for i in range(len(words) - SHINGLE + 1):
        shingle = " ".join(words[i : i + SHINGLE]).encode("utf-8")
        value = int.from_bytes(hashlib.blake2b(shingle, digest_size=8).digest(), "big")
        if value % SAMPLE_MOD == 0:
            out.add(value)
    return out


def extract_text(path: Path) -> str:
    """Texto de un PDF, EPUB o archivo de texto (volcados, JSONL, HTML…)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from tdmseal.iscc.content import extract_pdf_text

        return extract_pdf_text(path)
    if suffix == ".epub":
        from tdmseal.iscc.content import extract_epub_text

        return extract_epub_text(path)
    if suffix in TEXT_SUFFIXES:
        raw = path.read_bytes().decode("utf-8", errors="replace")
        if suffix in (".html", ".htm", ".xml"):
            raw = re.sub(r"<[^>]+>", " ", raw)
        elif suffix in (".jsonl", ".json"):
            # Los conjuntos de datos guardan el texto en cadenas JSON con los saltos
            # escapados ("\n"): sin decodificar, las palabras quedarían pegadas.
            raw = _json_text(raw, lines=suffix == ".jsonl")
        return raw
    raise ValueError(f"formato no admitido para comparar texto: {suffix}")


def _strings(value, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)


def _json_text(raw: str, *, lines: bool) -> str:
    out: list[str] = []
    chunks = raw.splitlines() if lines else [raw]
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            _strings(json.loads(chunk), out)
        except ValueError:
            out.append(chunk)  # línea que no es JSON: se toma tal cual
    return "\n".join(out)


def fingerprints_path(manifest: Path) -> Path:
    return (
        Path(str(manifest) + ".huellas.json")
        if not str(manifest).endswith(".huellas.json")
        else Path(manifest)
    )


def write_fingerprints(manifest: Path, works: dict[str, Path]) -> Path:
    """works: identificador de la fila (archivo) -> ruta del documento."""
    data: dict = {"shingle": SHINGLE, "mod": SAMPLE_MOD, "works": {}}
    for work, path in works.items():
        try:
            hashes = sample_hashes(extract_text(path))
        except Exception:  # noqa: BLE001 — sin texto (escaneado, cifrado): sin huella
            continue
        data["works"][work] = sorted(f"{h:016x}" for h in hashes)
    out = fingerprints_path(manifest)
    out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    return out


def load_fingerprints(manifest: Path) -> dict[str, set[int]]:
    path = fingerprints_path(manifest)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("shingle") != SHINGLE or data.get("mod") != SAMPLE_MOD:
        raise ValueError("huellas generadas con otros parámetros; regenere el manifiesto")
    return {work: {int(h, 16) for h in hashes} for work, hashes in data["works"].items()}


def containment(suspect: set[int], work: set[int]) -> tuple[float, float]:
    """(parte del sospechoso que viene de la obra, parte de la obra presente)."""
    if not suspect or not work:
        return 0.0, 0.0
    common = len(suspect & work)
    return common / len(suspect), common / len(work)
