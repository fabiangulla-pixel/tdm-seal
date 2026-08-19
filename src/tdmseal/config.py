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
