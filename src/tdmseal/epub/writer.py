"""Reescritura del contenedor EPUB cambiando solo el paquete OPF.

Reglas (EPUB 3.3, OCF):
- `mimetype` es la primera entrada, sin comprimir y sin campo extra;
- el resto de entradas se copian con su mismo nombre, orden, fecha,
  atributos y método de compresión, y con el mismo contenido (mismo CRC);
- solo cambia el contenido del OPF.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from tdmseal.epub.container import MIMETYPE


def _clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    clone.compress_type = info.compress_type
    clone.external_attr = info.external_attr
    clone.create_system = info.create_system
    clone.comment = info.comment
    return clone


def rewrite_epub(
    input_path: Path,
    output_path: Path,
    replacements: dict[str, bytes],
    additions: dict[str, bytes] | None = None,
) -> bool:
    """Copia el EPUB cambiando solo las entradas de `replacements` y añadiendo
    al final las de `additions` (aviso visible).

    Devuelve True si hubo que reparar la entrada `mimetype` (no estaba
    primera o estaba comprimida), cosa que se informa como aviso.
    """
    repaired = False
    with zipfile.ZipFile(input_path) as zin:
        infos = zin.infolist()
        mimetype_info = next((i for i in infos if i.filename == "mimetype"), None)
        if mimetype_info is None:
            raise ValueError("el EPUB no tiene la entrada 'mimetype'")
        if infos[0] is not mimetype_info or mimetype_info.compress_type != zipfile.ZIP_STORED:
            repaired = True

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as zout:
            mt = zipfile.ZipInfo("mimetype", date_time=mimetype_info.date_time)
            mt.compress_type = zipfile.ZIP_STORED
            mt.external_attr = mimetype_info.external_attr
            zout.writestr(mt, MIMETYPE)

            for info in infos:
                if info.filename == "mimetype":
                    continue
                data = replacements.get(info.filename)
                if data is None:
                    data = zin.read(info.filename)
                zout.writestr(_clone_info(info), data)
            existing = {i.filename for i in infos}
            for name, data in (additions or {}).items():
                if name in existing:
                    raise ValueError(f"ya existe una entrada {name} en el EPUB")
                new = zipfile.ZipInfo(name, date_time=mimetype_info.date_time)
                new.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(new, data)
            if zin.comment:
                zout.comment = zin.comment
    return repaired


def compare_container(
    input_path: Path, output_path: Path, changed: set[str], added: set[str] | None = None
) -> dict:
    """Comprueba que solo cambiaron `changed`, que solo se añadieron `added` (al
    final) y que `mimetype` es válido."""
    issues: list[str] = []
    added = added or set()
    with zipfile.ZipFile(input_path) as a, zipfile.ZipFile(output_path) as b:
        names_a = [i.filename for i in a.infolist() if i.filename != "mimetype"]
        names_b = [i.filename for i in b.infolist() if i.filename != "mimetype"]
        if names_b[len(names_a) :] and set(names_b[len(names_a) :]) != added:
            issues.append(f"entradas añadidas inesperadas: {names_b[len(names_a) :]}")
        names_b = names_b[: len(names_a)]
        if names_a != names_b:
            issues.append("cambió la lista u orden de entradas del contenedor")
        crc_a = {i.filename: i.CRC for i in a.infolist()}
        for info in b.infolist():
            if info.filename in changed or info.filename in added or info.filename == "mimetype":
                continue
            if crc_a.get(info.filename) != info.CRC:
                issues.append(f"cambió el contenido de {info.filename}")
        first = b.infolist()[0]
        if not (
            first.filename == "mimetype"
            and first.compress_type == zipfile.ZIP_STORED
            and b.read("mimetype") == MIMETYPE
        ):
            issues.append("'mimetype' no es la primera entrada sin comprimir")
        bad = b.testzip()
        if bad is not None:
            issues.append(f"entrada corrupta en la salida: {bad}")
    return {"status": "PASS" if not issues else "FAIL", "issues": issues}
