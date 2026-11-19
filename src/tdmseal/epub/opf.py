"""TDMRep (y el ISCC de TDM Seal) en el paquete OPF de un EPUB.

Sintaxis según TDMRep, Final CG Report 10-may-2024, secciones 6.4 y 6.5:

- EPUB 3: `<package prefix="tdm: http://www.w3.org/ns/tdmrep#">` y
  `<meta property="tdm:reservation">1</meta>`, `<meta property="tdm:policy">URL</meta>`.
- EPUB 2: `<meta name="tdm:reservation" content="1"/>`, `<meta name="tdm:policy" content="URL"/>`.

Se leen las dos formas en cualquier versión (hay EPUB 3 que conservan metas
de estilo EPUB 2 por compatibilidad). Al escribir se usa la forma de la
versión del paquete y, si existe la otra, se actualiza también para no dejar
declaraciones contradictorias.

El ISCC usa el mismo esquema con el prefijo `tdmseal` (ver
docs/xmp-namespace-iscc.md): `tdmseal:isccContentCode`, `tdmseal:isccSource`,
`tdmseal:isccSourceDatahash`.
"""

from __future__ import annotations

import re

from lxml import etree

from tdmseal.iscc.xmp import ISCC_XMP_NS, DeclaredIscc, resolve_provenance
from tdmseal.models import TDMPolicy, TDMRepDeclaration

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
TDM_EPUB_URI = "http://www.w3.org/ns/tdmrep#"
_META = f"{{{OPF_NS}}}meta"
_METADATA = f"{{{OPF_NS}}}metadata"

_ISCC_PROPS = ("isccContentCode", "isccSource", "isccSourceDatahash")


def parse_opf(data: bytes) -> etree._Element:
    parser = etree.XMLParser(
        remove_blank_text=False, resolve_entities=False, no_network=True, huge_tree=False
    )
    return etree.fromstring(data, parser=parser)


def serialize_opf(root: etree._Element, original: bytes) -> bytes:
    """Serializa conservando la declaración XML si el original la tenía."""
    had_declaration = original.lstrip().startswith(b"<?xml")
    return etree.tostring(root, xml_declaration=had_declaration, encoding="utf-8")


def is_epub3(root: etree._Element) -> bool:
    return (root.get("version") or "").strip().startswith("3")


def _metadata(root: etree._Element) -> etree._Element:
    md = root.find(_METADATA)
    if md is None:
        raise ValueError("el paquete OPF no tiene <metadata>")
    return md


def _metas(root: etree._Element, name: str) -> list[etree._Element]:
    """Metas (de cualquiera de las dos formas) que declaran `name`, sin `refines`."""
    found = []
    for meta in _metadata(root).iter(_META):
        if meta.get("refines"):
            continue
        if meta.get("property") == name or meta.get("name") == name:
            found.append(meta)
    return found


def _meta_value(meta: etree._Element) -> str | None:
    value = meta.get("content") if meta.get("name") else meta.text
    return value.strip() if value and value.strip() else None


def get_meta(root: etree._Element, name: str) -> str | None:
    for meta in _metas(root, name):
        value = _meta_value(meta)
        if value is not None:
            return value
    return None


def _parse_prefixes(value: str) -> list[tuple[str, str]]:
    return re.findall(r"([A-Za-z_][\w.-]*):\s+(\S+)", value or "")


def ensure_prefix(root: etree._Element, prefix: str, uri: str) -> None:
    """Declara `prefix: uri` en el atributo `prefix` de <package> (EPUB 3)."""
    pairs = [(p, u) for p, u in _parse_prefixes(root.get("prefix", "")) if p != prefix]
    pairs.append((prefix, uri))
    root.set("prefix", " ".join(f"{p}: {u}" for p, u in pairs))


def set_meta(root: etree._Element, name: str, value: str | None, epub3: bool) -> None:
    """Fija (o retira si value es None) la propiedad `name` en todas sus formas."""
    metas = _metas(root, name)
    if value is None:
        for meta in metas:
            meta.getparent().remove(meta)
        return
    native = [m for m in metas if (m.get("property") if epub3 else m.get("name"))]
    if not native:
        md = _metadata(root)
        meta = etree.SubElement(md, _META)
        if epub3:
            meta.set("property", name)
        else:
            meta.set("name", name)
        _indent_like_siblings(md, meta)
        native = [meta]
    for extra in native[1:]:  # no dejar duplicados de la misma forma
        extra.getparent().remove(extra)
    for meta in [native[0], *[m for m in metas if m not in native]]:
        if meta.get("name"):
            meta.set("content", value)
        else:
            meta.text = value


