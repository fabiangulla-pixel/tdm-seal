"""Validación de los datos mínimos que necesita el Policy Builder."""

from __future__ import annotations

import re

from tdmseal.models import PublisherInfo

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_publisher_for_policy(publisher: PublisherInfo) -> None:
    """Lanza ValueError si faltan datos imprescindibles para generar la política."""
    if not publisher.name:
        raise ValueError("Falta el nombre de la editorial.")
    if not publisher.website:
        raise ValueError("Falta el sitio web de la editorial (se usa para derivar el dominio).")
    if not publisher.rights_email:
        raise ValueError("Falta el correo de derechos.")
    if not _EMAIL_RE.match(publisher.rights_email):
        raise ValueError(f"Correo de derechos inválido: {publisher.rights_email!r}")
