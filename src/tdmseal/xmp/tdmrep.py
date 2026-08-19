"""Lectura y escritura de la declaración TDMRep dentro del XMP de nivel de documento.

Referencia: W3C TDM Reservation Protocol (TDMRep), Final Community Group
Report, 10 de mayo de 2024. https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/
"""

from __future__ import annotations

from urllib.parse import urlparse

from lxml import etree

from tdmseal.errors import TDM003_INVALID_RESERVATION, TDM004_INVALID_POLICY_URL, TDMSealError
from tdmseal.models import TDMPolicy, TDMRepDeclaration
from tdmseal.xmp.parser import RDF_NS, get_simple_property_text, iter_descriptions

TDM_NS = "http://www.w3.org/ns/tdmrep/"

_RESERVATION_TAG = f"{{{TDM_NS}}}reservation"
_POLICY_TAG = f"{{{TDM_NS}}}policy"
_ABOUT_ATTR = f"{{{RDF_NS}}}about"


def validate_policy_url(url: str) -> None:
    """Valida sintácticamente que `url` sea una URL absoluta http(s).

    No requiere conexión a internet: solo valida esquema y autoridad.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise TDMSealError(
            TDM004_INVALID_POLICY_URL,
            f"tdm:policy debe ser una URL absoluta http/https: {url!r}",
        )


def validate_reservation(value: int) -> None:
    if value not in (0, 1):
        raise TDMSealError(
            TDM003_INVALID_RESERVATION,
            f"tdm:reservation debe ser 0 o 1, se recibió {value!r}",
        )


def _find_tdm_descriptions(rdf_root: etree._Element) -> list[etree._Element]:
    """rdf:Description con rdf:about="" que ya declaran alguna propiedad tdm:*.

    Reconoce tanto la forma de elemento (`<tdm:reservation>1</tdm:reservation>`)
    como la forma de atributo (`tdm:reservation="1"`), usada por algunas
    herramientas de edición de metadatos.
    """
    result = []
    for desc in iter_descriptions(rdf_root):
        about = desc.get(_ABOUT_ATTR)
        if about != "":
            continue
        if (
            get_simple_property_text(desc, _RESERVATION_TAG) is not None
            or get_simple_property_text(desc, _POLICY_TAG) is not None
        ):
            result.append(desc)
    return result


def read_tdmrep(rdf_root: etree._Element) -> TDMRepDeclaration:
    """Lee la declaración TDMRep actual del XMP de nivel de documento, si existe."""
    reservation: int | None = None
    policy_url: str | None = None
    present = False

    for desc in _find_tdm_descriptions(rdf_root):
        res_text = get_simple_property_text(desc, _RESERVATION_TAG)
        if res_text is not None:
            present = True
            try:
                reservation = int(res_text)
            except ValueError:
                reservation = None
        pol_text = get_simple_property_text(desc, _POLICY_TAG)
        if pol_text:
            present = True
            policy_url = pol_text

    return TDMRepDeclaration(reservation=reservation, policy_url=policy_url, present=present)


def write_tdmrep(rdf_root: etree._Element, policy: TDMPolicy) -> str:
    """Inserta o actualiza tdm:reservation / tdm:policy en el XMP de nivel de documento.

    No toca ningún otro rdf:Description ni ninguna otra propiedad. Devuelve
    "create" si no existía declaración previa, o "update" si se sustituyó una
    existente.
    """
    existing = _find_tdm_descriptions(rdf_root)
    operation = "update" if existing else "create"

    if existing:
        desc = existing[0]
        # Si hay varias Description con propiedades tdm:*, se consolidan en la
        # primera y se retiran las propiedades tdm:* de las demás para no dejar
        # declaraciones contradictorias.
        for extra in existing[1:]:
            _strip_tdm_property(extra, _RESERVATION_TAG)
            _strip_tdm_property(extra, _POLICY_TAG)
    else:
        nsmap = {"rdf": RDF_NS, "tdm": TDM_NS}
        desc = etree.SubElement(rdf_root, f"{{{RDF_NS}}}Description", nsmap=nsmap)
        desc.set(_ABOUT_ATTR, "")

    # Si la propiedad existía como atributo, se retira: a partir de ahora se
    # escribe siempre en forma de elemento, para no dejar dos declaraciones
    # simultáneas de la misma propiedad.
    if _RESERVATION_TAG in desc.attrib:
        del desc.attrib[_RESERVATION_TAG]
    if _POLICY_TAG in desc.attrib:
        del desc.attrib[_POLICY_TAG]

    _set_child_text(desc, _RESERVATION_TAG, str(policy.reservation), nsmap={"tdm": TDM_NS})

    if policy.policy_url:
        _set_child_text(desc, _POLICY_TAG, policy.policy_url, nsmap={"tdm": TDM_NS})
    else:
        pol_el = desc.find(_POLICY_TAG)
        if pol_el is not None:
            desc.remove(pol_el)

    return operation


def _strip_tdm_property(desc: etree._Element, tag: str) -> None:
    if tag in desc.attrib:
        del desc.attrib[tag]
    el = desc.find(tag)
    if el is not None:
        desc.remove(el)


def _set_child_text(parent: etree._Element, tag: str, text: str, nsmap: dict[str, str]) -> None:
    el = parent.find(tag)
    if el is None:
        el = etree.SubElement(parent, tag, nsmap=nsmap)
    el.text = text
