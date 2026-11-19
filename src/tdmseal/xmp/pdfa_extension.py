"""PDF/A XMP Extension Schema para TDMRep (PDF/A-1/2/3, sección 6 de la especificación).

PDF/A-1/2/3 exigen declarar cualquier namespace XMP que no forme parte del
conjunto predefinido mediante un `pdfaExtension:schemas` en el XMP de nivel
de documento (ISO 19005-2/3, Annex B). PDF/A-4 no usa este mecanismo.

La plantilla del esquema vive en `resources/tdmrep_pdfa_extension_schema.xml`
(ver `resources/SOURCES.md` sobre su procedencia).
"""

from __future__ import annotations

import copy
from typing import Literal

from lxml import etree

from tdmseal._resources import resource_path
from tdmseal.xmp.parser import RDF_NS, find_rdf_root, iter_descriptions, parse_xmp
from tdmseal.xmp.tdmrep import TDM_NS

PDFA_EXTENSION_NS = "http://www.aiim.org/pdfa/ns/extension/"
PDFA_SCHEMA_NS = "http://www.aiim.org/pdfa/ns/schema#"
PDFA_PROPERTY_NS = "http://www.aiim.org/pdfa/ns/property#"

_SCHEMAS_TAG = f"{{{PDFA_EXTENSION_NS}}}schemas"
_NAMESPACE_URI_TAG = f"{{{PDFA_SCHEMA_NS}}}namespaceURI"
_ABOUT_ATTR = f"{{{RDF_NS}}}about"
TDMREP_TEMPLATE = "tdmrep_pdfa_extension_schema.xml"
ISCC_TEMPLATE = "tdmseal_iscc_pdfa_extension_schema.xml"

MergeOperation = Literal["create", "update", "unchanged"]


def _build_schema_li(template_name: str) -> etree._Element:
    """Construye el <rdf:li rdf:parseType="Resource"> con la descripción de un esquema."""
    template_root = find_rdf_root(parse_xmp(resource_path(template_name).read_bytes()))
    desc = next(iter_descriptions(template_root))

    li = etree.Element(f"{{{RDF_NS}}}li", nsmap={"rdf": RDF_NS})
    li.set(f"{{{RDF_NS}}}parseType", "Resource")
    for child in desc:
        li.append(copy.deepcopy(child))
    return li


def merge_tdmrep_extension_schema(rdf_root: etree._Element) -> MergeOperation:
    """Asegura que `pdfaExtension:schemas` declare el namespace TDMRep."""
    return merge_extension_schema(rdf_root, TDM_NS, TDMREP_TEMPLATE)


def merge_iscc_extension_schema(rdf_root: etree._Element) -> MergeOperation:
    """Asegura que `pdfaExtension:schemas` declare el namespace ISCC de TDM Seal."""
    from tdmseal.iscc.xmp import ISCC_XMP_NS

    return merge_extension_schema(rdf_root, ISCC_XMP_NS, ISCC_TEMPLATE)


def merge_extension_schema(
    rdf_root: etree._Element, namespace: str, template_name: str
) -> MergeOperation:
    """Asegura que `pdfaExtension:schemas` declare `namespace` con la plantilla dada.

    No toca otros esquemas ya declarados (p. ej. por InDesign). Idempotente:
    si la entrada del namespace ya está presente, no la duplica.
    """
    schemas_el = None
    for desc in iter_descriptions(rdf_root):
        if desc.get(_ABOUT_ATTR) != "":
            continue
        el = desc.find(_SCHEMAS_TAG)
        if el is not None:
            schemas_el = el
            break

    if schemas_el is None:
        nsmap = {"rdf": RDF_NS, "pdfaExtension": PDFA_EXTENSION_NS}
        desc = etree.SubElement(rdf_root, f"{{{RDF_NS}}}Description", nsmap=nsmap)
        desc.set(_ABOUT_ATTR, "")
        schemas_el = etree.SubElement(desc, _SCHEMAS_TAG)
        bag = etree.SubElement(schemas_el, f"{{{RDF_NS}}}Bag")
        bag.append(_build_schema_li(template_name))
        return "create"

    bag = schemas_el.find(f"{{{RDF_NS}}}Bag")
    if bag is None:
        bag = etree.SubElement(schemas_el, f"{{{RDF_NS}}}Bag")

    for li in bag.findall(f"{{{RDF_NS}}}li"):
        ns_el = li.find(_NAMESPACE_URI_TAG)
        if ns_el is not None and ns_el.text and ns_el.text.strip() == namespace:
            return "unchanged"

    bag.append(_build_schema_li(template_name))
    return "update"