def _indent_like_siblings(parent: etree._Element, new: etree._Element) -> None:
    """Mantiene la sangría del OPF al añadir `new` como último hijo de `parent`."""
    prev = new.getprevious()
    if prev is None:
        return
    closing = prev.tail  # espacio antes de </metadata>
    before_prev = prev.getprevious()
    between = before_prev.tail if before_prev is not None else parent.text
    if between is not None and between.strip() == "":
        prev.tail = between
    new.tail = closing


# ---- TDMRep -------------------------------------------------------------------


def read_tdm(root: etree._Element) -> TDMRepDeclaration:
    res_text = get_meta(root, "tdm:reservation")
    policy = get_meta(root, "tdm:policy")
    reservation = None
    if res_text is not None:
        try:
            reservation = int(res_text)
        except ValueError:
            reservation = None
    present = res_text is not None or policy is not None
    return TDMRepDeclaration(reservation=reservation, policy_url=policy, present=present)


def write_tdm(root: etree._Element, policy: TDMPolicy) -> str:
    """Inserta o actualiza tdm:reservation / tdm:policy. Devuelve create/update."""
    operation = "update" if read_tdm(root).present else "create"
    epub3 = is_epub3(root)
    if epub3:
        ensure_prefix(root, "tdm", TDM_EPUB_URI)
    set_meta(root, "tdm:reservation", str(policy.reservation), epub3)
    set_meta(root, "tdm:policy", policy.policy_url, epub3)
    return operation


# ---- ISCC ---------------------------------------------------------------------


def read_iscc(root: etree._Element) -> DeclaredIscc | None:
    values = [get_meta(root, f"tdmseal:{prop}") for prop in _ISCC_PROPS]
    if not any(values):
        return None
    return DeclaredIscc(*values)


def write_iscc(
    root: etree._Element, *, content_code: str | None, source_iscc: str, source_datahash: str
) -> None:
    content_code, source_iscc, source_datahash = resolve_provenance(
        read_iscc(root), content_code, source_iscc, source_datahash
    )
    epub3 = is_epub3(root)
    if epub3:
        ensure_prefix(root, "tdmseal", ISCC_XMP_NS)
    for prop, value in zip(_ISCC_PROPS, (content_code, source_iscc, source_datahash), strict=True):
        if value is not None:
            set_meta(root, f"tdmseal:{prop}", value, epub3)


# ---- Aviso visible (documento XHTML añadido al final del spine) ----------------


def is_fixed_layout(root: etree._Element) -> bool:
    return get_meta(root, "rendition:layout") == "pre-paginated"


def has_manifest_item(root: etree._Element, item_id: str) -> bool:
    manifest = root.find(f"{{{OPF_NS}}}manifest")
    return manifest is not None and any(i.get("id") == item_id for i in manifest)


def add_spine_document(root: etree._Element, item_id: str, href: str) -> None:
    """Añade un XHTML al manifiesto y al final del spine (lineal)."""
    manifest = root.find(f"{{{OPF_NS}}}manifest")
    spine = root.find(f"{{{OPF_NS}}}spine")
    if manifest is None or spine is None:
        raise ValueError("el paquete OPF no tiene <manifest> o <spine>")
    item = etree.SubElement(manifest, f"{{{OPF_NS}}}item")
    item.set("id", item_id)
    item.set("href", href)
    item.set("media-type", "application/xhtml+xml")
    _indent_like_siblings(manifest, item)
    itemref = etree.SubElement(spine, f"{{{OPF_NS}}}itemref")
    itemref.set("idref", item_id)
    _indent_like_siblings(spine, itemref)


# ---- Metadatos descriptivos (para el Meta-Code) -------------------------------


def read_dc(root: etree._Element, local: str) -> str | None:
    for el in _metadata(root).iter(f"{{{DC_NS}}}{local}"):
        if el.text and el.text.strip():
            return el.text.strip()
    return None
