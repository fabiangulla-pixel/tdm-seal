"""ISCC dentro del XMP de nivel de documento (namespace propio de TDM Seal).

Ni TDMRep ni ISCC definen dónde guardar un ISCC en el XMP de un PDF (iscc-sdk
solo escribe claves `/iscc_*` en el diccionario Info, y no el código). Se usa
un namespace propio, documentado en `docs/xmp-namespace-iscc.md`:

    https://github.com/fabiangulla-pixel/tdm-seal/ns/iscc/1.0/   (prefijo tdmseal)

Propiedades (todas de texto):

- `tdmseal:isccContentCode`: Text-Code del contenido. No cambia al sellar;
  es el que permite reconocer la obra aunque el archivo cambie de bytes.
- `tdmseal:isccSource`: ISCC-CODE completo del archivo **antes** de sellar.
  No puede escribirse el ISCC del archivo sellado dentro de sí mismo: al
  escribirlo cambiarían sus bytes y, con ellos, su Data-Code e Instance-Code.
- `tdmseal:isccSourceDatahash`: hash BLAKE3 (multihash) del archivo antes de
  sellar, para comprobar bit a bit que un archivo es ese original.

Al volver a sellar un archivo ya sellado se conserva la procedencia: si el
Text-Code coincide con el ya declarado, `isccSource` e `isccSourceDatahash`
no se sobrescriben (siguen apuntando al original de la primera vez).
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from tdmseal.xmp.parser import RDF_NS, get_simple_property_text, iter_descriptions

ISCC_XMP_NS = "https://github.com/fabiangulla-pixel/tdm-seal/ns/iscc/1.0/"
ISCC_XMP_PREFIX = "tdmseal"

_CONTENT = f"{{{ISCC_XMP_NS}}}isccContentCode"
_SOURCE = f"{{{ISCC_XMP_NS}}}isccSource"
_DATAHASH = f"{{{ISCC_XMP_NS}}}isccSourceDatahash"
_ALL = (_CONTENT, _SOURCE, _DATAHASH)
_ABOUT_ATTR = f"{{{RDF_NS}}}about"


@dataclass(frozen=True)
class DeclaredIscc:
    content_code: str | None
    source_iscc: str | None
    source_datahash: str | None

    def to_dict(self) -> dict:
        return {
            "content_code": self.content_code,
            "source_iscc": self.source_iscc,
            "source_datahash": self.source_datahash,
        }


def _doc_descriptions(rdf_root: etree._Element):
    for desc in iter_descriptions(rdf_root):
        if desc.get(_ABOUT_ATTR) == "":
            yield desc


def read_declared_iscc(rdf_root: etree._Element) -> DeclaredIscc | None:
    """Lee las propiedades tdmseal:iscc* del XMP; None si no hay ninguna."""
    values: dict[str, str | None] = dict.fromkeys(_ALL)
    for desc in _doc_descriptions(rdf_root):
        for tag in _ALL:
            if values[tag] is None:
                values[tag] = get_simple_property_text(desc, tag)
    if not any(values.values()):
        return None
    return DeclaredIscc(
        content_code=values[_CONTENT],
        source_iscc=values[_SOURCE],
        source_datahash=values[_DATAHASH],
    )


def resolve_provenance(
    existing: DeclaredIscc | None,
    content_code: str | None,
    source_iscc: str,
    source_datahash: str,
) -> tuple[str | None, str, str]:
    """Decide qué valores escribir (regla común a PDF y EPUB).

    Re-sellado del mismo contenido (Text-Code igual, o no calculable ahora):
    se conserva la procedencia original. Si no hay `content_code`, no se borra
    uno ya declarado: no tener con qué calcularlo no prueba que haya cambiado.
    """
    if (
        existing is not None
        and existing.source_iscc
        and (content_code is None or existing.content_code == content_code)
    ):
        return (
            content_code or existing.content_code,
            existing.source_iscc,
            existing.source_datahash or source_datahash,
        )
    return content_code, source_iscc, source_datahash


def write_declared_iscc(
    rdf_root: etree._Element,
    *,
    content_code: str | None,
    source_iscc: str,
    source_datahash: str,
) -> str:
    """Escribe o actualiza las propiedades ISCC. Devuelve create/update/unchanged.

    Si no hay `content_code` (sin extra o PDF sin texto), no se borra uno ya
    declarado: no tener con qué calcularlo no prueba que haya cambiado.
    """
    existing = read_declared_iscc(rdf_root)
    content_code, source_iscc, source_datahash = resolve_provenance(
        existing, content_code, source_iscc, source_datahash
    )

    target = None
    for desc in _doc_descriptions(rdf_root):
        if any(get_simple_property_text(desc, tag) is not None for tag in _ALL):
            if target is None:
                target = desc
            else:  # consolidar: no dejar declaraciones duplicadas
                for tag in _ALL:
                    _remove(desc, tag)
    if target is None:
        nsmap = {"rdf": RDF_NS, ISCC_XMP_PREFIX: ISCC_XMP_NS}
        target = etree.SubElement(rdf_root, f"{{{RDF_NS}}}Description", nsmap=nsmap)
        target.set(_ABOUT_ATTR, "")

    wanted = {_CONTENT: content_code, _SOURCE: source_iscc, _DATAHASH: source_datahash}
    changed = False
    for tag, value in wanted.items():
        if value is None:
            continue
        if get_simple_property_text(target, tag) != value:
            changed = True
        if tag in target.attrib:
            del target.attrib[tag]
        el = target.find(tag)
        if el is None:
            el = etree.SubElement(target, tag, nsmap={ISCC_XMP_PREFIX: ISCC_XMP_NS})
        el.text = value

    if existing is None:
        return "create"
    return "update" if changed else "unchanged"


def _remove(desc: etree._Element, tag: str) -> None:
    if tag in desc.attrib:
        del desc.attrib[tag]
    el = desc.find(tag)
    if el is not None:
        desc.remove(el)
