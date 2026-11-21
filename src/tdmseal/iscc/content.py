"""ISCC de contenido para PDF: Meta-Code + Text-Code + Data-Code + Instance-Code.

El Text-Code (Content-Code de texto) se calcula sobre el texto del documento,
no sobre sus bytes. Por eso **no cambia al sellar**: TDM Seal solo toca el XMP,
y el texto de las páginas sigue idéntico. El Data-Code y el Instance-Code, en
cambio, sí cambian, porque son huellas de los bytes del archivo.

Compatibilidad con iscc-sdk
---------------------------
Se reproduce el mismo procedimiento que `iscc_sdk.code_iscc` (v0.9.7) para
PDF, sin arrastrar sus dependencias pesadas (Tika embebido, numpy, exiv2…):

- texto: `pypdfium2`, página por página con `get_text_bounded()`, unido con
  saltos de línea; luego `text_clean` y `gen_text_code_v0` (64 bits);
- nombre para el Meta-Code: `/iscc_name` o `/Title` del diccionario Info, o
  si no hay, `dc:title` del XMP; si sigue vacío, el nombre del archivo sin
  extensión (con `-` y `_` cambiados por espacios), igual que el SDK;
- descripción: `/iscc_description` o `/Subject` del Info, o `dc:description`.

`tests/unit/test_iscc_content.py` compara contra iscc-sdk cuando está
instalado (no es dependencia del proyecto).

Diferencia deliberada con el SDK: si el PDF no tiene capa de texto (p. ej.
un escaneo sin OCR), el SDK calcula el Text-Code de un texto vacío, que es
el mismo para todos los PDF sin texto y por tanto no identifica nada. Aquí
se omite el Text-Code y se avisa.

`pypdfium2` es un extra opcional (`pip install tdm-seal[iscc]`). Sin él se
calculan Meta-Code, Data-Code e Instance-Code y se avisa de que falta el de
contenido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

import iscc_core as ic
import pikepdf

from tdmseal.iscc.data import compute_iscc
from tdmseal.pdf.docinfo import find_inherited_info
from tdmseal.xmp.parser import RDF_NS, find_rdf_root, parse_xmp

DC_NS = "http://purl.org/dc/elements/1.1/"

NO_EXTRA_WARNING = (
    "ISCC de contenido no calculado: falta el extra opcional (instale "
    "'tdm-seal[iscc]', que añade pypdfium2). Solo se calcularon Meta-Code, "
    "Data-Code e Instance-Code."
)
NO_EPUB_EXTRA_WARNING = (
    "ISCC de contenido del EPUB no calculado: falta el extra opcional "
    "'tdm-seal[iscc-epub]' (iscc-tika, ~110 MB, el mismo extractor que usa "
    "iscc-sdk). Solo se calcularon Meta-Code, Data-Code e Instance-Code."
)
# Mismo tope que iscc-sdk (text.py), para que todos deriven el mismo ISCC.
TEXT_EXTRACT_MAX_LENGTH = 10_000_000
NO_TEXT_WARNING = (
    "ISCC de contenido no calculado: el documento no tiene capa de texto "
    "extraíble (¿PDF escaneado sin OCR?). Solo se calcularon Meta-Code, "
    "Data-Code e Instance-Code."
)

_TAG_RE = re.compile(r"<[^>]*>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", flags=re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ContentIscc:
    """ISCC completo de un PDF y sus unidades."""

    iscc: str
    meta_code: str
    text_code: str | None
    data_code: str
    instance_code: str
    datahash: str
    filesize: int
    name: str
    description: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def content_computed(self) -> bool:
        return self.text_code is not None

    def to_dict(self) -> dict:
        return {
            "iscc": self.iscc,
            "units": {
                "meta": self.meta_code,
                "content_text": self.text_code,
                "data": self.data_code,
                "instance": self.instance_code,
            },
            "datahash": self.datahash,
            "filesize": self.filesize,
            "meta_name": self.name,
            "meta_description": self.description,
            "generator": f"tdm-seal (iscc-core {ic.__version__})",
            "warnings": list(self.warnings),
        }


def content_extra_available() -> bool:
    """True si el extra opcional `[iscc]` (pypdfium2) está instalado."""
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


def extract_pdf_text(path: Path) -> str:
    """Extrae el texto como iscc-sdk (`pdf_text_extract`). Requiere pypdfium2."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        parts = []
        for page in doc:
            textpage = page.get_textpage()
            try:
                parts.append(textpage.get_text_bounded())
            finally:
                textpage.close()
                page.close()
        return "\n".join(parts)
    finally:
        doc.close()


def _sanitize(value: str) -> str:
    """Equivalente ligero de `iscc_sdk.text_sanitize` (sin bleach)."""
    value = _SCRIPT_STYLE_RE.sub("", value)
    value = unescape(_TAG_RE.sub("", value))
    return re.sub(r"\s+", " ", value).strip()


