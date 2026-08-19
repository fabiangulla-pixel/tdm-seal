"""Modelos de datos centrales de TDM Seal."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

TdmReservation = Literal[0, 1]


@dataclass(frozen=True)
class TDMPolicy:
    """Declaración TDMRep que se desea escribir en un PDF."""

    reservation: TdmReservation
    policy_url: str | None = None

    def __post_init__(self) -> None:
        if self.reservation not in (0, 1):
            raise ValueError(f"tdm:reservation inválido: {self.reservation!r} (debe ser 0 o 1)")
        if self.policy_url is not None:
            from tdmseal.xmp.tdmrep import validate_policy_url

            validate_policy_url(self.policy_url)


@dataclass
class PublisherInfo:
    """Datos de la editorial/titular de derechos, para el reporte de auditoría.

    Puramente informativo: no se escribe en el PDF ni en TDMRep (que solo
    admite `reservation` y `policy_url`). Sirve para dejar constancia de
    quién declaró la reserva de derechos en cada reporte.
    """

    name: str | None = None
    acronym: str | None = None
    website: str | None = None
    rights_email: str | None = None

    def is_empty(self) -> bool:
        return not any([self.name, self.acronym, self.website, self.rights_email])


@dataclass
class TDMRepDeclaration:
    """Declaración TDMRep tal como se leyó de un PDF."""

    reservation: TdmReservation | None
    policy_url: str | None
    present: bool


@dataclass
class PDFInfo:
    """Estado de un PDF observado por el inspector, antes o después de sellar."""

    path: Path
    pdf_version: str
    page_count: int
    pdfa_part: int | None
    pdfa_conformance: str | None
    pdfua_part: int | None
    encrypted: bool
    signed: bool
    has_xmp: bool
    tdm: TDMRepDeclaration
    sha256: str

    @property
    def is_pdfa(self) -> bool:
        return self.pdfa_part is not None


@dataclass
class SealResult:
    """Resultado de intentar sellar un único PDF."""

    input_path: Path
    output_path: Path | None
    status: Literal["success", "skipped", "failed"]
    operation: Literal["create", "update", "none"] | None = None
    reason_code: str | None = None
    before: PDFInfo | None = None
    after: PDFInfo | None = None
    validations: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
