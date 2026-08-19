"""Serialización de paquetes XMP a bytes, con envoltorio xpacket estándar."""

from __future__ import annotations

from lxml import etree

_XPACKET_BEGIN = b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
_XPACKET_END = b'<?xpacket end="w"?>\n'


def serialize_xmp(root: etree._Element) -> bytes:
    """Serializa el árbol XMP completo (x:xmpmeta o rdf:RDF) como paquete XMP."""
    body = etree.tostring(root, xml_declaration=False, encoding="UTF-8")
    return _XPACKET_BEGIN + body + b"\n" + _XPACKET_END