def _info_value(info: pikepdf.Dictionary | None, key: str) -> str | None:
    if info is None:
        return None
    try:
        value = info.get(key)
    except (pikepdf.PdfError, AttributeError):
        return None
    if value is None:
        return None
    text = _sanitize(str(value))
    return text or None


def _xmp_dc_value(pdf: pikepdf.Pdf, local: str) -> str | None:
    metadata = pdf.Root.get("/Metadata")
    if metadata is None:
        return None
    try:
        rdf_root = find_rdf_root(parse_xmp(bytes(metadata.read_bytes())))
    except Exception:  # noqa: BLE001 — XMP ilegible: simplemente no hay valor
        return None
    for el in rdf_root.iter(f"{{{DC_NS}}}{local}"):
        texts = [li.text for li in el.iter(f"{{{RDF_NS}}}li") if li.text]
        candidate = texts[0] if texts else el.text
        if candidate:
            text = _sanitize(candidate)
            if text:
                return text
    return None


def name_from_filename(path: Path) -> str:
    """Nombre de respaldo, como `iscc_sdk.text_name_from_uri`."""
    return Path(path).stem.replace("-", " ").replace("_", " ")


def read_pdf_meta(path: Path) -> tuple[str | None, str | None]:
    """Devuelve (nombre, descripción) del PDF para el Meta-Code."""
    with pikepdf.open(path) as pdf:
        # Info heredado de tráileres anteriores incluido, como hace PDFBox/Tika.
        info = pdf.trailer.get("/Info")
        if info is None:
            info = find_inherited_info(pdf, path)
        name = (
            _info_value(info, "/iscc_name")
            or _info_value(info, "/Title")
            or _xmp_dc_value(pdf, "title")
        )
        description = (
            _info_value(info, "/iscc_description")
            or _info_value(info, "/Subject")
            or _xmp_dc_value(pdf, "description")
        )
    return name, description


def _normalized_name(name: str | None) -> str:
    value = ic.text_clean(name or "")
    value = ic.text_remove_newlines(value)
    return ic.text_trim(value, ic.core_opts.meta_trim_name)


def epub_extra_available() -> bool:
    """True si el extra opcional `[iscc-epub]` (iscc-tika) está instalado."""
    try:
        import iscc_tika  # noqa: F401
    except ImportError:
        return False
    return True


def extract_epub_text(path: Path) -> str:
    """Extrae el texto como iscc-sdk (`text_extract`, Tika). Requiere iscc-tika."""
    from iscc_tika import Extractor

    extractor = Extractor().set_extract_string_max_length(TEXT_EXTRACT_MAX_LENGTH)
    text, _meta = extractor.extract_file_to_string(Path(path).as_posix())
    return text


def read_epub_meta(path: Path) -> tuple[str | None, str | None]:
    """(título, descripción) del OPF, primer dc:title / dc:description."""
    import zipfile

    from tdmseal.epub.container import find_opf_path
    from tdmseal.epub.opf import parse_opf, read_dc

    with zipfile.ZipFile(path) as zf:
        root = parse_opf(zf.read(find_opf_path(zf)))
    title = read_dc(root, "title")
    description = read_dc(root, "description")
    return (
        _sanitize(title) if title else None,
        _sanitize(description) if description else None,
    )


def compute_content_iscc(path: Path, bits: int = 64) -> ContentIscc:
    """Calcula el ISCC-CODE completo de un PDF o EPUB (sin red, sin escribir nada).

    `bits` es el tamaño de cada unidad: 64 (como iscc-sdk) o 256 (unidades
    completas para declarar en un hub ISCC). El ISCC-CODE compuesto es el mismo.
    """
    path = Path(path)
    warnings: list[str] = []
    is_epub = path.suffix.lower() == ".epub"

    name, description = read_epub_meta(path) if is_epub else read_pdf_meta(path)
    if not _normalized_name(name):
        name = name_from_filename(path)
    meta = ic.gen_meta_code_v0(name=name, description=description, bits=bits)

    text_code: str | None = None
    if is_epub and not epub_extra_available():
        warnings.append(NO_EPUB_EXTRA_WARNING)
    elif not is_epub and not content_extra_available():
        warnings.append(NO_EXTRA_WARNING)
    else:
        raw = extract_epub_text(path) if is_epub else extract_pdf_text(path)
        text = ic.text_clean(raw)
        if text.strip():
            text_code = ic.gen_text_code_v0(text, bits=bits)["iscc"]
        else:
            warnings.append(NO_TEXT_WARNING)

    data = compute_iscc(path, bits=bits)
    units = [meta["iscc"]]
    if text_code:
        units.append(text_code)
    units += [data.data_code, data.instance_code]
    combined = ic.gen_iscc_code_v0(units)

    return ContentIscc(
        iscc=combined["iscc"],
        meta_code=meta["iscc"],
        text_code=text_code,
        data_code=data.data_code,
        instance_code=data.instance_code,
        datahash=data.datahash,
        filesize=data.filesize,
        name=name,
        description=description,
        warnings=warnings,
    )
