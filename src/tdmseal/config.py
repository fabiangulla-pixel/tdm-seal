"""Configuración de una operación de sellado (equivalente al `config` del pseudocódigo)."""

from __future__ import annotations

from dataclasses import dataclass

from tdmseal.models import TDMPolicy


@dataclass
class SealConfig:
    policy: TDMPolicy
    output_suffix: str = "_TDM"
    force_signed: bool = False
    allow_encrypted: bool = False
    run_qpdf_check: bool = True
    run_verapdf: bool = True
    # Calcular el ISCC completo (Meta + Text + Data + Instance) y escribirlo en el XMP.
    compute_iscc: bool = False
    # Preferencias IETF AIPREF (AiPreferences). No se incrustan en el archivo:
    # el borrador no lo define; se registran en el reporte (ver aipref.py).
    aipref: object | None = None
    # Aviso visible (NoticeOptions). None = desactivado (por defecto).
    notice: object | None = None
