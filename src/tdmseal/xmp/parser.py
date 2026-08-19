"""Parseo controlado de paquetes XMP (RDF/XML) preservando todo su contenido."""

from __future__ import annotations

from lxml import etree

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
X_NS = "adobe:ns:meta/"

_EMPTY_XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    b"</rdf:RDF>\n"
    b"</x:xmpmeta>\n"
)


class XMPParseError(ValueError):
    """El paquete XMP existente no es XML/RDF válido."""


def parse_xmp(xmp_bytes: bytes | None) -> etree._Element:
    """Parsea el XMP existente de un PDF, o crea un paquete vacío si no había ninguno.

    Nunca reconstruye desde cero un XMP existente: si hay bytes, se parsean tal
    cual (namespaces y propiedades desconocidas incluidos) y solo se modifica lo
    que TDM Seal necesita tocar.
    """
    source = xmp_bytes if xmp_bytes else _EMPTY_XMP
    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(source, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise XMPParseError(f"XMP malformado: {exc}") from exc
    return root


def find_rdf_root(xmpmeta_or_rdf: etree._Element) -> etree._Element:
    """Devuelve el elemento rdf:RDF, ya sea la raíz misma o dentro de x:xmpmeta."""
    if etree.QName(xmpmeta_or_rdf).localname == "RDF":
        return xmpmeta_or_rdf
    rdf = xmpmeta_or_rdf.find(f"{{{RDF_NS}}}RDF")
    if rdf is None:
        raise XMPParseError("El paquete XMP no contiene un elemento rdf:RDF")
    return rdf


def iter_descriptions(rdf_root: etree._Element):
    """Itera los rdf:Description hijos directos de rdf:RDF."""
    yield from rdf_root.findall(f"{{{RDF_NS}}}Description")


def get_simple_property_text(desc: etree._Element, tag: str) -> str | None:
    """Lee una propiedad XMP simple en cualquiera de sus dos formas válidas:

    como atributo del propio rdf:Description (`tag="valor"`) o como elemento
    hijo (`<tag>valor</tag>`). `tag` debe ir en notación Clark `{ns}local`.
    """
    val = desc.get(tag)
    if val is not None:
        return val
    el = desc.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return None


def find_simple_property(rdf_root: etree._Element, namespace: str, local: str) -> str | None:
    """Busca una propiedad simple (namespace, local) en cualquier rdf:Description."""
    tag = f"{{{namespace}}}{local}"
    for desc in iter_descriptions(rdf_root):
        value = get_simple_property_text(desc, tag)
        if value is not None:
            return value
    return None
