"""Reserva TDM en ONIX 3.0: el canal que leen distribuidores, librerías y agregadores.

ONIX 3.0 declara restricciones de uso de productos digitales con
`<EpubUsageConstraint>`: `EpubUsageType` (lista 145) código `11` = minería de
textos y datos, y `EpubUsageStatus` (lista 146) `01` = permitido sin límite,
`03` = prohibido. Es lo mismo que hacen los servicios comerciales; aquí además:

- `add_tdm_to_onix` lo añade a un ONIX que la editorial YA tiene (etiquetas
  de referencia o cortas, con o sin namespace), sin tocar nada más del archivo;
- `build_onix` crea un ONIX mínimo desde el manifiesto (ISBN, título, ISCC)
  para quien no tiene ONIX.

No se sube nada a la red.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from lxml import etree

ONIX_REF_NS = "http://ns.editeur.org/onix/3.0/reference"
TDM_USAGE_TYPE = "11"  # lista 145: Text and data mining
STATUS_PERMITTED = "01"  # lista 146: permitido sin límite
STATUS_PROHIBITED = "03"  # lista 146: prohibido

# Nombres de referencia -> etiqueta corta.
_SHORT = {
    "Product": "product",
    "DescriptiveDetail": "descriptivedetail",
    "ProductForm": "b012",
    "EpubUsageConstraint": "epubusageconstraint",
    "EpubUsageType": "x318",
    "EpubUsageStatus": "x319",
}
# Hijos de DescriptiveDetail que van DESPUÉS de EpubUsageConstraint (orden del XSD).
# TitleDetail es obligatorio, así que siempre hay un punto de inserción.
_AFTER = {
    "EpubLicense",
    "epublicense",
    "MapScale",
    "b063",
    "ProductClassification",
    "productclassification",
    "ProductPart",
    "productpart",
    "Collection",
    "collection",
    "NoCollection",
    "x411",
    "TitleDetail",
    "titledetail",
}
_DIGITAL_AUDIO = ("AJ", "AN")  # audiolibro descargable / en línea


def status_for(reservation: int) -> str:
    return STATUS_PROHIBITED if reservation == 1 else STATUS_PERMITTED


def is_digital_form(product_form: str | None) -> bool:
    """ProductForm E* (digital) o audio descargable; los impresos (B*) no llevan
    EpubUsageConstraint: para ellos va el aviso en la página de derechos."""
    if not product_form:
        return False
    form = product_form.strip().upper()
    return form.startswith("E") or form in _DIGITAL_AUDIO


@dataclass
class OnixChange:
    products: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_print: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"{self.products} producto(s)",
            f"{self.added} con reserva añadida",
            f"{self.updated} actualizados",
            f"{self.unchanged} ya estaban bien",
        ]
        if self.skipped_print:
            parts.append(f"{len(self.skipped_print)} impresos sin cambios")
        return ", ".join(parts)


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _child(parent: etree._Element, name: str) -> etree._Element | None:
    for el in parent:
        if _local(el) == name:
            return el
    return None


def _record_reference(product: etree._Element) -> str:
    for el in product:
        if _local(el) in ("RecordReference", "a001"):
            return (el.text or "").strip()
    return "?"


def add_tdm_to_onix(
    data: bytes, reservation: int, *, all_products: bool = False
) -> tuple[bytes, OnixChange]:
    """Añade (o corrige) la restricción TDM en cada producto digital de un ONIX 3.0.

    Devuelve el XML resultante y un resumen. Lanza ValueError si no es ONIX 3.0.
    """
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"el archivo no es XML válido: {exc}") from exc
    if _local(root) not in ("ONIXMessage", "ONIXmessage"):
        raise ValueError("no es un mensaje ONIX (falta <ONIXMessage>)")
    release = root.get("release", "")
    if release and not release.startswith("3"):
        raise ValueError(f"solo se admite ONIX 3.0 (este es release={release})")
    short = _local(root) == "ONIXmessage"
    ns = etree.QName(root).namespace

    def tag(name: str) -> str:
        local = _SHORT[name] if short else name
        return f"{{{ns}}}{local}" if ns else local

    wanted = status_for(reservation)
    change = OnixChange()
    for product in root:
        if _local(product) != (_SHORT["Product"] if short else "Product"):
            continue
        change.products += 1
        detail = _child(product, _SHORT["DescriptiveDetail"] if short else "DescriptiveDetail")
        if detail is None:
            change.skipped_print.append(_record_reference(product))
            continue
        form_el = _child(detail, _SHORT["ProductForm"] if short else "ProductForm")
        form = form_el.text if form_el is not None else None
        if not all_products and not is_digital_form(form):
            change.skipped_print.append(_record_reference(product))
            continue

        constraint_name = _SHORT["EpubUsageConstraint"] if short else "EpubUsageConstraint"
        type_name = _SHORT["EpubUsageType"] if short else "EpubUsageType"
        status_name = _SHORT["EpubUsageStatus"] if short else "EpubUsageStatus"
        existing = [el for el in detail if _local(el) == constraint_name]
        tdm = next(
            (
                el
                for el in existing
                if (_child(el, type_name) is not None)
                and (_child(el, type_name).text or "").strip() == TDM_USAGE_TYPE
            ),
            None,
        )
        if tdm is not None:
            status_el = _child(tdm, status_name)
            if status_el is not None and (status_el.text or "").strip() == wanted:
                change.unchanged += 1
                continue
            if status_el is None:
                status_el = etree.SubElement(tdm, tag("EpubUsageStatus"))
            status_el.text = wanted
            # Un límite (EpubUsageLimit) no tiene sentido con 01/03.
            for el in list(tdm):
                if _local(el) in ("EpubUsageLimit", "epubusagelimit"):
                    tdm.remove(el)
            change.updated += 1
            continue

        new = etree.Element(tag("EpubUsageConstraint"))
        etree.SubElement(new, tag("EpubUsageType")).text = TDM_USAGE_TYPE
        etree.SubElement(new, tag("EpubUsageStatus")).text = wanted
        if existing:
            anchor = existing[-1]
            anchor.addnext(new)
        else:
            before = next((el for el in detail if _local(el) in _AFTER), None)
            if before is None:
                detail.append(new)
            else:
                before.addprevious(new)
        # Respetar la sangría del documento.
        prev = new.getprevious()
        if prev is not None and prev.tail and prev.tail.strip() == "":
            new.tail = prev.tail
        change.added += 1

    encoding = _declared_encoding(data)
    out = etree.tostring(root.getroottree(), xml_declaration=True, encoding=encoding)
    return out, change


def _declared_encoding(data: bytes) -> str:
    match = re.match(
        rb"<\?xml[^>]*encoding=[\"']([A-Za-z0-9._-]+)[\"']", data.lstrip(b"\xef\xbb\xbf")
    )
    return match.group(1).decode("ascii") if match else "UTF-8"


def tdm_status_in_onix(data: bytes) -> dict[str, str | None]:
    """RecordReference -> estado TDM declarado (01/03/…) o None si no hay."""
    root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
    result: dict[str, str | None] = {}
    for product in root:
        if _local(product) not in ("Product", "product"):
            continue
        status = None
        for constraint in product.iter():
            if _local(constraint) not in ("EpubUsageConstraint", "epubusageconstraint"):
                continue
            kind = next(
                (c.text for c in constraint if _local(c) in ("EpubUsageType", "x318")), None
            )
            if (kind or "").strip() == TDM_USAGE_TYPE:
                status = next(
                    (c.text for c in constraint if _local(c) in ("EpubUsageStatus", "x319")),
                    None,
                )
        result[_record_reference(product)] = status
    return result


# ---- ONIX mínimo desde el manifiesto ------------------------------------------

_FORM_DETAIL = {"pdf": "E107", "epub": "E101"}  # lista 175


def build_onix(rows: list[dict], reservation: int, sender: str | None = None) -> bytes:
    """ONIX 3.0 (etiquetas de referencia) con un producto por obra del manifiesto."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")  # noqa: UP017
    status = status_for(reservation)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<ONIXMessage release="3.0" xmlns="{ONIX_REF_NS}">',
        "  <Header>",
        "    <Sender>",
        f"      <SenderName>{escape(sender or 'Editorial')}</SenderName>",
        "    </Sender>",
        f"    <SentDateTime>{stamp}</SentDateTime>",
        "    <MessageNote>Generado por TDM Seal: reserva de minería de textos y datos"
        " (EpubUsageType 11).</MessageNote>",
        "  </Header>",
    ]
    for i, row in enumerate(rows, 1):
        if str(row.get("estado", "")).startswith("error"):
            continue
        isbn = row.get("isbn")
        iscc = row.get("iscc")
        ref = f"tdmseal.{isbn or (iscc or '').replace('ISCC:', '') or i}"
        out += ["  <Product>", f"    <RecordReference>{escape(ref)}</RecordReference>"]
        out += ["    <NotificationType>03</NotificationType>"]
        if isbn and len(str(isbn)) == 13:
            out += [
                "    <ProductIdentifier>",
                "      <ProductIDType>15</ProductIDType>",
                f"      <IDValue>{escape(str(isbn))}</IDValue>",
                "    </ProductIdentifier>",
            ]
        # ProductIdentifier es obligatorio (XSD): si no hay ISBN ni ISCC, el SHA-256.
        proprietary = [("ISCC", iscc)] if iscc else []
        if not proprietary and not (isbn and len(str(isbn)) == 13):
            proprietary = [("SHA-256", row.get("sha256") or ref)]
        for name, value in proprietary:
            out += [
                "    <ProductIdentifier>",
                "      <ProductIDType>01</ProductIDType>",
                f"      <IDTypeName>{name}</IDTypeName>",
                f"      <IDValue>{escape(str(value))}</IDValue>",
                "    </ProductIdentifier>",
            ]
        out += [
            "    <DescriptiveDetail>",
            "      <ProductComposition>00</ProductComposition>",
            "      <ProductForm>ED</ProductForm>",
        ]
        detail = _FORM_DETAIL.get(str(row.get("formato", "")))
        if detail:
            out.append(f"      <ProductFormDetail>{detail}</ProductFormDetail>")
        title = row.get("titulo") or row.get("archivo") or "Sin título"
        out += [
            "      <EpubUsageConstraint>",
            f"        <EpubUsageType>{TDM_USAGE_TYPE}</EpubUsageType>",
            f"        <EpubUsageStatus>{status}</EpubUsageStatus>",
            "      </EpubUsageConstraint>",
            "      <TitleDetail>",
            "        <TitleType>01</TitleType>",
            "        <TitleElement>",
            "          <TitleElementLevel>01</TitleElementLevel>",
            f"          <TitleText>{escape(str(title))}</TitleText>",
            "        </TitleElement>",
            "      </TitleDetail>",
            "    </DescriptiveDetail>",
            "  </Product>",
        ]
    out.append("</ONIXMessage>")
    return ("\n".join(out) + "\n").encode("utf-8")
