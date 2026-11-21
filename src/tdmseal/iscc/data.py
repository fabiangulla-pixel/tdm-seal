"""Identificador ISCC del archivo (International Standard Content Code).

El ISCC se calcula a partir del propio contenido binario del archivo, no de
su nombre, su ruta ni la dirección donde está alojado. Por eso reconoce un
mismo archivo aunque cambie de nombre o de ubicación; un cambio de contenido
(otra conversión, una recompresión, etc.) produce un ISCC distinto. No
sustituye al ISBN, al DOI ni a ONIX: los complementa, ya que esos
identificadores describen la obra y su publicación, mientras que el ISCC
identifica el archivo concreto.

Se componen aquí dos unidades ISCC (sección 2.2 de la especificación ISCC):

- Instance-Code: hash criptográfico (BLAKE3) del archivo completo, único por
  bit; detecta cualquier cambio, por mínimo que sea.
- Data-Code: hash de similitud sobre la secuencia binaria; dos archivos con
  contenido casi idéntico (p. ej. tras volver a guardar el mismo PDF) quedan
  cerca entre sí, a diferencia del Instance-Code.

Ambas se combinan en un ISCC-CODE compuesto. No se genera aquí Content-Code
(requiere extracción de texto específica por formato) ni Meta-Code (requiere
metadatos descriptivos como título/autor); quedan para una fase posterior si
se decide incorporarlos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import iscc_core as ic


@dataclass(frozen=True)
class IsccResult:
    """ISCC calculado para un archivo, con sus unidades componentes."""

    iscc: str
    data_code: str
    instance_code: str
    datahash: str
    filesize: int


def compute_iscc(path: Path, bits: int = 64) -> IsccResult:
    """Calcula el ISCC de un archivo a partir de su contenido binario.

    No lee ni depende del nombre del archivo, su ruta ni ninguna ubicación
    externa: dos copias idénticas en bytes, en cualquier carpeta o con
    cualquier nombre, producen el mismo ISCC. `bits=256` da las unidades
    completas que exige la red de hubs ISCC (el ISCC-CODE no cambia).
    """
    path = Path(path)

    with open(path, "rb") as stream:
        data_code = ic.gen_data_code(stream, bits=bits)
    with open(path, "rb") as stream:
        instance_code = ic.gen_instance_code(stream, bits=bits)

    combined = ic.gen_iscc_code([data_code["iscc"], instance_code["iscc"]])

    return IsccResult(
        iscc=combined["iscc"],
        data_code=data_code["iscc"],
        instance_code=instance_code["iscc"],
        datahash=instance_code["datahash"],
        filesize=instance_code["filesize"],
    )
